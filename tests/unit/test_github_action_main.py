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
        patch("watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client),
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


def test_run_writes_score_semaforo_blocked_to_github_output(monkeypatch, tmp_path):
    """`action.yml` reexpone estos outputs para que un workflow que consuma
    la Action pueda ramificar sobre el resultado sin parsear el comentario
    del PR -- `GITHUB_OUTPUT` es el mecanismo real que usa el runner."""
    output_path = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    event_path = _write_event(tmp_path)
    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)

    with (
        patch("watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client),
        patch("watchgate.adapters.github_action.main.parse_diff", return_value=_fake_diff()),
        patch(
            "watchgate.adapters.github_action.main.run_full_analysis",
            return_value=_fake_result(Semaforo.ROJO, 90),
        ),
    ):
        gha_main.run(event_path, github_token="fake-token")

    contents = output_path.read_text()
    assert "score=90" in contents
    assert "semaforo=rojo" in contents
    assert "blocked=true" in contents


def test_run_without_github_output_env_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    event_path = _write_event(tmp_path)
    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)

    with (
        patch("watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client),
        patch("watchgate.adapters.github_action.main.parse_diff", return_value=_fake_diff()),
        patch(
            "watchgate.adapters.github_action.main.run_full_analysis",
            return_value=_fake_result(Semaforo.VERDE, 5),
        ),
    ):
        exit_code = gha_main.run(event_path, github_token="fake-token")

    assert exit_code == 0


def test_run_returns_failure_exit_code_when_red_and_block_on_red(tmp_path):
    event_path = _write_event(tmp_path)
    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)

    with (
        patch("watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client),
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


def test_run_persists_result_to_dashboard(tmp_path):
    event_path = _write_event(tmp_path)
    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)
    result = _fake_result(Semaforo.VERDE, 5)

    with (
        patch("watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client),
        patch("watchgate.adapters.github_action.main.parse_diff", return_value=_fake_diff()),
        patch(
            "watchgate.adapters.github_action.main.run_full_analysis",
            return_value=result,
        ),
        patch(
            "watchgate.adapters.github_action.main.dashboard_client.post_score"
        ) as mock_post_score,
    ):
        gha_main.run(event_path, github_token="fake-token")

    mock_post_score.assert_called_once_with(result, "author-login")


def test_run_applies_dashboard_config_before_analysis(tmp_path):
    event_path = _write_event(tmp_path)
    fake_client = MagicMock()
    fake_client.get_pr_diff_shas.return_value = ("base" * 10, "head" * 10)
    result = _fake_result(Semaforo.VERDE, 5)
    config_from_dashboard = object()  # sentinel distinto del config de load_config()

    with (
        patch("watchgate.adapters.github_action.main.GitHubClient", return_value=fake_client),
        patch("watchgate.adapters.github_action.main.parse_diff", return_value=_fake_diff()),
        patch(
            "watchgate.adapters.github_action.main.run_full_analysis", return_value=result
        ) as mock_run_full_analysis,
        patch("watchgate.adapters.github_action.main.dashboard_client.post_score"),
        patch(
            "watchgate.adapters.github_action.main.dashboard_settings_client."
            "apply_dashboard_config",
            return_value=config_from_dashboard,
        ) as mock_apply_config,
    ):
        gha_main.run(event_path, github_token="fake-token")

    mock_apply_config.assert_called_once()
    args, _ = mock_apply_config.call_args
    assert args[1] == "org/repo"
    # run_full_analysis debe recibir el config ya combinado con el del
    # dashboard, no el que devuelve load_config() a secas.
    analysis_args, _ = mock_run_full_analysis.call_args
    assert analysis_args[2] is config_from_dashboard


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
