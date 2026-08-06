"""Tests de watchgate/adapters/github_action/github_client.py (spec §12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import httpx
import pytest

from watchgate.adapters.github_action.github_client import GitHubClient


def _mock_response(json_data, headers: dict[str, str] | None = None) -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = json_data
    resp.headers = headers or {}
    return resp


def test_get_pr_diff_shas_reads_base_and_head_from_event_payload():
    client = GitHubClient(token="fake-token")
    pr_event = {
        "pull_request": {
            "base": {"sha": "aaaa"},
            "head": {"sha": "bbbb"},
        }
    }
    base_sha, head_sha = client.get_pr_diff_shas(pr_event)
    assert base_sha == "aaaa"
    assert head_sha == "bbbb"


def test_get_reputation_metadata_builds_real_signals_from_github_api():
    client = GitHubClient(token="fake-token")
    created_at = (datetime.now(UTC) - timedelta(days=400)).isoformat().replace("+00:00", "Z")

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/users/octocat"):
            return _mock_response({"login": "octocat", "created_at": created_at})
        if url.endswith("/repos/org/repo/commits") and params.get("author") == "octocat":
            return _mock_response(
                [{"author": {"login": "octocat"}, "commit": {"verification": {"verified": True}}}],
                headers={"Link": '<...?page=12>; rel="last"'},
            )
        if url.endswith("/repos/org/repo/commits") and "author" not in params:
            return _mock_response(
                [
                    {"commit": {"verification": {"verified": False}}},
                    {"commit": {"verification": {"verified": True}}},
                ]
            )
        raise AssertionError(f"URL inesperada: {url} params={params}")

    with patch("httpx.get", side_effect=fake_get):
        rep = client.get_reputation_metadata("org", "repo", "octocat")

    assert rep.author_login == "octocat"
    assert rep.author_account_age_days is not None and rep.author_account_age_days >= 399
    assert rep.author_prior_contributions_to_repo == 12
    assert rep.commit_email_matches_verified_email is True
    assert rep.commit_is_signed is True
    assert rep.signing_key_seen_before_for_login is None
    assert rep.repo_has_history_of_signed_commits is True


def test_get_reputation_metadata_degrades_gracefully_when_user_lookup_fails():
    """Un fallo puntual de la API (ej. el usuario se borró la cuenta) no debe
    tirar abajo el resto de señales -- ni tampoco convertirse en una
    reputación "intachable" por defecto."""
    client = GitHubClient(token="fake-token")

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/users/ghost"):
            raise httpx.HTTPStatusError("404", request=Mock(), response=Mock(status_code=404))
        if url.endswith("/repos/org/repo/commits") and params.get("author") == "ghost":
            return _mock_response([])
        if url.endswith("/repos/org/repo/commits"):
            return _mock_response([])
        raise AssertionError(f"URL inesperada: {url}")

    with patch("httpx.get", side_effect=fake_get):
        rep = client.get_reputation_metadata("org", "repo", "ghost")

    assert rep.author_account_age_days is None
    assert rep.author_prior_contributions_to_repo == 0
    assert rep.commit_email_matches_verified_email is False
    assert rep.commit_is_signed is False


def test_post_comment_sends_body_to_the_right_pr():
    client = GitHubClient(token="fake-token")
    fake_resp = Mock()
    fake_resp.raise_for_status = Mock()
    with patch("httpx.post", return_value=fake_resp) as mock_post:
        client.post_comment("org", "repo", 42, "cuerpo del comentario")

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.github.com/repos/org/repo/issues/42/comments"
    assert kwargs["json"] == {"body": "cuerpo del comentario"}
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token"


def test_post_check_run_maps_conclusion_and_summary():
    client = GitHubClient(token="fake-token")
    fake_resp = Mock()
    fake_resp.raise_for_status = Mock()
    with patch("httpx.post", return_value=fake_resp) as mock_post:
        client.post_check_run("org", "repo", "deadbeef", "failure", "riesgo alto")

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.github.com/repos/org/repo/check-runs"
    body = kwargs["json"]
    assert body["head_sha"] == "deadbeef"
    assert body["conclusion"] == "failure"
    assert body["output"]["summary"] == "riesgo alto"


def test_post_comment_propagates_failures_instead_of_swallowing_them():
    """A diferencia de get_reputation_metadata, un fallo aquí sí debe
    propagarse -- si no se puede publicar, el resultado del análisis no
    llega a nadie, y eso debe hacer fallar el job de forma ruidosa."""
    client = GitHubClient(token="fake-token")
    with patch("httpx.post", side_effect=httpx.ConnectError("sin red")):
        with pytest.raises(httpx.ConnectError):
            client.post_comment("org", "repo", 1, "x")
