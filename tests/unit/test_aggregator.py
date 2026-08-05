"""Tests de aggregator.py (spec §10)."""

from __future__ import annotations

from watchgate.core.aggregator import aggregate
from watchgate.core.comment_template import render_comment
from watchgate.core.models import LayerResult, Semaforo


def _result(
    name: str, score: int, skipped: bool = False, skip_reason: str | None = None
) -> LayerResult:
    return LayerResult(
        layer_name=name,
        risk_score=score,
        justification=f"justificación de {name}",
        skipped=skipped,
        skip_reason=skip_reason,
    )


def test_regresion_literal_memoria_score_47_amarillo():
    """Test de regresión que no debe fallar nunca (spec §10): con estática 20,
    deps 10, reputación 40, semántica 85 y pesos 0.25/0.20/0.15/0.40, el
    resultado exacto de la memoria es score == 47, semaforo == AMARILLO."""
    results = {
        "static": _result("static", 20),
        "deps": _result("deps", 10),
        "reputation": _result("reputation", 40),
        "semantic": _result("semantic", 85),
    }
    weights = {"static": 0.25, "deps": 0.20, "reputation": 0.15, "semantic": 0.40}

    out = aggregate(results, weights, diff=None, pr_id="42", repo="org/repo")

    assert out.score == 47
    assert out.semaforo == Semaforo.AMARILLO


def test_skipped_layer_excluded_from_weighted_average():
    results = {
        "static": _result("static", 90),
        "semantic": _result("semantic", 0, skipped=True, skip_reason="presupuesto agotado"),
    }
    weights = {"static": 0.5, "semantic": 0.5}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    # Solo "static" cuenta: score == 90 -> ROJO.
    assert out.score == 90
    assert out.semaforo == Semaforo.ROJO


def test_all_layers_skipped_does_not_divide_by_zero():
    results = {
        "static": _result("static", 0, skipped=True, skip_reason="sin ficheros de código"),
    }
    weights = {"static": 1.0}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 0
    assert out.semaforo == Semaforo.VERDE


def test_thresholds_boundaries():
    weights = {"static": 1.0}

    verde = aggregate({"static": _result("static", 39)}, weights, None, "1", "r")
    amarillo = aggregate({"static": _result("static", 40)}, weights, None, "1", "r")
    rojo = aggregate({"static": _result("static", 70)}, weights, None, "1", "r")

    assert verde.semaforo == Semaforo.VERDE
    assert amarillo.semaforo == Semaforo.AMARILLO
    assert rojo.semaforo == Semaforo.ROJO


def test_render_comment_includes_score_and_semantic_justification():
    results = {
        "static": _result("static", 20),
        "semantic": _result("semantic", 85),
    }
    weights = {"static": 0.5, "semantic": 0.5}
    out = aggregate(results, weights, diff=None, pr_id="7", repo="org/repo")

    comment = render_comment(out)

    assert "52" in comment or str(out.score) in comment
    assert "justificación de semantic" in comment
    assert "Static: 20/100" in comment
    assert "Semantic: 85/100" in comment


def test_render_comment_shows_skip_reason_for_skipped_layer():
    results = {
        "static": _result("static", 10),
        "semantic": _result("semantic", 0, skipped=True, skip_reason="presupuesto agotado"),
    }
    weights = {"static": 1.0, "semantic": 0.0}
    out = aggregate(results, weights, diff=None, pr_id="7", repo="org/repo")

    comment = render_comment(out)

    assert "omitida: presupuesto agotado" in comment
    assert "Justificación (capa semántica):" not in comment
