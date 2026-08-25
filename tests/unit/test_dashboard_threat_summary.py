"""Tests de watchgate/dashboard/backend/db.py: persistencia del desglose de
naturaleza de amenaza (`threat_summary` / `LayerResult.threat_nature` de la
capa estática) al guardar y releer un `AggregatedResult` -- ver
docs/planificacion/plan_separacion_vulnerabilidad_malware.md §"Actualización
del Dashboard queda diferida para una fase posterior" (esta es esa fase).
"""

from __future__ import annotations

from pathlib import Path

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo, ThreatNature
from watchgate.dashboard.backend import db as database


def _result_with_malicious_static_finding() -> AggregatedResult:
    layers = {
        "static": LayerResult(
            layer_name="static",
            risk_score=95,
            justification="Se encontraron hallazgos estáticos.",
            threat_nature=ThreatNature.MALICIOUS,
        ),
        "deps": LayerResult(layer_name="deps", risk_score=0, justification=""),
    }
    return AggregatedResult(
        score=100,
        semaforo=Semaforo.ROJO,
        layer_results=layers,
        weights_used={"static": 0.25, "deps": 0.15},
        pr_id="7",
        repo="acme/payments-api",
        timestamp="2026-08-10T12:00:00+00:00",
        threat_summary={"malicioso": 1, "vulnerabilidad": 0, "incertidumbre": 0},
    )


def test_insert_aggregated_persists_threat_summary_and_static_threat_nature(
    tmp_path: Path,
) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        score_id = database.insert_aggregated(conn, _result_with_malicious_static_finding())

        stored = database.get_score(conn, score_id)

    assert stored is not None
    assert stored.threat_summary == {"malicioso": 1, "vulnerabilidad": 0, "incertidumbre": 0}
    # ScoreOut.layer_results son dicts (model_dump() de LayerResult), no
    # instancias -- el enum ya viaja como su .value ("malicioso").
    assert stored.layer_results["static"]["threat_nature"] == ThreatNature.MALICIOUS.value
    # Ninguna otra capa persiste threat_nature hoy (solo static_threat_nature
    # tiene columna dedicada) -- no debe inventarse uno para deps.
    assert stored.layer_results["deps"]["threat_nature"] is None


def test_insert_aggregated_persists_justification_for_every_layer_not_only_semantic(
    tmp_path: Path,
) -> None:
    """Bug real, reproducido: el dashboard mostraba el risk_score de
    static/reputation con un score alto (70/80) pero SIN ninguna
    explicación, mientras que semantic sí la mostraba -- `_serialize_
    findings` solo guardaba `justification` para `semantic` (vía la
    columna dedicada `semantic_justification`), nunca para el resto de
    capas, aunque esas capas SÍ generan una frase real (p. ej.
    reputation_layer.py construye "El autor no tiene contribuciones
    previas a este repositorio." -- nunca cadena vacía salvo que de
    verdad no haya señales)."""
    layers = {
        "static": LayerResult(
            layer_name="static",
            risk_score=70,
            justification="Se detectó un patrón de ofuscación en 2 ficheros.",
        ),
        "reputation": LayerResult(
            layer_name="reputation",
            risk_score=80,
            justification="El autor no tiene contribuciones previas a este repositorio.",
        ),
        "semantic": LayerResult(
            layer_name="semantic",
            risk_score=85,
            justification="Secret hardcodeado (AWS key) en variable de entorno del modulo.",
        ),
    }
    result = AggregatedResult(
        score=59,
        semaforo=Semaforo.ROJO,
        layer_results=layers,
        weights_used={"static": 0.25, "reputation": 0.15, "semantic": 0.40},
        pr_id="8",
        repo="acme/payments-api",
        timestamp="2026-08-12T00:00:00+00:00",
    )
    with database.db_session(tmp_path / "dashboard.db") as conn:
        score_id = database.insert_aggregated(conn, result)
        stored = database.get_score(conn, score_id)

    assert stored is not None
    assert (
        stored.layer_results["static"]["justification"]
        == "Se detectó un patrón de ofuscación en 2 ficheros."
    )
    assert (
        stored.layer_results["reputation"]["justification"]
        == "El autor no tiene contribuciones previas a este repositorio."
    )
    assert (
        stored.layer_results["semantic"]["justification"]
        == "Secret hardcodeado (AWS key) en variable de entorno del modulo."
    )


def test_insert_aggregated_defaults_threat_summary_and_static_threat_nature_to_empty(
    tmp_path: Path,
) -> None:
    """Una PR sin hallazgos (AggregatedResult con threat_summary por
    defecto y sin threat_nature en la capa static) no debe hacer explotar
    la reconstrucción -- debe releerse como "todo a cero"/None."""
    layers = {"static": LayerResult(layer_name="static", risk_score=0, justification="")}
    result = AggregatedResult(
        score=0,
        semaforo=Semaforo.VERDE,
        layer_results=layers,
        weights_used={"static": 0.25},
        pr_id="8",
        repo="acme/payments-api",
        timestamp="2026-08-10T12:05:00+00:00",
    )

    with database.db_session(tmp_path / "dashboard.db") as conn:
        score_id = database.insert_aggregated(conn, result)
        stored = database.get_score(conn, score_id)

    assert stored is not None
    assert stored.threat_summary == {
        "malicioso": 0,
        "vulnerabilidad": 0,
        "incertidumbre": 0,
    }
    assert stored.layer_results["static"]["threat_nature"] is None


def test_list_scores_round_trips_threat_summary(tmp_path: Path) -> None:
    with database.db_session(tmp_path / "dashboard.db") as conn:
        database.insert_aggregated(conn, _result_with_malicious_static_finding())
        scores = database.list_scores(conn, "acme/payments-api")

    assert len(scores) == 1
    assert scores[0].threat_summary["malicioso"] == 1
