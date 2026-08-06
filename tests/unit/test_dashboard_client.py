"""Tests de watchgate/adapters/github_action/dashboard_client.py (spec §12, paso 8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from watchgate.adapters.github_action import dashboard_client
from watchgate.core.models import AggregatedResult, Confidence, LayerResult, RiskCategory, Semaforo


def _result() -> AggregatedResult:
    return AggregatedResult(
        score=42,
        semaforo=Semaforo.AMARILLO,
        layer_results={
            "semantic": LayerResult(
                layer_name="semantic",
                risk_score=42,
                justification="justificación",
                category=RiskCategory.NINGUNA,
                confidence=Confidence.ALTA,
            )
        },
        weights_used={"semantic": 1.0},
        pr_id="9",
        repo="org/repo",
        timestamp="2026-01-01T00:00:00+00:00",
    )


def test_does_nothing_when_dashboard_url_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_DASHBOARD_URL", raising=False)
    with patch("watchgate.adapters.github_action.dashboard_client.httpx.post") as mock_post:
        dashboard_client.post_score(_result(), "author-login")
    mock_post.assert_not_called()


def test_posts_result_with_bearer_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com/")
    monkeypatch.setenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", "secreto-ci")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None

    with patch(
        "watchgate.adapters.github_action.dashboard_client.httpx.post",
        return_value=fake_response,
    ) as mock_post:
        dashboard_client.post_score(_result(), "author-login")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://dashboard.example.com/api/scores"
    assert kwargs["headers"]["Authorization"] == "Bearer secreto-ci"
    assert kwargs["json"]["author_login"] == "author-login"
    assert kwargs["json"]["result"]["repo"] == "org/repo"


def test_posts_without_authorization_header_when_no_token_configured(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com")
    monkeypatch.delenv("WATCHGATE_DASHBOARD_INGEST_TOKEN", raising=False)
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None

    with patch(
        "watchgate.adapters.github_action.dashboard_client.httpx.post",
        return_value=fake_response,
    ) as mock_post:
        dashboard_client.post_score(_result(), None)

    _, kwargs = mock_post.call_args
    assert "Authorization" not in kwargs["headers"]


def test_swallows_http_errors_without_raising(monkeypatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_URL", "https://dashboard.example.com")
    with patch(
        "watchgate.adapters.github_action.dashboard_client.httpx.post",
        side_effect=httpx.ConnectError("no se pudo conectar"),
    ):
        dashboard_client.post_score(_result(), "author-login")  # no debe lanzar
