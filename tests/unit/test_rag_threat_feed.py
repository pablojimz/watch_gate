"""Tests de watchgate/core/rag/threat_feed.py (sync de avisos al corpus).

Sin red: `httpx.get` se monkeypatchea con respuestas fabricadas con la misma
forma que la API real de GitHub Security Advisories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from watchgate.core.rag import threat_feed
from watchgate.core.rag.threat_feed import (
    advisory_case_id,
    advisory_to_markdown,
    fetch_advisories,
    sync_advisories_to_corpus,
)
from watchgate.dashboard.backend.routers.rag import _SAFE_CASE_ID, _parse_corpus_file

_MALWARE_ADVISORY: dict[str, Any] = {
    "ghsa_id": "GHSA-abcd-1234-wxyz",
    "type": "malware",
    "summary": "Malicious code in fake-package (npm)",
    "description": (
        "Any computer that has this package installed should be considered compromised."
    ),
    "severity": "critical",
    "cve_id": None,
    "published_at": "2026-08-01T12:00:00Z",
    "html_url": "https://github.com/advisories/GHSA-abcd-1234-wxyz",
    "vulnerabilities": [
        {
            "package": {"ecosystem": "npm", "name": "fake-package"},
            "vulnerable_version_range": "<= 1.2.3",
            "first_patched_version": None,
        }
    ],
}


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> Any:
        return self._payload


def test_advisory_case_id_is_safe_for_the_dashboard_router() -> None:
    case_id = advisory_case_id("GHSA-abcd-1234-wxyz")
    assert case_id == "advisory_ghsa-abcd-1234-wxyz"
    assert _SAFE_CASE_ID.match(case_id), "el id debe pasar el patrón anti-traversal del router"


def test_advisory_case_id_strips_unexpected_characters() -> None:
    assert _SAFE_CASE_ID.match(advisory_case_id("GHSA weird/../id"))


def test_advisory_to_markdown_produces_a_corpus_compatible_document(tmp_path: Path) -> None:
    markdown = advisory_to_markdown(_MALWARE_ADVISORY)
    assert markdown is not None
    expected_title = "# Aviso: Malicious code in fake-package (npm) (GHSA-abcd-1234-wxyz)"
    assert markdown.startswith(expected_title)
    assert "`fake-package` (npm)" in markdown
    assert "## Patrón a vigilar" in markdown

    # El mismo parser que usa el dashboard debe extraer título, tipo y resumen.
    path = tmp_path / "advisory_ghsa-abcd-1234-wxyz.md"
    path.write_text(markdown, encoding="utf-8")
    case = _parse_corpus_file(path)
    assert case is not None
    assert case.type == "aviso"
    assert "compromised" in case.summary


def test_advisory_without_id_or_summary_is_skipped() -> None:
    assert advisory_to_markdown({"summary": "sin id"}) is None
    assert advisory_to_markdown({"ghsa_id": "GHSA-x", "summary": "   "}) is None


def test_fetch_advisories_stops_at_last_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una página con menos resultados que el per_page pedido es la última:
    no se pide una página más de propina."""
    calls: list[dict[str, Any]] = []

    def _fake_get(url: str, params: dict[str, Any], **kwargs: Any) -> _FakeResponse:
        calls.append(dict(params))
        return _FakeResponse([{"ghsa_id": "GHSA-only-one", "summary": "s"}])

    monkeypatch.setattr(threat_feed.httpx, "get", _fake_get)

    result = fetch_advisories(ecosystem="npm", limit=5)
    assert [a["ghsa_id"] for a in result] == ["GHSA-only-one"]
    assert len(calls) == 1


def test_fetch_advisories_paginates_when_limit_exceeds_page_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La API sirve 100 por página como máximo: un limit mayor exige una
    segunda petición con el per_page restante."""
    calls: list[dict[str, Any]] = []

    def _fake_get(url: str, params: dict[str, Any], **kwargs: Any) -> _FakeResponse:
        calls.append(dict(params))
        page, per_page = int(params["page"]), int(params["per_page"])
        batch = [{"ghsa_id": f"GHSA-p{page}-{i}", "summary": "s"} for i in range(per_page)]
        return _FakeResponse(batch)

    monkeypatch.setattr(threat_feed.httpx, "get", _fake_get)

    result = fetch_advisories(ecosystem="npm", limit=120)
    assert len(result) == 120
    assert [c["per_page"] for c in calls] == [100, 20]
    assert [c["page"] for c in calls] == [1, 2]


def test_fetch_advisories_network_failure_returns_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    def _fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(threat_feed.httpx, "get", _fake_get)
    assert fetch_advisories(ecosystem="npm", limit=5) == []


def test_sync_writes_files_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        threat_feed,
        "fetch_advisories",
        lambda advisory_type, ecosystem, limit: [_MALWARE_ADVISORY],
    )

    written = sync_advisories_to_corpus(tmp_path, ecosystems=("npm", "pip"))
    # El mismo aviso aparece en los dos ecosistemas -> un solo fichero.
    assert len(written) == 1
    assert written[0].name == "advisory_ghsa-abcd-1234-wxyz.md"

    # Segunda pasada sin cambios: no reescribe nada.
    assert sync_advisories_to_corpus(tmp_path, ecosystems=("npm",)) == []


def test_sync_skips_malformed_advisories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        threat_feed,
        "fetch_advisories",
        lambda advisory_type, ecosystem, limit: [{"ghsa_id": None, "summary": ""}],
    )
    assert sync_advisories_to_corpus(tmp_path, ecosystems=("npm",)) == []
    assert list(tmp_path.glob("*.md")) == []
