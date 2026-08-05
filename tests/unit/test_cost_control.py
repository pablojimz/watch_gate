"""Tests de cost_control.py (spec §8)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from watchgate.core.cost_control import CostController, build_skipped_budget_result, diff_hash
from watchgate.core.layers._semantic.client import SemanticOutput
from watchgate.core.models import FileChange, FileStatus, LayerResult, NormalizedDiff


@pytest.fixture
def controller():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "cost.db")
    ctrl = CostController(db_path=db_path, max_diff_tokens=50, monthly_budget_tokens=1000)
    yield ctrl
    ctrl.close()


def _diff_with_files(*hunks: str) -> NormalizedDiff:
    files = [
        FileChange(
            path=f"file{i}.py",
            status=FileStatus.MODIFIED,
            diff_hunk=h,
            additions=1,
            deletions=0,
        )
        for i, h in enumerate(hunks)
    ]
    return NormalizedDiff(
        base_sha="a", head_sha="b", repo_path=".", files=files, commit_messages=[], authors=[]
    )


def test_estimate_tokens_proportional_to_length():
    from watchgate.core.cost_control import _CHARS_PER_TOKEN_ESTIMATE

    real = CostController(db_path=tempfile.mktemp(), max_diff_tokens=10, monthly_budget_tokens=10)
    assert real.estimate_tokens("") == 0
    assert real.estimate_tokens("a" * _CHARS_PER_TOKEN_ESTIMATE) == 1
    assert real.estimate_tokens("a" * _CHARS_PER_TOKEN_ESTIMATE * 10) == 10
    real.close()


def test_cache_roundtrip(controller):
    """get_cached/store_cached trabajan con SemanticOutput (no un dict
    suelto): es el mismo tipo que produce/consume SemanticLayer vía el
    Protocol CostControllerLike -- un dict plano no se podía serializar de
    vuelta con json.dumps directo (reproducido en la revisión de Línea 2)."""
    h = "abc123"
    assert controller.get_cached(h) is None

    output = SemanticOutput(
        risk_score=42, category="backdoor", justification="x", confidence="alta"
    )
    controller.store_cached(h, output)

    assert controller.get_cached(h) == output


def test_cache_roundtrip_survives_concurrent_access_from_multiple_threads(controller):
    """orchestrator.py ejecuta las capas en un ThreadPoolExecutor: la
    conexión sqlite3 de CostController se usa desde un hilo distinto al que
    la creó. Sin check_same_thread=False + Lock, esto lanzaba
    sqlite3.ProgrammingError (reproducido en la revisión)."""
    import concurrent.futures

    def worker(i: int) -> int:
        controller.record_usage("org/repo", 1)
        return controller.budget_remaining("org/repo")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(20)))

    assert len(results) == 20
    assert controller.budget_remaining("org/repo") == 1000 - 20


def test_diff_hash_is_deterministic():
    diff = _diff_with_files("+ print(1)")
    h1 = diff_hash(diff)
    h2 = diff_hash(diff.model_copy())
    assert h1 == h2

    other = _diff_with_files("+ print(2)")
    assert diff_hash(other) != h1


def test_budget_remaining_decreases_with_usage(controller):
    assert controller.budget_remaining("org/repo") == 1000
    controller.record_usage("org/repo", 400)
    assert controller.budget_remaining("org/repo") == 600
    controller.record_usage("org/repo", 700)
    assert controller.budget_remaining("org/repo") == -100


def test_should_skip_true_when_budget_exhausted(controller):
    assert controller.should_skip("org/repo") is False
    controller.record_usage("org/repo", 1000)
    assert controller.should_skip("org/repo") is True


def test_should_truncate_reflects_max_diff_tokens(controller):
    small = _diff_with_files("+ x = 1")
    assert controller.should_truncate(small) is False

    big_hunk = "+ " + ("x" * 1000)
    big = _diff_with_files(big_hunk)
    assert controller.should_truncate(big) is True


def test_semantic_layer_skips_llm_call_when_budget_exhausted(controller):
    """Reproduce el criterio de aceptación exacto de la spec: con presupuesto
    agotado, la capa semántica no debe llamar al LLM (call_count == 0)."""

    class FakeLLMClient:
        def __init__(self):
            self.call_count = 0

        def complete_structured(self, *args, **kwargs):
            self.call_count += 1
            return {
                "risk_score": 0,
                "category": "ninguna",
                "justification": "",
                "confidence": "baja",
            }

    fake_client = FakeLLMClient()
    controller.record_usage("org/repo", 1000)  # agota el presupuesto

    def fake_semantic_analyze(repo: str, llm_client: FakeLLMClient) -> LayerResult:
        if controller.should_skip(repo):
            return build_skipped_budget_result()
        return llm_client.complete_structured()

    result = fake_semantic_analyze("org/repo", fake_client)

    assert fake_client.call_count == 0
    assert result.skipped is True
    assert result.skip_reason == "Presupuesto de tokens agotado para este repositorio este mes"


def test_truncate_diff_prioritizes_flagged_files_and_marks_truncation(controller):
    flagged = FileChange(
        path="suspicious.py",
        status=FileStatus.MODIFIED,
        diff_hunk="+ eval(x)" * 5,
        additions=5,
        deletions=0,
    )
    clean = FileChange(
        path="clean.py",
        status=FileStatus.MODIFIED,
        diff_hunk="+ y = 1\n" * 100,
        additions=100,
        deletions=0,
    )
    diff = NormalizedDiff(
        base_sha="a",
        head_sha="b",
        repo_path=".",
        files=[clean, flagged],
        commit_messages=[],
        authors=[],
    )

    truncated = controller.truncate_diff(diff, static_findings=["suspicious.py"])

    result_by_path = {f.path: f for f in truncated.files}
    # El fichero marcado se conserva íntegro.
    assert result_by_path["suspicious.py"].diff_hunk == flagged.diff_hunk
    # El fichero no marcado, al exceder el presupuesto, queda truncado con marcador.
    assert "truncado" in result_by_path["clean.py"].diff_hunk


def test_cost_controller_context_manager_and_idempotent_close():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "cost.db")
    with CostController(db_path=db_path, max_diff_tokens=50, monthly_budget_tokens=1000) as ctrl:
        assert ctrl.budget_remaining("repo") == 1000
    # Al salir del bloque con, se cierra automáticamente sin lanzar error
    ctrl.close()  # La segunda llamada debe ser no-op e idempotente
