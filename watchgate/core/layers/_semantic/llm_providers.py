"""Implementaciones adicionales de `LLMClient` (§7.3): Gemini y cualquier
backend que hable el protocolo de chat completions de OpenAI.

`AnthropicClient` (en `client.py`) fue la primera implementación, pero la
interfaz ya estaba pensada para no depender de un único proveedor. Este
módulo añade dos más:

- `GeminiClient`: API cloud de Google, vía el SDK oficial `google-genai`.
- `OpenAICompatibleClient`: no es un proveedor concreto, sino el protocolo
  que hablan Ollama, llama.cpp server, LM Studio y vLLM al servir modelos en
  local -- así se soporta "cualquier modelo local" sin escribir un cliente
  por cada motor de inferencia, apuntando `base_url` a `http://localhost:...`.

Nota sobre `GeminiClient`: los nombres de tipos y campos (`Content`, `Part`,
`FunctionDeclaration`, `FunctionCall.args`, `Models.generate_content(...)`,
etc.) están verificados contra el SDK `google-genai` realmente instalado
(introspección de `model_fields` y firmas), no solo recordados. Lo único que
no se ha podido probar aquí es una llamada de red real (sin credenciales en
este entorno) -- conviene una prueba de humo con una clave real antes de
usarlo en producción.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from watchgate.core.layers._semantic.client import (
    _INVALID_JSON_RETRY_MESSAGE,
    LLMClient,
    SemanticOutput,
    SemanticParsingError,
    ToolExecutor,
    _extract_json_object,
)
from watchgate.core.layers._semantic.tools import FORCE_FINAL_ANSWER_MESSAGE, ToolCallBudget


class GeminiClient(LLMClient):
    """Implementación contra la API de Google Gemini (SDK `google-genai`)."""

    def __init__(self, client: Any = None, model: str = "gemini-2.5-flash") -> None:
        if client is None:
            from google import genai

            client = genai.Client(api_key=os.environ.get("WATCHGATE_LLM_API_KEY"))
        self._client = client
        self._model = model

    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_executor: ToolExecutor,
        max_tool_calls: int,
    ) -> SemanticOutput:
        from google.genai import types

        budget = ToolCallBudget(max_calls=max_tool_calls)
        contents: list[Any] = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]
        gemini_tools = self._build_tools(tools)

        max_turns = max_tool_calls + 3
        for _ in range(max_turns):
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=gemini_tools if not budget.exhausted else [],
                ),
            )
            # A diferencia de AnthropicClient (itera response.content, que si
            # llega vacío da una lista vacía, no un error), Gemini puede
            # devolver `candidates` vacío -- p. ej. si sus propios filtros de
            # seguridad bloquean la respuesta. Indexar [0] a pelo ahí
            # reventaba con IndexError, que safe_analyze() sí captura, pero
            # como una excepción genérica sin contexto útil en skip_reason.
            if not response.candidates:
                block_reason = getattr(response, "prompt_feedback", None)
                raise SemanticParsingError(
                    f"Gemini no devolvió ningún candidate (prompt_feedback={block_reason!r})."
                )
            parts = response.candidates[0].content.parts
            function_calls = [p for p in parts if getattr(p, "function_call", None)]

            if not function_calls:
                text = "".join(p.text for p in parts if getattr(p, "text", None))
                return self._parse_with_retry(system_prompt, contents, text)

            contents.append(response.candidates[0].content)
            response_parts = []
            for part in function_calls:
                call = part.function_call
                if budget.exhausted:
                    response_parts.append(
                        _function_response_part(types, call.name, FORCE_FINAL_ANSWER_MESSAGE)
                    )
                    continue
                result = tool_executor(call.name, dict(call.args or {}))
                budget.record_call()
                response_parts.append(_function_response_part(types, call.name, result))
            contents.append(types.Content(role="user", parts=response_parts))

        raise SemanticParsingError(
            f"El LLM siguió pidiendo tool calls tras {max_turns} turnos sin llegar a "
            "una respuesta final; se corta para evitar un bucle sin fin."
        )

    @staticmethod
    def _build_tools(tools: list[dict[str, Any]]) -> list[Any]:
        if not tools:
            return []
        from google.genai import types

        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool["description"],
                        parameters=tool["input_schema"],
                    )
                    for tool in tools
                ]
            )
        ]

    def _parse_with_retry(
        self, system_prompt: str, contents: list[Any], text: str
    ) -> SemanticOutput:
        from google.genai import types

        try:
            return SemanticOutput.model_validate(_extract_json_object(text))
        except (ValueError, json.JSONDecodeError):
            pass

        retry_contents = [
            *contents,
            types.Content(role="model", parts=[types.Part(text=text)]),
            types.Content(role="user", parts=[types.Part(text=_INVALID_JSON_RETRY_MESSAGE)]),
        ]
        retry_response = self._client.models.generate_content(
            model=self._model,
            contents=retry_contents,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        if not retry_response.candidates:
            block_reason = getattr(retry_response, "prompt_feedback", None)
            raise SemanticParsingError(
                f"Gemini no devolvió ningún candidate en el reintento "
                f"(prompt_feedback={block_reason!r})."
            )
        retry_parts = retry_response.candidates[0].content.parts
        retry_text = "".join(p.text for p in retry_parts if getattr(p, "text", None))
        try:
            return SemanticOutput.model_validate(_extract_json_object(retry_text))
        except (ValueError, json.JSONDecodeError) as exc:
            raise SemanticParsingError("LLM no devolvió JSON válido tras 2 intentos") from exc


def _function_response_part(types: Any, name: str, result: Any) -> Any:
    payload = result if isinstance(result, dict) else {"result": result}
    return types.Part(function_response=types.FunctionResponse(name=name, response=payload))


class OpenAICompatibleClient(LLMClient):
    """Cualquier backend que hable el protocolo de chat completions de
    OpenAI: Ollama, llama.cpp server, LM Studio, vLLM... Pensado para
    modelos locales, sin depender de un SDK propietario ni de una cloud
    concreta -- basta con apuntar `base_url` al servidor correspondiente."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_executor: ToolExecutor,
        max_tool_calls: int,
    ) -> SemanticOutput:
        budget = ToolCallBudget(max_calls=max_tool_calls)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

        max_turns = max_tool_calls + 3
        for _ in range(max_turns):
            message = self._chat(messages, openai_tools if not budget.exhausted else [])
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                return self._parse_with_retry(messages, message.get("content") or "")

            messages.append(
                {"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls}
            )
            for call in tool_calls:
                function = call["function"]
                if budget.exhausted:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": FORCE_FINAL_ANSWER_MESSAGE,
                        }
                    )
                    continue
                try:
                    arguments = (
                        json.loads(function["arguments"]) if function.get("arguments") else {}
                    )
                except json.JSONDecodeError:
                    # Modelos locales son menos fiables generando tool calls bien
                    # formadas que Anthropic/Gemini; un JSON inválido aquí no debe
                    # tirar abajo toda la conversación (mismo criterio que el
                    # dispatcher de layer.py para argumentos mal formados).
                    budget.record_call()
                    bad_args = function.get("arguments")
                    error_payload = {"error": f"argumentos no son JSON válido: {bad_args!r}"}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(error_payload),
                        }
                    )
                    continue
                result = tool_executor(function["name"], arguments)
                budget.record_call()
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)}
                )

        raise SemanticParsingError(
            f"El LLM siguió pidiendo tool calls tras {max_turns} turnos sin llegar a "
            "una respuesta final; se corta para evitar un bucle sin fin."
        )

    def _chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self._model, "messages": messages}
        if tools:
            payload["tools"] = tools
        response = self._client.post(f"{self._base_url}/chat/completions", json=payload)
        response.raise_for_status()
        message: dict[str, Any] = response.json()["choices"][0]["message"]
        return message

    def _parse_with_retry(self, messages: list[dict[str, Any]], text: str) -> SemanticOutput:
        try:
            return SemanticOutput.model_validate(_extract_json_object(text))
        except (ValueError, json.JSONDecodeError):
            pass

        retry_messages = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": _INVALID_JSON_RETRY_MESSAGE},
        ]
        retry_message = self._chat(retry_messages, [])
        retry_text = retry_message.get("content") or ""
        try:
            return SemanticOutput.model_validate(_extract_json_object(retry_text))
        except (ValueError, json.JSONDecodeError) as exc:
            raise SemanticParsingError("LLM no devolvió JSON válido tras 2 intentos") from exc
