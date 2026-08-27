"""Tests de watchgate/adapters/github_action/github_client.py (spec §12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from watchgate.adapters.github_client import DiffTooLargeError, GitHubClient


def _mock_response(json_data, headers: dict[str, str] | None = None) -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = json_data
    resp.headers = headers or {}
    return resp


def _mock_stream_response(
    chunks: list[str], status_code: int = 200, headers: dict[str, str] | None = None
) -> MagicMock:
    """Simula el context manager que devuelve `httpx.stream(...)`, usado
    por `_stream_diff` (get_pull_request_diff / get_compare_diff)."""
    resp = Mock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.raise_for_status = Mock()
    resp.iter_text = Mock(return_value=iter(chunks))
    cm = MagicMock()
    cm.__enter__ = Mock(return_value=resp)
    cm.__exit__ = Mock(return_value=False)
    return cm


def test_github_client_custom_api_url_and_token(monkeypatch):
    client = GitHubClient(token="custom_tok", api_url="https://github.enterprise.com/api/v3")
    assert client._api_base == "https://github.enterprise.com/api/v3"
    assert client._headers["Authorization"] == "Bearer custom_tok"

    monkeypatch.setenv("WATCHGATE_GITHUB_TOKEN", "env_tok")
    monkeypatch.setenv("WATCHGATE_GITHUB_API_URL", "https://env-github.com/api/v3")
    client_env = GitHubClient()
    assert client_env._api_base == "https://env-github.com/api/v3"
    assert client_env._headers["Authorization"] == "Bearer env_tok"


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


def test_github_client_list_all_open_pull_requests_paginates():
    client = GitHubClient("fake_token")

    def fake_get(url, params=None):
        page = (params or {}).get("page", 1)
        if page == 1:
            return _mock_response([{"number": i} for i in range(1, 51)])
        if page == 2:
            return _mock_response([{"number": i} for i in range(51, 60)])
        return _mock_response([])

    with patch.object(client, "_get", side_effect=fake_get):
        prs = client.list_all_open_pull_requests("owner", "repo", max_prs=50)
        assert len(prs) == 50
        assert prs[0]["number"] == 1
        assert prs[-1]["number"] == 50


def test_get_reputation_metadata_builds_real_signals_from_github_api():
    client = GitHubClient(token="fake-token")
    created_at = (datetime.now(UTC) - timedelta(days=400)).isoformat().replace("+00:00", "Z")

    def fake_request(method, url, headers=None, params=None, timeout=None, follow_redirects=None):
        if url.endswith("/users/octocat"):
            return _mock_response({"login": "octocat", "created_at": created_at})
        if url.endswith("/repos/org/repo/commits") and params.get("author") == "octocat":
            return _mock_response(
                [{"author": {"login": "octocat"}, "commit": {"verification": {"verified": True}}}],
                headers={"Link": '<...?page=12>; rel="last"'},
            )
        if url.endswith("/repos/org/repo/commits") and "author" not in (params or {}):
            return _mock_response(
                [
                    {"commit": {"verification": {"verified": False}}},
                    {"commit": {"verification": {"verified": True}}},
                ]
            )
        raise AssertionError(f"URL inesperada: {url} params={params}")

    with patch("httpx.request", side_effect=fake_request):
        rep = client.get_reputation_metadata("org", "repo", "octocat")

    assert rep.author_login == "octocat"
    assert rep.author_account_age_days is not None and rep.author_account_age_days >= 399
    assert rep.author_prior_contributions_to_repo == 12
    assert rep.commit_email_matches_verified_email is True
    assert rep.commit_is_signed is True
    assert rep.signing_key_seen_before_for_login is None
    assert rep.repo_has_history_of_signed_commits is True


def test_get_reputation_metadata_with_pr_number_and_profile_activity():
    client = GitHubClient(token="fake-token")
    created_at = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")

    def fake_request(method, url, headers=None, params=None, timeout=None, follow_redirects=None):
        if url.endswith("/users/newuser"):
            return _mock_response(
                {"login": "newuser", "created_at": created_at, "public_repos": 0, "followers": 0}
            )
        if url.endswith("/repos/org/repo/commits") and (params or {}).get("author") == "newuser":
            return _mock_response([])
        if url.endswith("/repos/org/repo/pulls/5/commits"):
            return _mock_response(
                [{"author": {"login": "newuser"}, "commit": {"verification": {"verified": True}}}]
            )
        if url.endswith("/repos/org/repo/commits") and "author" not in (params or {}):
            return _mock_response([])
        raise AssertionError(f"URL inesperada: {url} params={params}")

    with patch("httpx.request", side_effect=fake_request):
        rep = client.get_reputation_metadata("org", "repo", "newuser", pr_number=5)

    assert rep.author_login == "newuser"
    assert rep.author_public_repos == 0
    assert rep.author_followers == 0
    assert rep.author_prior_contributions_to_repo == 0
    assert rep.commit_email_matches_verified_email is True
    assert rep.commit_is_signed is True


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


def test_merge_pull_request_sends_merge_method_to_the_right_pr():
    client = GitHubClient(token="fake-token")
    fake_resp = Mock()
    fake_resp.raise_for_status = Mock()
    fake_resp.json.return_value = {"merged": True, "message": "Pull Request successfully merged"}
    with patch("httpx.put", return_value=fake_resp) as mock_put:
        result = client.merge_pull_request("org", "repo", 42)

    args, kwargs = mock_put.call_args
    assert args[0] == "https://api.github.com/repos/org/repo/pulls/42/merge"
    assert kwargs["json"] == {"merge_method": "squash"}
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token"
    assert result["merged"] is True


def test_merge_pull_request_propagates_failures_instead_of_swallowing_them():
    """Un merge rechazado por GitHub (rama protegida, checks pendientes,
    conflictos...) debe propagarse -- quien llama (accept_score) decide
    cómo comunicarlo, no este cliente."""
    client = GitHubClient(token="fake-token")
    fake_resp = Mock()
    fake_resp.raise_for_status = Mock(
        side_effect=httpx.HTTPStatusError("405", request=Mock(), response=Mock())
    )
    with patch("httpx.put", return_value=fake_resp):
        with pytest.raises(httpx.HTTPStatusError):
            client.merge_pull_request("org", "repo", 42)


def test_get_repo_metadata_fetches_repo_json():
    client = GitHubClient(token="fake-token")
    with patch.object(
        client, "_get", return_value=_mock_response({"default_branch": "develop"})
    ) as mock_get:
        meta = client.get_repo_metadata("org", "repo")

    assert meta["default_branch"] == "develop"
    mock_get.assert_called_once_with("/repos/org/repo")


def test_get_branch_head_commit_fetches_commit_json():
    client = GitHubClient(token="fake-token")
    commit_json = {"sha": "abc123", "author": {"login": "octocat"}}
    with patch.object(client, "_get", return_value=_mock_response(commit_json)) as mock_get:
        commit = client.get_branch_head_commit("org", "repo", "main")

    assert commit["sha"] == "abc123"
    mock_get.assert_called_once_with("/repos/org/repo/commits/main")


def test_get_compare_diff_streams_against_the_compare_endpoint():
    client = GitHubClient(token="fake-token")
    with patch(
        "httpx.stream", return_value=_mock_stream_response(["diff --git a/x b/x\n"])
    ) as mock_stream:
        diff = client.get_compare_diff("org", "repo", "base-sha", "main")

    assert diff == "diff --git a/x b/x\n"
    args, _kwargs = mock_stream.call_args
    assert args[0] == "GET"
    assert args[1] == "https://api.github.com/repos/org/repo/compare/base-sha...main"


def test_get_compare_diff_raises_when_over_size_limit():
    """MISMO límite de 2MB que get_pull_request_diff -- comparten
    _stream_diff, y en un repo grande esto es bastante más probable de
    alcanzar aquí que en el diff de una sola PR."""
    client = GitHubClient(token="fake-token")
    huge_chunk = "a" * (2 * 1024 * 1024 + 1)
    with patch("httpx.stream", return_value=_mock_stream_response([huge_chunk])):
        with pytest.raises(DiffTooLargeError):
            client.get_compare_diff("org", "repo", "base-sha", "main")


def test_get_root_commit_sha_paginates_to_the_last_page():
    """Hallazgo real en vivo: la Compare API de GitHub no admite el SHA del
    árbol vacío de git como base (404) -- hace falta el primer commit REAL.
    per_page=1 + la cabecera Link "last" da el número total de páginas sin
    tener que descargar el historial completo; esa última página trae el
    commit más antiguo."""
    client = GitHubClient(token="fake-token")

    def fake_get(url, params=None):
        if params.get("page") is None:
            return _mock_response(
                [{"sha": "head-sha"}], headers={"Link": '<...?page=42>; rel="last"'}
            )
        assert params["page"] == 42
        return _mock_response([{"sha": "root-sha"}])

    with patch.object(client, "_get", side_effect=fake_get):
        root_sha = client.get_root_commit_sha("org", "repo", "main")

    assert root_sha == "root-sha"


def test_get_root_commit_sha_single_commit_branch_has_no_last_page():
    """Sin cabecera Link "last" (una sola página -- rama con un único
    commit), ese único commit YA es el root; no debe intentar una segunda
    petición."""
    client = GitHubClient(token="fake-token")
    with patch.object(
        client, "_get", return_value=_mock_response([{"sha": "only-commit-sha"}])
    ) as mock_get:
        root_sha = client.get_root_commit_sha("org", "repo", "main")

    assert root_sha == "only-commit-sha"
    assert mock_get.call_count == 1


def test_get_default_branch_scan_data_builds_pr_shaped_metadata():
    """El resultado debe encajar en la MISMA forma que get_pull_request_data
    (metadata["user"]["login"]) para que run_main_branch_scan reutilice el
    pipeline de análisis sin ningún cambio, y el diff debe pedirse contra el
    commit ROOT real (no el SHA del árbol vacío -- ver
    get_root_commit_sha)."""
    client = GitHubClient(token="fake-token")
    with (
        patch.object(client, "get_repo_metadata", return_value={"default_branch": "develop"}),
        patch.object(
            client,
            "get_branch_head_commit",
            return_value={"sha": "headsha123", "author": {"login": "octocat"}},
        ),
        patch.object(client, "get_root_commit_sha", return_value="root-sha-abc") as mock_root,
        patch.object(client, "get_compare_diff", return_value="diff --git a/x b/x\n") as mock_cmp,
    ):
        diff_text, metadata = client.get_default_branch_scan_data("org", "repo")

    assert diff_text == "diff --git a/x b/x\n"
    assert metadata["user"]["login"] == "octocat"
    assert metadata["head"]["sha"] == "headsha123"
    assert metadata["default_branch"] == "develop"
    mock_root.assert_called_once_with("org", "repo", "develop")
    mock_cmp.assert_called_once_with("org", "repo", "root-sha-abc", "develop")


def test_get_default_branch_scan_data_falls_back_when_metadata_incomplete():
    """Sin default_branch en la respuesta del repo, sin autor resuelto en
    el commit HEAD, o sin poder resolver el root commit -- no debe
    reventar: cae a "main"/"unknown"/comparar la rama contra sí misma
    (diff vacío), igual que get_pull_request_data hace hoy vía
    metadata.get(...)."""
    client = GitHubClient(token="fake-token")
    with (
        patch.object(client, "get_repo_metadata", return_value={}),
        patch.object(client, "get_branch_head_commit", return_value={"sha": "headsha"}),
        patch.object(client, "get_root_commit_sha", return_value=None),
        patch.object(client, "get_compare_diff", return_value="") as mock_cmp,
    ):
        _diff_text, metadata = client.get_default_branch_scan_data("org", "repo")

    assert metadata["user"]["login"] == "unknown"
    assert metadata["default_branch"] == "main"
    mock_cmp.assert_called_once_with("org", "repo", "main", "main")
