"""Tests de watchgate/core/layers/_semantic/llm_providers.py (§7.3)."""

from __future__ import annotations

import json

import httpx
import pytest

from watchgate.core.layers._semantic.client import SemanticParsingError
from watchgate.core.layers._semantic.llm_providers import GeminiClient, OpenAICompatibleClient
from watchgate.core.layers._semantic.prompting import (
    _CACHE_BREAKPOINT_MARKER,
    build_system_prompt,
)
from watchgate.core.models import Confidence, RiskCategory


def _valid_json(**overrides: object) -> str:
    payload = {
        "risk_score": 85,
        "category": "backdoor",
        "justification": "x",
        "confidence": "alta",
    }
    payload.update(overrides)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# GeminiClient — usa los tipos reales del SDK google-genai; solo se stubea la
# llamada de red (`models.generate_content`).
# ---------------------------------------------------------------------------


def _gemini_text_response(text: str):
    from google.genai import types

    content = types.Content(role="model", parts=[types.Part(text=text)])
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


def _gemini_function_call_response(name: str, args: dict, call_id: str = "call1"):
    from google.genai import types

    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(id=call_id, name=name, args=args)
                        )
                    ],
                )
            )
        ]
    )


class _FakeModels:
    def __init__(self, responses: list) -> None:
        self._responses = iter(responses)
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return next(self._responses)


class _FakeGenaiClient:
    def __init__(self, responses: list) -> None:
        self.models = _FakeModels(responses)


def test_gemini_returns_output_when_model_answers_directly_with_valid_json():
    fake = _FakeGenaiClient([_gemini_text_response(_valid_json())])
    client = GeminiClient(client=fake)

    output = client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    assert output.risk_score == 85
    assert output.category == RiskCategory.BACKDOOR
    assert output.confidence == Confidence.ALTA


def test_gemini_sends_configured_temperature():
    """Determinismo del score, no "creatividad" -- ver GeminiClient.__init__."""
    fake = _FakeGenaiClient([_gemini_text_response(_valid_json())])
    client = GeminiClient(client=fake, temperature=0.3)

    client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    assert fake.models.calls[0]["config"].temperature == 0.3


def test_gemini_executes_function_call_and_continues_the_conversation():
    responses = [
        _gemini_function_call_response("fetch_referenced_file", {"path": "a"}),
        _gemini_text_response(_valid_json(risk_score=10, category="ninguna")),
    ]
    fake = _FakeGenaiClient(responses)
    calls = []

    def executor(name: str, tool_input: dict) -> str:
        calls.append((name, tool_input))
        return "contenido del fichero"

    client = GeminiClient(client=fake)
    output = client.complete_structured(
        "sys",
        "user",
        tools=[{"name": "fetch_referenced_file", "description": "d", "input_schema": {}}],
        tool_executor=executor,
        max_tool_calls=3,
    )

    assert output.risk_score == 10
    assert calls == [("fetch_referenced_file", {"path": "a"})]


def test_gemini_forces_final_answer_once_tool_budget_is_exhausted():
    responses = [
        _gemini_function_call_response("t", {}, "c1"),
        _gemini_function_call_response("t", {}, "c2"),
        _gemini_text_response(_valid_json(risk_score=0, category="ninguna")),
    ]
    fake = _FakeGenaiClient(responses)
    calls = []

    client = GeminiClient(client=fake)
    output = client.complete_structured(
        "sys",
        "user",
        tools=[{"name": "t", "description": "d", "input_schema": {}}],
        tool_executor=lambda n, i: calls.append((n, i)) or "x",
        max_tool_calls=1,
    )

    assert len(calls) == 1
    assert output.risk_score == 0


def test_gemini_retries_once_on_invalid_json_then_succeeds():
    fake = _FakeGenaiClient(
        [
            _gemini_text_response("esto no es json"),
            _gemini_text_response(_valid_json(risk_score=20, category="ofuscacion")),
        ]
    )
    client = GeminiClient(client=fake)

    output = client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )
    assert output.risk_score == 20


def test_gemini_raises_clear_error_instead_of_indexerror_when_candidates_empty():
    """Gemini puede devolver `candidates` vacío (p. ej. respuesta bloqueada
    por sus propios filtros de seguridad) -- antes de este fix,
    `response.candidates[0]` reventaba con IndexError sin contexto útil."""
    from google.genai import types

    fake = _FakeGenaiClient([types.GenerateContentResponse(candidates=[])])
    client = GeminiClient(client=fake)

    with pytest.raises(SemanticParsingError, match="no devolvió ningún candidate"):
        client.complete_structured(
            "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
        )


def test_gemini_raises_clear_error_when_candidates_empty_on_retry():
    from google.genai import types

    fake = _FakeGenaiClient(
        [
            _gemini_text_response("no json"),
            types.GenerateContentResponse(candidates=[]),
        ]
    )
    client = GeminiClient(client=fake)

    with pytest.raises(SemanticParsingError, match="no devolvió ningún candidate en el reintento"):
        client.complete_structured(
            "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
        )


def test_gemini_raises_semantic_parsing_error_after_two_invalid_json_attempts():
    fake = _FakeGenaiClient(
        [_gemini_text_response("no json"), _gemini_text_response("sigue sin ser json")]
    )
    client = GeminiClient(client=fake)

    with pytest.raises(SemanticParsingError, match="LLM no devolvió JSON válido tras 2 intentos"):
        client.complete_structured(
            "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
        )


def test_gemini_raises_instead_of_looping_forever_if_model_keeps_requesting_tools():
    fake = _FakeGenaiClient([_gemini_function_call_response("t", {}, f"c{i}") for i in range(20)])
    client = GeminiClient(client=fake)

    with pytest.raises(SemanticParsingError, match="siguió pidiendo tool calls"):
        client.complete_structured(
            "sys",
            "user",
            tools=[{"name": "t", "description": "d", "input_schema": {}}],
            tool_executor=lambda n, i: "x",
            max_tool_calls=3,
        )

    assert len(fake.models.calls) == 6


def test_gemini_summarize_file_parses_valid_json_response():
    fake = _FakeGenaiClient(
        [_gemini_text_response('{"category": "api", "summary": "Endpoint REST."}')]
    )
    client = GeminiClient(client=fake)

    result = client.summarize_file("api/handler.py", "def handler(): pass", ["def handler():"])

    assert result.category == "api"
    assert result.summary == "Endpoint REST."


def test_gemini_summarize_file_degrades_to_unknown_when_no_candidates():
    from google.genai import types

    fake = _FakeGenaiClient([types.GenerateContentResponse(candidates=[])])
    client = GeminiClient(client=fake)

    result = client.summarize_file("x.py", "content", [])

    assert result.category == "unknown"
    assert "x.py" in result.summary


def test_gemini_synthesize_text_returns_raw_text():
    fake = _FakeGenaiClient([_gemini_text_response("## Arquitectura\nResumen.")])
    client = GeminiClient(client=fake)

    assert client.synthesize_text("sys", "user") == "## Arquitectura\nResumen."


def test_gemini_synthesize_text_returns_empty_on_failure():
    class _RaisingModels:
        def generate_content(self, **kwargs: object) -> None:
            raise RuntimeError("red caída")

    class _RaisingClient:
        models = _RaisingModels()

    client = GeminiClient(client=_RaisingClient())

    assert client.synthesize_text("sys", "user") == ""


# ---------------------------------------------------------------------------
# OpenAICompatibleClient — protocolo de chat completions de OpenAI, el mismo
# que hablan Ollama/llama.cpp server/LM Studio/vLLM en local.
# ---------------------------------------------------------------------------


class _FakeTransport(httpx.BaseTransport):
    """Devuelve una secuencia fija de respuestas JSON, sin red real."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = iter(responses)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=next(self._responses))


def _chat_response(message: dict) -> dict:
    return {"choices": [{"message": message}]}


def _local_client(responses: list[dict]) -> tuple[OpenAICompatibleClient, _FakeTransport]:
    transport = _FakeTransport(responses)
    httpx_client = httpx.Client(transport=transport)
    client = OpenAICompatibleClient(
        base_url="http://localhost:11434/v1", model="llama3.1", client=httpx_client
    )
    return client, transport


def test_local_sends_configured_temperature():
    """Determinismo del score, no "creatividad" -- ver OpenAICompatibleClient.__init__."""
    transport = _FakeTransport([_chat_response({"role": "assistant", "content": _valid_json()})])
    httpx_client = httpx.Client(transport=transport)
    client = OpenAICompatibleClient(
        base_url="http://localhost:11434/v1",
        model="llama3.1",
        client=httpx_client,
        temperature=0.3,
    )

    client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    sent_payload = json.loads(transport.requests[0].content)
    assert sent_payload["temperature"] == 0.3


def test_local_returns_output_when_model_answers_directly_with_valid_json():
    client, _ = _local_client([_chat_response({"role": "assistant", "content": _valid_json()})])

    output = client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )
    assert output.risk_score == 85
    assert output.category == RiskCategory.BACKDOOR


def test_local_executes_tool_call_and_continues_the_conversation():
    responses = [
        _chat_response(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {
                            "name": "fetch_referenced_file",
                            "arguments": json.dumps({"path": "a"}),
                        },
                    }
                ],
            }
        ),
        _chat_response(
            {"role": "assistant", "content": _valid_json(risk_score=10, category="ninguna")}
        ),
    ]
    client, transport = _local_client(responses)
    calls = []

    def executor(name: str, tool_input: dict) -> str:
        calls.append((name, tool_input))
        return "contenido del fichero"

    output = client.complete_structured(
        "sys",
        "user",
        tools=[{"name": "fetch_referenced_file", "description": "d", "input_schema": {}}],
        tool_executor=executor,
        max_tool_calls=3,
    )

    assert output.risk_score == 10
    assert calls == [("fetch_referenced_file", {"path": "a"})]
    second_payload = json.loads(transport.requests[1].content)
    assert second_payload["messages"][-1]["tool_call_id"] == "call1"


def test_local_forces_final_answer_once_tool_budget_is_exhausted():
    def tool_call_response(call_id: str) -> dict:
        return _chat_response(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": "t", "arguments": "{}"},
                    }
                ],
            }
        )

    final_message = {"role": "assistant", "content": _valid_json(risk_score=0, category="ninguna")}
    responses = [
        tool_call_response("c1"),
        tool_call_response("c2"),
        _chat_response(final_message),
    ]
    client, _ = _local_client(responses)
    calls = []

    output = client.complete_structured(
        "sys",
        "user",
        tools=[{"name": "t", "description": "d", "input_schema": {}}],
        tool_executor=lambda n, i: calls.append((n, i)) or "x",
        max_tool_calls=1,
    )

    assert len(calls) == 1
    assert output.risk_score == 0


def test_local_retries_once_on_invalid_json_then_succeeds():
    responses = [
        _chat_response({"role": "assistant", "content": "esto no es json"}),
        _chat_response(
            {"role": "assistant", "content": _valid_json(risk_score=20, category="ofuscacion")}
        ),
    ]
    client, transport = _local_client(responses)

    output = client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )
    assert output.risk_score == 20
    retry_payload = json.loads(transport.requests[1].content)
    assert "no era JSON válido" in retry_payload["messages"][-1]["content"]


def test_local_raises_instead_of_looping_forever_if_model_keeps_requesting_tools():
    def tool_call_response(call_id: str) -> dict:
        return _chat_response(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": "t", "arguments": "{}"},
                    }
                ],
            }
        )

    responses = [tool_call_response(f"c{i}") for i in range(20)]
    client, transport = _local_client(responses)

    with pytest.raises(SemanticParsingError, match="siguió pidiendo tool calls"):
        client.complete_structured(
            "sys",
            "user",
            tools=[{"name": "t", "description": "d", "input_schema": {}}],
            tool_executor=lambda n, i: "x",
            max_tool_calls=3,
        )

    assert len(transport.requests) == 6


def test_local_survives_malformed_json_in_tool_call_arguments():
    """Modelos locales son menos fiables generando tool calls bien formadas
    que Anthropic/Gemini; unos argumentos que no son JSON válido no deben
    tirar abajo toda la conversación."""
    responses = [
        _chat_response(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "t", "arguments": "{esto no es json"},
                    }
                ],
            }
        ),
        _chat_response(
            {"role": "assistant", "content": _valid_json(risk_score=0, category="ninguna")}
        ),
    ]
    client, _ = _local_client(responses)

    def executor_that_should_not_be_called(name: str, tool_input: dict) -> str:
        raise AssertionError("no debería llamarse: los argumentos no eran JSON válido")

    output = client.complete_structured(
        "sys",
        "user",
        tools=[{"name": "t", "description": "d", "input_schema": {}}],
        tool_executor=executor_that_should_not_be_called,
        max_tool_calls=3,
    )
    assert output.risk_score == 0


def test_local_raises_semantic_parsing_error_after_two_invalid_json_attempts():
    responses = [
        _chat_response({"role": "assistant", "content": "no json"}),
        _chat_response({"role": "assistant", "content": "sigue sin ser json"}),
    ]
    client, _ = _local_client(responses)

    with pytest.raises(SemanticParsingError, match="LLM no devolvió JSON válido tras 2 intentos"):
        client.complete_structured(
            "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
        )


def test_gemini_strips_the_cache_breakpoint_marker_before_sending():
    """Gemini no necesita marcar nada explícito para beneficiarse del bloque
    estático-primero (caché implícita automática de Gemini 2.5) -- pero el
    marcador en sí no debe llegarle nunca como texto literal."""
    system_prompt = build_system_prompt(
        project_type="Python", languages="python", recent_activity_summary="-", rag_context=[]
    )
    fake = _FakeGenaiClient([_gemini_text_response(_valid_json())])
    client = GeminiClient(client=fake)

    client.complete_structured(
        system_prompt, "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    sent_config = fake.models.calls[0]["config"]
    assert _CACHE_BREAKPOINT_MARKER not in sent_config.system_instruction
    assert "Eres un analista de seguridad" in sent_config.system_instruction


def test_local_strips_the_cache_breakpoint_marker_before_sending():
    """Mismo caso que Gemini: vLLM/Ollama/llama.cpp cachean el prefijo de
    KV-cache repetido de forma automática, sin ningún flag ni marcador."""
    system_prompt = build_system_prompt(
        project_type="Python", languages="python", recent_activity_summary="-", rag_context=[]
    )
    client, transport = _local_client(
        [_chat_response({"role": "assistant", "content": _valid_json()})]
    )

    client.complete_structured(
        system_prompt, "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    sent_payload = json.loads(transport.requests[0].content)
    sent_system_message = sent_payload["messages"][0]["content"]
    assert _CACHE_BREAKPOINT_MARKER not in sent_system_message
    assert "Eres un analista de seguridad" in sent_system_message


def test_local_summarize_file_parses_valid_json_response():
    client, _transport = _local_client(
        [
            _chat_response(
                {
                    "role": "assistant",
                    "content": '{"category": "config", "summary": "Config de despliegue."}',
                }
            )
        ]
    )

    result = client.summarize_file("k8s/deploy.yaml", "apiVersion: v1", [])

    assert result.category == "config"
    assert result.summary == "Config de despliegue."


def test_local_summarize_file_degrades_to_unknown_on_malformed_response():
    client, _transport = _local_client(
        [_chat_response({"role": "assistant", "content": "no es JSON"})]
    )

    result = client.summarize_file("weird.txt", "???", [])

    assert result.category == "unknown"
    assert "weird.txt" in result.summary


def test_local_summarize_file_degrades_to_unknown_when_request_fails():
    class _RaisingTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Ollama no está levantado")

    httpx_client = httpx.Client(transport=_RaisingTransport())
    client = OpenAICompatibleClient(
        base_url="http://localhost:11434/v1", model="llama3.1", client=httpx_client
    )

    result = client.summarize_file("x.py", "content", [])

    assert result.category == "unknown"


def test_local_synthesize_text_returns_raw_text():
    client, _transport = _local_client(
        [_chat_response({"role": "assistant", "content": "## Arquitectura\nResumen local."})]
    )

    assert client.synthesize_text("sys", "user") == "## Arquitectura\nResumen local."


def test_local_synthesize_text_returns_empty_on_failure():
    class _RaisingTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Ollama no está levantado")

    httpx_client = httpx.Client(transport=_RaisingTransport())
    client = OpenAICompatibleClient(
        base_url="http://localhost:11434/v1", model="llama3.1", client=httpx_client
    )

    assert client.synthesize_text("sys", "user") == ""
