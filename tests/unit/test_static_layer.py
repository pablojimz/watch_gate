"""Tests unitarios para StaticLayer (watchgate/core/layers/static_layer.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from watchgate.core.layers.base import LAYER_REGISTRY
from watchgate.core.layers.static_layer import SEVERITY_SCORE, StaticLayer
from watchgate.core.models import CommitAuthor, FileChange, FileStatus, NormalizedDiff


def _make_diff(files: list[FileChange]) -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="0000000000000000000000000000000000000000",
        head_sha="1111111111111111111111111111111111111111",
        repo_path="/tmp/fake_repo",
        files=files,
        commit_messages=["test commit"],
        authors=[CommitAuthor(name="Test User", email="test@example.com")],
    )


def test_static_layer_registered() -> None:
    assert "static" in LAYER_REGISTRY
    assert LAYER_REGISTRY["static"] is StaticLayer


def test_detect_language() -> None:
    layer = StaticLayer()
    assert layer._detect_language("src/main.py") == "python"
    assert layer._detect_language("web/app.js") == "javascript"
    assert layer._detect_language("web/app.tsx") == "typescript"
    assert layer._detect_language("config/ci.yml") == "yaml"
    assert layer._detect_language("README.md") is None


def test_severity_score_mapping() -> None:
    assert SEVERITY_SCORE["INFO"] == 10
    assert SEVERITY_SCORE["WARNING"] == 30
    assert SEVERITY_SCORE["ERROR"] == 60


def test_static_layer_clean_diff() -> None:
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,1 +1,1 @@\n-print('hello')\n+print('hello world')",
                additions=1,
                deletions=1,
            )
        ]
    )

    with patch.object(layer, "_run_semgrep_on_file", return_value=[]):
        with patch.object(layer, "_get_rules_dir", return_value=Path(tempfile.gettempdir())):
            res = layer.analyze(diff, {})

    assert res.risk_score == 0
    assert "No se encontraron hallazgos estáticos" in res.justification
    assert res.skipped is False


def test_static_layer_with_findings_takes_max_score() -> None:
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/eval_test.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,1 @@\n+eval(user_input)",
                additions=1,
                deletions=0,
            )
        ]
    )

    mock_findings = [
        {
            "tool": "semgrep",
            "rule_id": "rules.eval-exec-dynamic",
            "message": "eval()",
            "risk_score": 60,
        },
        {"tool": "semgrep", "rule_id": "rules.network-call", "message": "curl", "risk_score": 30},
    ]

    with patch.object(layer, "_run_semgrep_on_file", return_value=mock_findings):
        with patch.object(layer, "_get_rules_dir", return_value=Path(tempfile.gettempdir())):
            res = layer.analyze(diff, {})

    # Debe tomar el MAX (60), NUNCA SUMAR (90)
    assert res.risk_score == 60
    assert "eval-exec-dynamic" in res.justification
    assert "2 hallazgos estáticos" in res.justification


def test_static_layer_skips_when_rules_unavailable() -> None:
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,1 +1,1 @@\n+x = 1",
                additions=1,
                deletions=0,
            )
        ]
    )

    with patch.object(layer, "_get_rules_dir", return_value=None):
        res = layer.analyze(diff, {})

    assert res.risk_score == 0
    assert res.skipped is True
    assert "Reglas Semgrep no disponibles" in res.skip_reason
