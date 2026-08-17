"""Tests de watchgate/dashboard/backend/db.py: el `pr_id` de un escaneo de
la rama principal ("main", ver tasks.py::MAIN_BRANCH_SCAN_PR_ID) debe
sobrevivir el viaje de ida y vuelta por `pr_scores` -- antes se guardaba
como `pr_number=0` (columna INTEGER, "main" no tiene dígitos) pero se
releía como `pr_id="0"`, indistinguible en el historial de un hipotético
"PR #0" (que nunca existe de verdad en GitHub).
"""

from __future__ import annotations

from pathlib import Path

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
from watchgate.dashboard.backend import db as database


def _main_branch_result(repo: str = "acme/payments-api") -> AggregatedResult:
    layers = {
        "static": LayerResult(layer_name="static", risk_score=10, justification=""),
        "deps": LayerResult(layer_name="deps", risk_score=5, justification=""),
    }
    return AggregatedResult(
        score=10,
        semaforo=Semaforo.VERDE,
        layer_results=layers,
        weights_used={"static": 0.25, "deps": 0.15},
        pr_id="main",
        repo=repo,
        timestamp="2026-08-17T12:00:00+00:00",
    )


def test_main_branch_scan_roundtrips_pr_id_as_main_not_zero(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        score_id = database.insert_aggregated(conn, _main_branch_result())
        stored = database.get_score(conn, score_id)

    assert stored is not None
    assert stored.pr_id == "main"


def test_main_branch_scan_does_not_collide_with_a_real_pr(tmp_path: Path) -> None:
    """Un escaneo de "main" y una PR real conviven en el mismo repo sin
    pisarse -- confirma que el sentinel interno (pr_number=0) no colisiona
    con ningún pr_number real (siempre >= 1 en GitHub)."""
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _main_branch_result())
        pr_result = _main_branch_result()
        pr_result.pr_id = "12"
        database.insert_aggregated(conn, pr_result)

        scores = database.list_scores(conn, "acme/payments-api")

    pr_ids = {s.pr_id for s in scores}
    assert pr_ids == {"main", "12"}
