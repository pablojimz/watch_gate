"""Cliente del proveedor LLM — interfaz + implementación (§7.3).

`DECISIÓN HUMANA` ya tomada: Anthropic como proveedor inicial. `LLMClient`
es la interfaz que permite sustituirlo (OpenAI, Ollama...) sin tocar el
resto de la capa semántica (A.0.0 aplicado también aquí).

Nota de diseño respecto al pseudocódigo de la spec: la firma de
`complete_structured` añade un parámetro `tool_executor` que no aparece en el
esqueleto de la spec. Sin él, el cliente no tendría forma de *ejecutar* las
tools durante la conversación con el LLM (la spec solo le pasa los
esquemas JSON, no las funciones); `tool_executor(name, tool_input)` es quien
las despacha, y lo construye `layer.py` con acceso a los callables reales.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from watchgate.core.layers._semantic.tools import FORCE_FINAL_ANSWER_MESSAGE, ToolCallBudget
from watchgate.core.models import Confidence, RiskCategory

ToolExecutor = Callable[[str, dict[str, Any]], Any]

_INVALID_JSON_RETRY_MESSAGE = "Tu respuesta anterior no era JSON válido. Responde solo con el JSON."


class SemanticOutput(BaseModel):
    """Esquema exacto de §7.1."""

    risk_score: int = Field(ge=0, le=100)
    category: RiskCategory
    justification: str
    confidence: Confidence


class SemanticParsingError(Exception):
    """El LLM no devolvió JSON válido tras los dos intentos permitidos."""


class LLMClient(ABC):
    @abstractmethod
    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_executor: ToolExecutor,
        max_tool_calls: int,
    ) -> SemanticOutput:
        """Debe devolver un SemanticOutput válido, o lanzar
        SemanticParsingError si el modelo no devuelve JSON válido tras 2
        intentos."""


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extrae el primer objeto JSON de un texto, por si el modelo añade texto
    alrededor a pesar de la instrucción de responder solo con JSON."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No se encontró ningún objeto JSON en la respuesta.")
    candidate: dict[str, Any] = json.loads(text[start : end + 1])
    return candidate


class AnthropicClient(LLMClient):
    """Implementación concreta inicial contra la API de Anthropic."""

    def __init__(self, client: Any = None, model: str = "claude-sonnet-5") -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=os.environ.get("WATCHGATE_LLM_API_KEY"))
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
        budget = ToolCallBudget(max_calls=max_tool_calls)
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]

        # Tope duro de turnos, independiente del presupuesto de tool calls: si
        # el modelo sigue pidiendo tool_use incluso después de agotado el
        # presupuesto (tools=[] ya no debería provocarlo, pero un modelo con
        # comportamiento adversarial o un fallo del proveedor podría hacerlo
        # de todos modos), esto evita un bucle sin fin y un gasto descontrolado
        # de llamadas a la API.
        max_turns = max_tool_calls + 3
        for _ in range(max_turns):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
                tools=tools if not budget.exhausted else [],
            )
            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

            if not tool_use_blocks:
                text = "".join(block.text for block in response.content if block.type == "text")
                return self._parse_with_retry(system_prompt, messages, text)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_use_blocks:
                if budget.exhausted:
                    # La spec dice "mensaje de sistema adicional", pero la API de
                    # Anthropic no admite turnos de rol "system" intercalados en la
                    # conversación, y todo tool_use debe llevar su tool_result
                    # correspondiente. Se entrega como contenido del tool_result.
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": FORCE_FINAL_ANSWER_MESSAGE,
                        }
                    )
                    continue
                result = tool_executor(block.name, block.input)
                budget.record_call()
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
                )
            messages.append({"role": "user", "content": tool_results})

        raise SemanticParsingError(
            f"El LLM siguió pidiendo tool_use tras {max_turns} turnos sin llegar a "
            "una respuesta final; se corta para evitar un bucle sin fin."
        )

    def _parse_with_retry(
        self, system_prompt: str, messages: list[dict[str, Any]], text: str
    ) -> SemanticOutput:
        try:
            return SemanticOutput.model_validate(_extract_json_object(text))
        except (ValueError, json.JSONDecodeError):
            pass

        retry_messages = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": _INVALID_JSON_RETRY_MESSAGE},
        ]
        retry_response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=retry_messages,
        )
        retry_text = "".join(block.text for block in retry_response.content if block.type == "text")
        try:
            return SemanticOutput.model_validate(_extract_json_object(retry_text))
        except (ValueError, json.JSONDecodeError) as exc:
            raise SemanticParsingError("LLM no devolvió JSON válido tras 2 intentos") from exc
