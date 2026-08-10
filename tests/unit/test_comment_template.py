"""Tests de render_comment (watchgate/core/comment_template.py)."""

from __future__ import annotations

from watchgate.core.comment_template import render_comment
from watchgate.core.models import AggregatedResult, LayerResult, Semaforo


def _result(*, malicioso: int, vulnerabilidad: int = 0) -> AggregatedResult:
    return AggregatedResult(
        score=100 if malicioso else 51,
        semaforo=Semaforo.ROJO if malicioso else Semaforo.AMARILLO,
        pr_id="1",
        repo="acme/webapp",
        timestamp="2026-08-10T10:00:00+00:00",
        weights_used={"semantic": 1.0},
        threat_summary={
            "malicioso": malicioso,
            "vulnerabilidad": vulnerabilidad,
            "incertidumbre": 0,
        },
        layer_results={
            "semantic": LayerResult(
                layer_name="semantic",
                risk_score=95,
                justification=(
                    "El fichero exfiltra AWS_SECRET_ACCESS_KEY a telemetry-sync.pw vía curl|bash."
                ),
                skipped=False,
            )
        },
    )


def test_malicious_result_redacts_layer_breakdown_and_justification() -> None:
    comment = render_comment(_result(malicioso=1))

    assert "telemetry-sync.pw" not in comment
    assert "curl|bash" not in comment
    assert "Semantic:" not in comment
    assert "bloqueado por la política de seguridad" in comment
    # El semáforo/score sigue siendo visible -- ya lo revela el check de CI.
    assert "Riesgo Alto (100/100)" in comment


def test_vulnerability_only_result_keeps_full_detail() -> None:
    comment = render_comment(_result(malicioso=0, vulnerabilidad=1))

    assert "telemetry-sync.pw" in comment
    assert "Semantic: 95/100" in comment
    assert "bloqueado por la política de seguridad" not in comment


def test_benign_result_is_never_redacted() -> None:
    result = _result(malicioso=0, vulnerabilidad=0).model_copy(
        update={"score": 5, "semaforo": Semaforo.VERDE}
    )
    comment = render_comment(result)

    assert "bloqueado por la política de seguridad" not in comment
    assert "Semantic: 95/100" in comment
