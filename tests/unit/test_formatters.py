"""Pruebas unitarias para los formateadores de salida (SARIF, GitHub, Console)."""

from __future__ import annotations

import io
import json

from watchgate.core.models import (
    AggregatedResult,
    Finding,
    LayerResult,
    Semaforo,
)
from watchgate.formatters.console import render_console
from watchgate.formatters.github import render_github_annotations
from watchgate.formatters.sarif import normalize_sarif_path, render_sarif


def _make_dummy_aggregated(
    score: int = 45, semaforo: Semaforo = Semaforo.AMARILLO
) -> AggregatedResult:
    finding = Finding(
        file_path="src/auth.py",
        line=42,
        rule_id="eval-detected",
        message="Detección de eval() peligroso",
        severity="error",
    )
    static_res = LayerResult(
        layer_name="static",
        risk_score=80,
        justification="Se detectó eval()",
        findings=[finding],
    )
    deps_res = LayerResult(
        layer_name="dependencies",
        risk_score=10,
        justification="Sin alertas mayores",
    )
    return AggregatedResult(
        score=score,
        semaforo=semaforo,
        layer_results={"static": static_res, "dependencies": deps_res},
        weights_used={"static": 0.5, "dependencies": 0.5},
        pr_id="123",
        repo="org/repo",
        timestamp="2026-08-07T12:00:00Z",
    )


def test_normalize_sarif_path() -> None:
    assert normalize_sarif_path("src/auth.py") == "src/auth.py"
    assert normalize_sarif_path("/home/user/project/src/auth.py") == "home/user/project/src/auth.py"
    assert normalize_sarif_path("../src/auth.py") == "src/auth.py"
    assert normalize_sarif_path(".\\src\\auth.py") == "src/auth.py"


def test_render_sarif_valid_json() -> None:
    agg = _make_dummy_aggregated()
    sarif_str = render_sarif(agg)
    doc = json.loads(sarif_str)

    assert doc["version"] == "2.1.0"
    assert "runs" in doc
    runs = doc["runs"]
    assert len(runs) == 1
    results = runs[0]["results"]
    assert len(results) >= 1
    assert results[0]["ruleId"] == "watchgate-static-eval-detected"
    loc_uri = results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert loc_uri == "src/auth.py"
    assert results[0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 42


def test_render_github_annotations_stream() -> None:
    agg = _make_dummy_aggregated(score=75, semaforo=Semaforo.ROJO)
    stream = io.StringIO()
    output = render_github_annotations(agg, stream=stream)

    assert "::error title=WatchGate Score::" in output
    expected_line = (
        "::error title=WatchGate [static],file=src/auth.py,line=42"
        "::Detección de eval() peligroso"
    )
    assert expected_line in output
    assert stream.getvalue() == output + "\n"


def test_render_console_contains_panels() -> None:
    agg = _make_dummy_aggregated()
    console_out = render_console(agg)
    assert "WatchGate Security Gate Analysis" in console_out
    assert "Desglose por Capa de Análisis" in console_out
    assert "Estática (Semgrep/YARA)" in console_out
