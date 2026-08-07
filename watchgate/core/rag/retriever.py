"""Recuperación de contexto relevante para el prompt (§7.4, A.3.2)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from watchgate.core.rag.indexer import (
    COLLECTION_NAME,
    DEFAULT_INDEX_PATH,
    EMBEDDING_MODEL_NAME,
    FEEDBACK_COLLECTION_NAME,
    get_chroma_client,
)

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# Cachea el modelo de embeddings en vez de instanciarlo en cada llamada: cargarlo
# de cero en cada análisis es un coste real evitable, y bajo llamadas concurrentes
# (p. ej. la suite de validación de tests/integration/) instanciar SentenceTransformer
# varias veces a la vez provoca una race condition real de PyTorch al mover el
# modelo a un dispositivo ("Cannot copy out of meta tensor..."), reproducida en la
# práctica. Doble-checked locking: el candado solo se toma en la primera carga.
_embedding_model: SentenceTransformer | None = None
_embedding_model_lock = threading.Lock()


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        with _embedding_model_lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer

                _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model


class RetrievedFragment(BaseModel):
    text: str
    case_name: str
    origin: str = "corpus"
    verdict: str | None = None


def _query_collection(
    client: Any, collection_name: str, query_embedding: list[list[float]], k: int
) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        collection = client.get_collection(collection_name)
    except Exception:  # noqa: BLE001 - la colección puede no existir todavía
        return [], []

    count = collection.count()
    if count == 0:
        return [], []

    results = collection.query(query_embeddings=query_embedding, n_results=min(k, count))
    documents = results.get("documents") or [[]]
    metadatas = results.get("metadatas") or [[]]
    return documents[0], metadatas[0]


def _to_fragment(text: str, meta: dict[str, Any], default_origin: str) -> RetrievedFragment:
    return RetrievedFragment(
        text=text,
        case_name=str(meta.get("case_name", "desconocido")),
        origin=str(meta.get("origin", default_origin)),
        verdict=str(meta["verdict"]) if meta.get("verdict") else None,
    )


def retrieve_relevant_context(
    diff_summary: str,
    k: int = 3,
    index_path: str = DEFAULT_INDEX_PATH,
    feedback_k: int = 1,
) -> list[RetrievedFragment]:
    """Consulta el corpus público (`attack_patterns`) y, aparte, la colección
    de casos confirmados por feedback humano (`feedback_cases`), y combina
    los resultados. El feedback tiene hueco garantizado (hasta `feedback_k`,
    por defecto 1): un caso confirmado del propio historial de revisión es la
    señal más directa que existe y no debería quedar fuera solo porque el
    corpus público haya crecido y gane por similitud bruta -- son colecciones
    separadas justo para evitar esa competencia.

    Devuelve lista vacía si no existe ningún índice todavía (no se ha
    ejecutado `watchgate rag reindex` ni hay ningún caso de feedback)."""
    client = get_chroma_client(index_path=index_path)
    model = _get_embedding_model()
    query_embedding = model.encode([diff_summary]).tolist()

    feedback_docs, feedback_metas = _query_collection(
        client, FEEDBACK_COLLECTION_NAME, query_embedding, feedback_k
    )
    corpus_docs, corpus_metas = _query_collection(client, COLLECTION_NAME, query_embedding, k)

    fragments = [
        _to_fragment(text, meta, default_origin="feedback")
        for text, meta in zip(feedback_docs, feedback_metas, strict=True)
    ]
    fragments += [
        _to_fragment(text, meta, default_origin="corpus")
        for text, meta in zip(corpus_docs, corpus_metas, strict=True)
    ]
    return fragments
