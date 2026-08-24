"""Tests de GET /api/rag/corpus (watchgate/dashboard/backend/routers/rag.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from watchgate.dashboard.backend.routers.rag import (
    _CORPUS_DIR,
    _infer_type,
    _parse_corpus_file,
    get_rag_corpus_case,
    list_rag_corpus,
)


def test_infer_type_matches_each_known_prefix():
    assert _infer_type("Caso: algo") == "caso_real"
    assert _infer_type("MITRE ATT&CK T1027 — algo") == "mitre_attck"
    assert _infer_type("Técnica: algo") == "tecnica"
    assert _infer_type("Patrón: algo") == "patron"
    assert _infer_type("Aviso: Malicious code in x (npm) (GHSA-xxxx)") == "aviso"
    assert _infer_type("Un título cualquiera") == "otro"


def test_parse_corpus_file_extracts_title_type_and_first_paragraph(tmp_path):
    case_file = tmp_path / "example.md"
    case_file.write_text(
        "# Caso: ejemplo sintético\n"
        "\n"
        "## Resumen\n"
        "\n"
        "Primer párrafo con la explicación real del caso, en\n"
        "varias líneas de texto.\n"
        "\n"
        "## Otra sección\n"
        "\n"
        "Este contenido no debe aparecer en el resumen.\n",
        encoding="utf-8",
    )

    case = _parse_corpus_file(case_file)

    assert case is not None
    assert case.id == "example"
    assert case.title == "Caso: ejemplo sintético"
    assert case.type == "caso_real"
    assert (
        case.summary
        == "Primer párrafo con la explicación real del caso, en varias líneas de texto."
    )
    assert "no debe aparecer" not in case.summary


def test_parse_corpus_file_handles_descripcion_heading_too(tmp_path):
    """Algunos ficheros del corpus usan "## Descripción" en vez de
    "## Resumen" -- el parser no debe asumir un nombre de sección fijo."""
    case_file = tmp_path / "example.md"
    case_file.write_text(
        "# MITRE ATT&CK T9999 — Técnica sintética\n\n## Descripción\n\nTexto del resumen.\n",
        encoding="utf-8",
    )

    case = _parse_corpus_file(case_file)

    assert case is not None
    assert case.type == "mitre_attck"
    assert case.summary == "Texto del resumen."


def test_parse_corpus_file_returns_none_without_h1_title(tmp_path):
    case_file = tmp_path / "no_title.md"
    case_file.write_text("## Resumen\n\nSin encabezado de nivel 1.\n", encoding="utf-8")

    assert _parse_corpus_file(case_file) is None


def test_real_corpus_directory_parses_cleanly_end_to_end():
    """Contra el corpus real del repo (no un fixture sintético) -- si algún
    fichero real rompe el parser (encabezado inesperado, encoding...), este
    test lo detecta antes que un usuario viendo la página vacía."""
    assert _CORPUS_DIR.is_dir()
    md_files = list(_CORPUS_DIR.glob("*.md"))
    assert len(md_files) > 0

    cases = list_rag_corpus(_user=None)  # type: ignore[arg-type]

    assert len(cases) == len(md_files)
    for case in cases:
        assert case.title
        assert case.type in {"caso_real", "aviso", "mitre_attck", "tecnica", "patron", "otro"}
        # No todos los ficheros garantizan un resumen no vacío (dependería
        # de la estructura exacta), pero sí un id derivado del nombre real.
        assert case.id
        assert Path(_CORPUS_DIR / f"{case.id}.md").is_file()


def test_get_rag_corpus_case_returns_full_markdown_content():
    detail = get_rag_corpus_case("xz_utils", _user=None)  # type: ignore[arg-type]

    assert detail.id == "xz_utils"
    assert detail.title.startswith("Caso: backdoor en xz-utils")
    assert "## Resumen" in detail.content
    # `content` es el markdown crudo (con saltos de línea reales dentro de
    # cada párrafo), `summary` es la misma frase ya normalizada a una sola
    # línea (ver _parse_corpus_file) -- no son substring exacto una de la
    # otra a propósito, comparamos sin espacios para verificar que es el
    # mismo texto real.
    assert "".join(detail.summary.split()) in "".join(detail.content.split())


def test_get_rag_corpus_case_404s_on_unknown_id():
    with pytest.raises(HTTPException) as exc_info:
        get_rag_corpus_case("no_existe_este_caso", _user=None)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 404


@pytest.mark.parametrize(
    "malicious_id",
    [
        "../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "foo/bar",
        "foo\\bar",
        "",
    ],
)
def test_get_rag_corpus_case_rejects_path_traversal_attempts(malicious_id):
    """`case_id` viaja en la URL -- validado contra un patrón cerrado ANTES
    de construir la ruta al fichero, no solo confiando en que el fichero
    resultante no exista."""
    with pytest.raises(HTTPException) as exc_info:
        get_rag_corpus_case(malicious_id, _user=None)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 404
