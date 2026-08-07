"""Incorporación dinámica de casos confirmados por revisión humana al RAG.

El corpus estático en `core/rag/corpus/` está versionado y se rehace entero
con `build_index()`. Este módulo es el otro lado del bucle de feedback descrito
en la arquitectura: cuando el dashboard confirma el veredicto de un análisis
(verdadero positivo o falso positivo), ese caso se trocea, se embebe y se
upsertea en su propia colección (`FEEDBACK_COLLECTION_NAME`), separada del
corpus público. Los casos de feedback son estado de la instancia (viven bajo
`.watchgate/`, igual que el propio índice) y no se comitean.

Colección separada a propósito: el corpus público crece con investigación
general y puede llegar a tener muchas entradas; un caso confirmado del propio
historial de revisión es la señal más directa que existe y no debería competir
por hueco en el top-k contra el corpus general. retriever.py consulta ambas
colecciones y garantiza hueco para el feedback en vez de dejar que compita.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from watchgate.core.rag.indexer import (
    DEFAULT_INDEX_PATH,
    EMBEDDING_MODEL_NAME,
    FEEDBACK_COLLECTION_NAME,
    chunk_document,
    get_chroma_client,
)

DEFAULT_FEEDBACK_DIR = ".watchgate/rag_feedback"

Verdict = Literal["true_positive", "false_positive"]

_SAFE_CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

_VERDICT_LABELS: dict[Verdict, str] = {
    "true_positive": "CONFIRMADO COMO RIESGO REAL",
    "false_positive": "CONFIRMADO COMO FALSO POSITIVO",
}


def _render_feedback_document(case_id: str, title: str, narrative: str, verdict: Verdict) -> str:
    label = _VERDICT_LABELS[verdict]
    return f"# {title}\n\n[{label}] (caso {case_id}, revisado por un humano)\n\n{narrative}"


def add_confirmed_case(
    case_id: str,
    title: str,
    narrative: str,
    verdict: Verdict,
    index_path: str = DEFAULT_INDEX_PATH,
    feedback_dir: str = DEFAULT_FEEDBACK_DIR,
) -> int:
    """Añade (o actualiza, si `case_id` ya existía) un caso confirmado por un
    humano al índice RAG sin rehacer el resto de la colección. Devuelve el
    número de fragmentos añadidos.

    `case_id` se usa tal cual como nombre de fichero (`feedback_dir/{case_id}.md`)
    y como filtro de metadata en ChromaDB: un valor con `/` o `..` podría escribir
    fuera de `feedback_dir` (inyección de ruta), así que se restringe a un
    charset seguro antes de tocar el sistema de ficheros.
    """
    if not _SAFE_CASE_ID_PATTERN.match(case_id):
        raise ValueError(
            f"case_id inválido: {case_id!r}. Solo se permiten letras, números, "
            "'-' y '_' (evita rutas como '../otro/caso')."
        )

    content = _render_feedback_document(case_id, title, narrative, verdict)

    feedback_path = Path(feedback_dir)
    feedback_path.mkdir(parents=True, exist_ok=True)
    (feedback_path / f"{case_id}.md").write_text(content, encoding="utf-8")

    chunks = chunk_document(content)
    if not chunks:
        return 0

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    embeddings = model.encode(chunks).tolist()

    ids = [f"feedback-{case_id}-{i}" for i in range(len(chunks))]
    metadatas: list[Mapping[str, str | int | float | bool]] = [
        {
            "source": "feedback",
            "case_name": title,
            "origin": "feedback",
            "case_id": case_id,
            "verdict": str(verdict),
        }
        for _ in chunks
    ]

    client = get_chroma_client(index_path=index_path)
    try:
        collection = client.get_collection(FEEDBACK_COLLECTION_NAME)
    except Exception:  # noqa: BLE001 - todavía no existe esta colección
        collection = client.create_collection(FEEDBACK_COLLECTION_NAME)

    # Si el caso ya existía (se está corrigiendo o ampliando el veredicto) y
    # ahora tiene menos fragmentos, los sobrantes de la versión anterior no
    # deben quedar huérfanos en la colección (mismo problema que en build_index,
    # pero a nivel de un único documento en vez de todo el corpus).
    collection.delete(where={"case_id": case_id})
    collection.upsert(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    return len(ids)
