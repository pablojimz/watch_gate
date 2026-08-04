"""SemanticLayer — orquesta prompting/tools/client/RAG (§7.5).

`cost_control` se recibe como un `CostControllerLike` (Protocol estructural):
esta capa no importa `watchgate.core.cost_control` directamente, así que es
testeable con un fake y se integra con la implementación real de esa pieza
(§8) sin cambiar una línea aquí — solo pasando la instancia real al
constructor.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from watchgate.core.layers._semantic import prompting, tools
from watchgate.core.layers._semantic.client import (
    LLMClient,
    SemanticOutput,
    SemanticParsingError,
    ToolExecutor,
)
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import LayerResult, NormalizedDiff
from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH
from watchgate.core.rag.retriever import retrieve_relevant_context

_MAX_TOOL_CALLS = 3
_NO_BUDGET_SKIP_REASON = "Presupuesto de tokens agotado para este repositorio este mes"


class CostControllerLike(Protocol):
    """Subconjunto de watchgate/core/cost_control.py (§8) que necesita esta
    capa. Al ser un Protocol, la implementación real de esa pieza no
    necesita heredar de aquí: basta con exponer estos métodos."""

    def budget_remaining(self, repo: str) -> int: ...
    def estimate_tokens(self, text: str) -> int: ...
    def get_cached(self, diff_hash: str) -> SemanticOutput | None: ...
    def store_cached(self, diff_hash: str, output: SemanticOutput) -> None: ...
    def record_usage(self, repo: str, tokens_used: int) -> None: ...


def compute_diff_hash(diff: NormalizedDiff) -> str:
    """Determinista: el mismo diff exacto produce el mismo hash (§8)."""
    return hashlib.sha256(
        json.dumps(diff.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


class _ToolCallCounter:
    def __init__(self) -> None:
        self.count = 0


def _dispatch_tool(
    name: str, tool_input: dict[str, Any], diff: NormalizedDiff, metadata: dict[str, Any]
) -> Any:
    if name == "lookup_package_registry":
        return tools.lookup_package_registry(**tool_input)
    if name == "fetch_referenced_file":
        return tools.fetch_referenced_file(
            path=tool_input["path"], ref=tool_input["ref"], repo_path=diff.repo_path
        )
    if name == "check_file_reputation":
        return tools.check_file_reputation(
            path=tool_input["path"], ref=tool_input["ref"], repo_path=diff.repo_path
        )
    if name == "get_commit_history":
        fetch_commit_history = metadata.get("fetch_commit_history_callback")
        if fetch_commit_history is None:
            return {"error": "get_commit_history no disponible: sin adaptador inyectado"}
        tool = tools.make_get_commit_history_tool(fetch_commit_history)
        return tool(tool_input["author_login"], tool_input["repo"])
    return {"error": f"tool desconocida: {name}"}


def _build_tool_executor(
    diff: NormalizedDiff, metadata: dict[str, Any], counter: _ToolCallCounter
) -> ToolExecutor:
    def executor(name: str, tool_input: dict[str, Any]) -> Any:
        counter.count += 1
        try:
            return _dispatch_tool(name, tool_input, diff, metadata)
        except Exception as exc:  # noqa: BLE001 - un tool_call con argumentos
            # mal formados (o cualquier fallo interno de una tool) no debe
            # tirar abajo toda la conversación con el LLM; se le devuelve el
            # error como resultado de la tool, igual que haría un fallo de red.
            return {"error": f"fallo ejecutando la tool {name!r}: {exc!r}"}

    return executor


def _diff_summary(diff: NormalizedDiff) -> str:
    return "\n".join(f"{fc.path}: {fc.diff_hunk[:200]}" for fc in diff.files)


@register_layer
class SemanticLayer(AnalysisLayer):
    name = "semantic"

    def __init__(
        self,
        llm_client: LLMClient,
        cost_control: CostControllerLike,
        max_diff_tokens: int = 6000,
        project_type: str = "desconocido",
        languages: str = "desconocido",
        recent_activity_summary: str = "sin datos",
        rag_index_path: str = DEFAULT_INDEX_PATH,
    ) -> None:
        self._llm_client = llm_client
        self._cost_control = cost_control
        self._max_diff_tokens = max_diff_tokens
        self._project_type = project_type
        self._languages = languages
        self._recent_activity_summary = recent_activity_summary
        self._rag_index_path = rag_index_path

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        repo = str(metadata.get("repo", ""))

        if self._cost_control.budget_remaining(repo) <= 0:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=_NO_BUDGET_SKIP_REASON,
            )

        diff_hash = compute_diff_hash(diff)
        cached = self._cost_control.get_cached(diff_hash)
        if cached is not None:
            return self._to_layer_result(cached, tool_calls_made=0)

        static_findings_paths: set[str] = set(metadata.get("static_findings_paths", set()))
        rag_context = retrieve_relevant_context(
            _diff_summary(diff), index_path=self._rag_index_path
        )
        dependency_findings = tools.gather_dependency_findings(diff)

        system_prompt = prompting.build_system_prompt(
            self._project_type,
            self._languages,
            self._recent_activity_summary,
            rag_context,
            dependency_findings=dependency_findings,
        )
        user_prompt = prompting.build_user_prompt(
            diff, static_findings_paths, self._cost_control.estimate_tokens, self._max_diff_tokens
        )

        counter = _ToolCallCounter()
        tool_executor = _build_tool_executor(diff, metadata, counter)

        try:
            output = self._llm_client.complete_structured(
                system_prompt,
                user_prompt,
                tools=tools.build_tool_schemas(),
                tool_executor=tool_executor,
                max_tool_calls=_MAX_TOOL_CALLS,
            )
        except SemanticParsingError as exc:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=str(exc),
            )

        self._cost_control.store_cached(diff_hash, output)
        # Nota: esto estima el coste de la petición inicial (system + user
        # prompt), pero no puede contabilizar las idas y vueltas de tool-calls
        # ni los tokens de salida del modelo, porque LLMClient.complete_structured
        # no expone el consumo real de la conversación (§7.3/§8 no lo definen).
        # Subestima el uso real cuando hay tool calls; documentado para quien
        # integre cost_control.py de verdad.
        estimated_tokens = self._cost_control.estimate_tokens(
            system_prompt
        ) + self._cost_control.estimate_tokens(user_prompt)
        self._cost_control.record_usage(repo, estimated_tokens)
        return self._to_layer_result(output, tool_calls_made=counter.count)

    def _to_layer_result(self, output: SemanticOutput, tool_calls_made: int) -> LayerResult:
        return LayerResult(
            layer_name=self.name,
            risk_score=output.risk_score,
            justification=output.justification,
            category=output.category,
            confidence=output.confidence,
            tool_calls_made=tool_calls_made,
        )
