"""rag.py — expone el corpus de casos documentados que alimenta la capa
semántica/RAG (`watchgate/core/rag/corpus/*.md`), para que el dashboard
pueda mostrar de qué información dispone el sistema al buscar patrones
similares -- antes esto era invisible fuera del propio repositorio.

Lee los ficheros .md directamente (sin pasar por `watchgate.core.rag.indexer`,
que arrastra chromadb/langchain-text-splitters para el troceado/embebido real
del índice) porque aquí solo hace falta el título y un resumen corto de cada
caso, no reconstruir el índice vectorial -- este endpoint no necesita que el
índice esté siquiera construido (`watchgate rag reindex` puede no haberse
ejecutado nunca) para funcionar."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from watchgate.dashboard.backend.auth import CurrentUser

router = APIRouter(tags=["rag"])

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9_-]+$")

# Mismo directorio que CORPUS_DIR en core/rag/indexer.py -- no se importa
# esa constante para no arrastrar el import de chromadb (ver docstring del
# módulo).
_CORPUS_DIR = Path(__file__).resolve().parents[4] / "watchgate" / "core" / "rag" / "corpus"

_TYPE_PREFIXES: dict[str, str] = {
    "Caso:": "caso_real",
    "MITRE ATT&CK": "mitre_attck",
    "Técnica:": "tecnica",
    "Patrón:": "patron",
}


class RagCorpusCase(BaseModel):
    id: str
    title: str
    type: str
    summary: str


class RagCorpusCaseDetail(RagCorpusCase):
    content: str


def _infer_type(title: str) -> str:
    for prefix, type_key in _TYPE_PREFIXES.items():
        if title.startswith(prefix):
            return type_key
    return "otro"


def _parse_corpus_file(path: Path) -> RagCorpusCase | None:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_match is None:
        return None
    title = title_match.group(1).strip()

    # Resumen = primer párrafo tras el primer encabezado H2 ("## Resumen",
    # "## Descripción"...) -- no asumimos el nombre exacto de esa sección,
    # varía entre "Resumen" y "Descripción" según el fichero.
    after_h1 = text[title_match.end() :]
    h2_match = re.search(r"^##\s+.+$", after_h1, re.MULTILINE)
    summary = ""
    if h2_match is not None:
        after_h2 = after_h1[h2_match.end() :].lstrip("\n")
        paragraph_end = after_h2.find("\n\n")
        summary = (after_h2 if paragraph_end == -1 else after_h2[:paragraph_end]).strip()
        summary = re.sub(r"\s+", " ", summary)

    return RagCorpusCase(id=path.stem, title=title, type=_infer_type(title), summary=summary)


@router.get("/rag/corpus", response_model=list[RagCorpusCase])
def list_rag_corpus(_user: CurrentUser) -> list[RagCorpusCase]:
    if not _CORPUS_DIR.is_dir():
        return []
    cases = [
        case
        for path in sorted(_CORPUS_DIR.glob("*.md"))
        if (case := _parse_corpus_file(path)) is not None
    ]
    return sorted(cases, key=lambda c: c.title)


@router.get("/rag/corpus/{case_id}", response_model=RagCorpusCaseDetail)
def get_rag_corpus_case(case_id: str, _user: CurrentUser) -> RagCorpusCaseDetail:
    # `case_id` viaja en la URL, controlado por quien llame -- validado
    # contra un patrón cerrado (mismo alfabeto que un nombre de fichero real
    # de este corpus) ANTES de construir la ruta, no después: evita
    # traversal de directorio (`../../etc/passwd`) sin depender solo de que
    # `.resolve()` lo detecte más tarde.
    if not _SAFE_CASE_ID.match(case_id):
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    path = _CORPUS_DIR / f"{case_id}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    case = _parse_corpus_file(path)
    if case is None:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    return RagCorpusCaseDetail(**case.model_dump(), content=path.read_text(encoding="utf-8"))
