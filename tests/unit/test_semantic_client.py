"""Tests de watchgate/core/layers/_semantic/client.py (spec §7.3)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from watchgate.core.layers._semantic.client import (
    _INVALID_JSON_RETRY_MESSAGE,
    AnthropicClient,
    SemanticParsingError,
)
from watchgate.core.layers._semantic.prompting import (
    _CACHE_BREAKPOINT_MARKER,
    build_system_prompt,
)
from watchgate.core.layers._semantic.tools import FORCE_FINAL_ANSWER_MESSAGE
from watchgate.core.models import Confidence, RiskCategory


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name: str, tool_input: dict, id_: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=id_)


def _response(*blocks: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks))


class _FakeMessages:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = iter(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return next(self._responses)


class _FakeAnthropic:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.messages = _FakeMessages(responses)


def _valid_json(**overrides: object) -> str:
    payload = {
        "risk_score": 85,
        "category": "backdoor",
        "justification": "x",
        "confidence": "alta",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_returns_output_when_llm_answers_directly_with_valid_json():
    fake = _FakeAnthropic([_response(_text_block(_valid_json()))])
    client = AnthropicClient(client=fake)

    output = client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    assert output.risk_score == 85
    assert output.category == RiskCategory.BACKDOOR
    assert output.confidence == Confidence.ALTA


def test_extracts_json_even_when_wrapped_in_markdown_fences_or_prose():
    """Aunque se le pida responder solo con JSON, es habitual que el modelo
    lo envuelva en ```json ... ``` o añada una frase alrededor."""
    wrapped = f"```json\n{_valid_json(risk_score=42, category='ofuscacion')}\n```"
    fake = _FakeAnthropic([_response(_text_block(wrapped))])
    client = AnthropicClient(client=fake)

    output = client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    assert output.risk_score == 42
    assert output.category == RiskCategory.OFUSCACION


def test_executes_tool_and_continues_the_conversation():
    tool_response = _response(_tool_use_block("fetch_referenced_file", {"path": "a"}, "call1"))
    final_response = _response(_text_block(_valid_json(risk_score=10, category="ninguna")))
    fake = _FakeAnthropic([tool_response, final_response])

    calls = []

    def executor(name: str, tool_input: dict) -> str:
        calls.append((name, tool_input))
        return "contenido del fichero"

    client = AnthropicClient(client=fake)
    output = client.complete_structured(
        "sys",
        "user",
        tools=[{"name": "fetch_referenced_file"}],
        tool_executor=executor,
        max_tool_calls=3,
    )

    assert output.risk_score == 10
    assert calls == [("fetch_referenced_file", {"path": "a"})]
    second_call_messages = fake.messages.calls[1]["messages"]
    assert second_call_messages[-1]["content"][0]["tool_use_id"] == "call1"


def test_forces_final_answer_once_tool_budget_is_exhausted():
    responses = [
        _response(_tool_use_block("t", {}, "c1")),
        _response(_tool_use_block("t", {}, "c2")),
        _response(_text_block(_valid_json(risk_score=0, category="ninguna"))),
    ]
    fake = _FakeAnthropic(responses)
    calls = []

    def executor(name: str, tool_input: dict) -> str:
        calls.append((name, tool_input))
        return "x"

    client = AnthropicClient(client=fake)
    output = client.complete_structured(
        "sys", "user", tools=[{"name": "t"}], tool_executor=executor, max_tool_calls=1
    )

    assert len(calls) == 1  # solo la primera tool call se ejecuta de verdad
    assert output.risk_score == 0


def test_forces_final_answer_within_a_single_response_with_parallel_tool_calls():
    """Caso distinto al anterior: dos tool_use en la MISMA respuesta (llamadas
    en paralelo), no en respuestas separadas. El presupuesto debe agotarse
    a mitad del propio bucle sobre los bloques de esa respuesta."""
    responses = [
        _response(
            _tool_use_block("t", {}, "c1"),
            _tool_use_block("t", {}, "c2"),
        ),
        _response(_text_block(_valid_json(risk_score=0, category="ninguna"))),
    ]
    fake = _FakeAnthropic(responses)
    calls = []

    def executor(name: str, tool_input: dict) -> str:
        calls.append((name, tool_input))
        return "x"

    client = AnthropicClient(client=fake)
    output = client.complete_structured(
        "sys", "user", tools=[{"name": "t"}], tool_executor=executor, max_tool_calls=1
    )

    assert len(calls) == 1  # solo la primera de las dos tool_use paralelas se ejecuta
    assert output.risk_score == 0
    tool_results = fake.messages.calls[1]["messages"][-1]["content"]
    assert tool_results[0]["content"] == json.dumps("x")
    assert tool_results[1]["content"] == FORCE_FINAL_ANSWER_MESSAGE


def test_retries_once_on_invalid_json_then_succeeds():
    bad = _response(_text_block("esto no es json"))
    good = _response(_text_block(_valid_json(risk_score=20, category="ofuscacion")))
    fake = _FakeAnthropic([bad, good])

    client = AnthropicClient(client=fake)
    output = client.complete_structured(
        "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    assert output.risk_score == 20
    retry_messages = fake.messages.calls[1]["messages"]
    assert retry_messages[-1]["content"] == _INVALID_JSON_RETRY_MESSAGE


def test_raises_semantic_parsing_error_after_two_invalid_json_attempts():
    fake = _FakeAnthropic(
        [_response(_text_block("no json")), _response(_text_block("sigue sin ser json"))]
    )
    client = AnthropicClient(client=fake)

    with pytest.raises(SemanticParsingError, match="LLM no devolvió JSON válido tras 2 intentos"):
        client.complete_structured(
            "sys", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
        )


def test_raises_instead_of_looping_forever_if_model_keeps_requesting_tools():
    """Caso adversarial: el modelo sigue pidiendo tool_use incluso después de
    agotado el presupuesto (tools=[] ya no debería provocarlo, pero un fallo
    del proveedor o un modelo mal comportado podría hacerlo). Debe cortar con
    un error controlado, no colgarse ni disparar llamadas sin límite."""
    fake = _FakeAnthropic([_response(_tool_use_block("t", {}, f"c{i}")) for i in range(20)])
    client = AnthropicClient(client=fake)

    with pytest.raises(SemanticParsingError, match="siguió pidiendo tool_use"):
        client.complete_structured(
            "sys", "user", tools=[{"name": "t"}], tool_executor=lambda n, i: "x", max_tool_calls=3
        )

    # exactamente max_tool_calls + 3 turnos, no un número sin acotar
    assert len(fake.messages.calls) == 6


def test_system_prompt_with_cache_marker_is_sent_as_two_blocks_with_cache_control():
    """Optimización de coste: el prompt real de `build_system_prompt()` lleva
    el marcador de `_CACHE_BREAKPOINT_MARKER` entre el bloque estático
    (instrucciones + few-shot) y el variable (fecha/RAG/contexto). Anthropic
    exige marcar `cache_control` explícitamente por bloque -- sin este split,
    no se cachea nada."""
    system_prompt = build_system_prompt(
        project_type="Python", languages="python", recent_activity_summary="-", rag_context=[]
    )
    fake = _FakeAnthropic([_response(_text_block(_valid_json()))])
    client = AnthropicClient(client=fake)

    client.complete_structured(
        system_prompt, "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    sent_system = fake.messages.calls[0]["system"]
    assert isinstance(sent_system, list)
    assert len(sent_system) == 2
    assert sent_system[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in sent_system[1]
    # El bloque cacheado es justo la parte estática -- nunca contiene el
    # marcador en sí, y el bloque variable no lleva las instrucciones fijas.
    assert _CACHE_BREAKPOINT_MARKER not in sent_system[0]["text"]
    assert _CACHE_BREAKPOINT_MARKER not in sent_system[1]["text"]
    assert "Eres un analista de seguridad" in sent_system[0]["text"]


def test_system_prompt_without_cache_marker_is_sent_as_a_plain_string():
    """Sin el marcador (un `system_prompt` a mano, como en el resto de tests
    de este fichero) el comportamiento es exactamente el de antes -- un
    string plano, sin ningún bloque de caché."""
    fake = _FakeAnthropic([_response(_text_block(_valid_json()))])
    client = AnthropicClient(client=fake)

    client.complete_structured(
        "sys sin marcador", "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    assert fake.messages.calls[0]["system"] == "sys sin marcador"


def test_cache_control_block_reused_on_the_invalid_json_retry_call():
    """La segunda llamada (reintento tras JSON inválido) debe usar el mismo
    `system` ya troceado -- no reconstruirlo ni, peor, mandar el marcador
    crudo sin trocear en el reintento."""
    system_prompt = build_system_prompt(
        project_type="Python", languages="python", recent_activity_summary="-", rag_context=[]
    )
    bad = _response(_text_block("no es json"))
    good = _response(_text_block(_valid_json(risk_score=20, category="ofuscacion")))
    fake = _FakeAnthropic([bad, good])
    client = AnthropicClient(client=fake)

    client.complete_structured(
        system_prompt, "user", tools=[], tool_executor=lambda n, i: None, max_tool_calls=3
    )

    assert fake.messages.calls[0]["system"] == fake.messages.calls[1]["system"]
