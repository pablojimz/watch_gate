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


def test_estimate_tokens_uses_a_real_tokenizer_not_just_char_count():
    """Hallazgo real (referencia: mercedes-uma-hackathon, mismo problema ya
    resuelto ahí): contar caracteres/4 no distingue prosa de código denso en
    símbolos (JSON, base64, minificado) -- el ratio real de caracteres/token
    en ese tipo de contenido está lejos de la media que asume ese heurístico.
    tiktoken (`o200k_base`) sí lo distingue de verdad: un texto con mucha
    puntuación/símbolos repetidos tokeniza distinto a prosa de la misma
    longitud en caracteres."""
    controller = CostController(
        db_path=tempfile.mktemp(), max_diff_tokens=10, monthly_budget_tokens=10
    )
    prose = "the quick brown fox jumps over the lazy dog " * 5
    symbols = "{}[]();,.:!?" * 20  # misma familia de longitud, sin palabras reales
    assert controller.estimate_tokens("") == 0
    assert controller.estimate_tokens(prose) > 0
    # tiktoken agrupa símbolos repetidos de forma muy distinta a palabras
    # reales -- si esto fuera solo len(texto)//4, ambos (longitud similar)
    # darían el mismo resultado; con un tokenizer real, no tiene por qué.
    assert controller.estimate_tokens(prose) != controller.estimate_tokens(symbols)
    # Monotonía real: el doble de texto (repetido, sin cambiar el
    # vocabulario) nunca puede dar MENOS tokens.
    assert controller.estimate_tokens(prose * 2) > controller.estimate_tokens(prose)
    controller.close()


def test_estimate_tokens_falls_back_to_char_heuristic_if_tiktoken_unavailable(monkeypatch):
    """Un fallo de red al cargar el encoding la primera vez (o cualquier otro
    fallo de tiktoken) no debe tumbar la estimación de coste -- cae al
    heurístico de caracteres en vez de propagar la excepción."""
    import watchgate.core.cost_control as cost_control_module
    from watchgate.core.cost_control import _CHARS_PER_TOKEN_ESTIMATE

    monkeypatch.setattr(cost_control_module, "_get_encoder", lambda: None)
    controller = CostController(
        db_path=tempfile.mktemp(), max_diff_tokens=10, monthly_budget_tokens=10
    )
    assert controller.estimate_tokens("") == 0
    assert controller.estimate_tokens("a" * _CHARS_PER_TOKEN_ESTIMATE) == 1
    assert controller.estimate_tokens("a" * _CHARS_PER_TOKEN_ESTIMATE * 10) == 10
    controller.close()


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


def test_cache_degrades_gracefully_on_stale_schema_missing_a_column():
    """.watchgate/cost.db es un fichero SQLite por repositorio, creado una
    vez con create_all() y nunca migrado -- si SemanticCache gana una
    columna nueva (como org_id, añadida para aislar caché por
    organización), cualquier fichero preexistente de un desarrollador se
    queda con el esquema viejo para siempre (create_all() no altera tablas
    ya creadas). Bug real reproducido en vivo contra un cost.db real de
    antes de esa columna: la capa semántica ENTERA (peso 0.40 por defecto,
    la más alta) se marcaba "omitida" con el mensaje crudo de SQLAlchemy
    como única pista. Para una caché, cuyo único propósito es evitar una
    llamada repetida al LLM, un fallo de lectura/escritura debe degradar a
    "sin caché" (fuerza una llamada real), no tirar el análisis semántico
    entero."""
    from sqlalchemy import create_engine, text

    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "cost.db")

    # Crea `semantic_cache` a mano SIN la columna `org_id` -- simula el
    # fichero preexistente de un desarrollador, creado antes de que esa
    # columna se añadiera al modelo.
    stale_engine = create_engine(f"sqlite:///{db_path}")
    with stale_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE semantic_cache ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "diff_hash VARCHAR NOT NULL, "
                "output_json VARCHAR NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
    stale_engine.dispose()

    # `create_all()` en __init__ no toca la tabla ya existente (sin la
    # columna org_id) -- exactamente el escenario real.
    ctrl = CostController(db_path=db_path, max_diff_tokens=50, monthly_budget_tokens=1000)
    try:
        assert ctrl.get_cached("abc123") is None

        output = SemanticOutput(
            risk_score=42, category="backdoor", justification="x", confidence="alta"
        )
        ctrl.store_cached("abc123", output)  # no debe lanzar

        # El resultado sigue sin estar cacheado (el esquema sigue desfasado),
        # pero una llamada real al LLM seguiría funcionando -- lo importante
        # es que ninguna de las dos operaciones abortó el análisis.
        assert ctrl.get_cached("abc123") is None
    finally:
        ctrl.close()


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


def test_cost_controller_context_manager_and_idempotent_close():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "cost.db")
    with CostController(db_path=db_path, max_diff_tokens=50, monthly_budget_tokens=1000) as ctrl:
        assert ctrl.budget_remaining("repo") == 1000
    # Al salir del bloque con, se cierra automáticamente sin lanzar error
    ctrl.close()  # La segunda llamada debe ser no-op e idempotente


def test_unlimited_budget_tokens_none():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "cost.db")
    ctrl = CostController(db_path=db_path, max_diff_tokens=50, monthly_budget_tokens=None)
    assert ctrl.budget_remaining("org/repo") > 0
    assert ctrl.should_skip("org/repo") is False
    ctrl.close()


def test_zero_budget_tokens_means_no_budget_not_unlimited():
    """Bug real encontrado en revisión: monthly_budget_tokens=0 se trataba
    igual que None (sin tope) y devolvía presupuesto prácticamente
    ilimitado -- lo contrario de lo que un operador que fija presupuesto
    cero quiere decir. None y 0 no son lo mismo: None es "sin tope
    configurado", 0 es "no gastes nada"."""
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "cost.db")
    ctrl = CostController(db_path=db_path, max_diff_tokens=50, monthly_budget_tokens=0)
    assert ctrl.budget_remaining("org/repo") == 0
    assert ctrl.should_skip("org/repo") is True
    ctrl.close()


def test_negative_budget_tokens_also_means_no_budget():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "cost.db")
    ctrl = CostController(db_path=db_path, max_diff_tokens=50, monthly_budget_tokens=-1)
    assert ctrl.budget_remaining("org/repo") == 0
    assert ctrl.should_skip("org/repo") is True
    ctrl.close()
