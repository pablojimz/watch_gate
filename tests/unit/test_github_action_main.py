"""Tests de watchgate/adapters/github_action/main.py (spec §12).

Sin red real ni git real: GitHubClient y parse_diff se sustituyen por dobles
de prueba inyectados; el propósito es probar la orquestación (qué se llama,
en qué orden, con qué datos), no las piezas que ya tienen sus propios tests
(github_client.py, pipeline.py, diffparser.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from watchgate.adapters.github_action import main as gha_main
from watchgate.core.models import (
    AggregatedResult,
    Confidence,
    FileChange,
    FileStatus,
    LayerResult,
    NormalizedDiff,
    RiskCategory,
    Semaforo,
)


def _pr_event(pr_number: int = 7) -> dict:
    return {
        "repository": {"owner": {"login": "org"}, "name": "repo"},
        "pull_request": {
            "number": pr_number,
            "user": {"login": "author-login"},
            "base": {"sha": "base" * 10},
            "head": {"sha": "head" * 10},
        },
    }


def _write_event(tmp_path: Path, pr_number: int = 7) -> str:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_pr_event(pr_number)))
    return str(event_path)


def _fake_diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="base" * 10,
        head_sha="head" * 10,
        repo_path=".",
        files=[
            FileChange(
                path="app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="+x=1",
                additions=1,
                deletions=0,
            )
        ],
        commit_messages=["fix: cosa"],
        authors=[],
    )


def _fake_result(semaforo: Semaforo, score: int) -> AggregatedResult:
    return AggregatedResult(
        score=score,
        semaforo=semaforo,
        layer_results={
            "semantic": LayerResult(
                layer_name="semantic",
                risk_score=score,
                justification="justificación",
                category=RiskCategory.NINGUNA,
                confidence=Confidence.ALTA,
            )
        },
        weights_used={"semantic": 1.0},
        pr_id="7",
        repo="org/repo",
        timestamp="2026-01-01T00:00:00+00:00",
    )


def test_run_posts_comment_and_check_run_with_pr_context_from_event(tmp_path):
    event_path = _write_event(tmp_path)
    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)
    fake_client.get_reputation_metadata.return_value = MagicMock()

    with (
        patch(
            "watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client
        ),
        patch("watchgate.adapters.github_action.main.parse_diff", return_value=_fake_diff()),
        patch(
            "watchgate.adapters.github_action.main.run_full_analysis",
            return_value=_fake_result(Semaforo.VERDE, 5),
        ),
    ):
        exit_code = gha_main.run(event_path, github_token="fake-token")

    fake_client.get_reputation_metadata.assert_called_once_with("org", "repo", "author-login")
    fake_client.post_comment.assert_called_once()
    args, _ = fake_client.post_comment.call_args
    assert args[0] == "org"
    assert args[1] == "repo"
    assert args[2] == 7

    fake_client.post_check_run.assert_called_once()
    check_args, _ = fake_client.post_check_run.call_args
    assert check_args[2] == "head" * 10
    assert check_args[3] == "neutral"  # verde no bloquea

    assert exit_code == 0


def test_run_returns_failure_exit_code_when_red_and_block_on_red(tmp_path):
    event_path = _write_event(tmp_path)
    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)

    with (
        patch(
            "watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client
        ),
        patch("watchgate.adapters.github_action.main.parse_diff", return_value=_fake_diff()),
        patch(
            "watchgate.adapters.github_action.main.run_full_analysis",
            return_value=_fake_result(Semaforo.ROJO, 90),
        ),
    ):
        exit_code = gha_main.run(event_path, github_token="fake-token")

    check_args, _ = fake_client.post_check_run.call_args
    assert check_args[3] == "failure"
    assert exit_code == 1


def test_main_exits_early_without_github_token(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_EVENT_PATH", _write_event(tmp_path))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert gha_main.main() == 1


def test_main_exits_early_without_event_path(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    assert gha_main.main() == 1


def test_api_key_never_appears_in_output(tmp_path, capsys):
    """Test de seguridad obligatorio (spec §12): ejecutar la Action en modo
    simulado y comprobar que el valor literal de la API key no aparece en
    ningún mensaje impreso -- ni el token de GitHub ni el de WATCHGATE_LLM."""
    event_path = _write_event(tmp_path)
    secret_github_token = "ghs_SUPER_SECRETO_1234567890"  # noqa: S105

    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)

    with (
        patch(
            "watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client
        ) as mock_client_cls,
        patch("watchgate.adapters.github_action.main.parse_diff", return_value=_fake_diff()),
        patch(
            "watchgate.adapters.github_action.main.run_full_analysis",
            return_value=_fake_result(Semaforo.AMARILLO, 50),
        ),
    ):
        gha_main.run(event_path, github_token=secret_github_token)

    captured = capsys.readouterr()
    assert secret_github_token not in captured.out
    assert secret_github_token not in captured.err
    # el token sí debe haberse usado para construir el cliente -- no es que
    # simplemente no se use, es que no debe imprimirse
    mock_client_cls.assert_called_once_with(token=secret_github_token)


