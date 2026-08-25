"""Recuperación de contexto relevante para el prompt (§7.4, A.3.2)."""

from __future__ import annotations

import logging
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

logger = logging.getLogger("watchgate.core.rag.retriever")

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


# Cuántos fragmentos se piden por cada hueco final del top-k del corpus,
# para poder deduplicar por caso sin quedarse cortos (ver
# retrieve_relevant_context). ChromaDB recorta a lo que exista.
_DIVERSITY_OVERFETCH_FACTOR = 3


def _query_collection(
    client: Any,
    collection_name: str,
    query_embedding: list[list[float]],
    k: int,
    where: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        collection = client.get_collection(collection_name)
    except Exception as exc:  # noqa: BLE001 - "no existe todavía" y un fallo
        # real de conectividad (p. ej. contra `WATCHGATE_CHROMA_URL` remoto)
        # levantan la misma excepción genérica del cliente de ChromaDB -- sin
        # este log, un problema de red real se ve exactamente igual que
        # "todavía no se ha corrido `watchgate rag reindex`": contexto RAG
        # descartado en silencio en cada análisis, sin ninguna pista de por
        # qué. `debug`, no `warning`: en uso normal de un solo tenant sin
        # feedback aún registrado, esto es un estado legítimo y frecuente.
        logger.debug(
            "No se pudo obtener la colección %r de ChromaDB (¿todavía no existe, o fallo de "
            "conectividad?): %r",
            collection_name,
            exc,
        )
        return [], []

    count = collection.count()
    if count == 0:
        return [], []

    query_kwargs: dict[str, Any] = {"query_embeddings": query_embedding, "n_results": min(k, count)}
    if where is not None:
        query_kwargs["where"] = where
    results = collection.query(**query_kwargs)
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
    org_id: str | None = None,
) -> list[RetrievedFragment]:
    """Consulta el corpus público (`attack_patterns`) y, aparte, la colección
    de casos confirmados por feedback humano (`feedback_cases`), y combina
    los resultados. El feedback tiene hueco garantizado (hasta `feedback_k`,
    por defecto 1): un caso confirmado del propio historial de revisión es la
    señal más directa que existe y no debería quedar fuera solo porque el
    corpus público haya crecido y gane por similitud bruta -- son colecciones
    separadas justo para evitar esa competencia.

    `org_id`: en modo RAG distribuido, `FEEDBACK_COLLECTION_NAME` puede ser
    una única colección compartida entre despliegues/tenants -- sin filtrar
    por `org_id` (ver `feedback.py::add_confirmed_case`), el feedback de un
    tenant se colaría en la recuperación de otro. El corpus público
    (`COLLECTION_NAME`) NUNCA se filtra por org_id -- es intencionalmente
    compartido (investigación pública de casos de ataque conocidos).

    Los `k` resultados del corpus se DIVERSIFICAN por caso (máximo un
    fragmento por `case_name`): un documento largo troceado en varios
    fragmentos parecidos -- o, desde el sync de avisos, decenas de
    documentos `advisory_*` que comparten plantilla -- podía llenar el
    top-k con variaciones de lo mismo y expulsar al segundo/tercer caso
    DISTINTO que sí aporta contexto nuevo al prompt. Se sobre-consulta
    (k * _DIVERSITY_OVERFETCH_FACTOR, ChromaDB ya recorta al tamaño real
    de la colección) y se queda el fragmento más similar de cada caso.

    Devuelve lista vacía si no existe ningún índice todavía (no se ha
    ejecutado `watchgate rag reindex` ni hay ningún caso de feedback)."""
    client = get_chroma_client(index_path=index_path)
    model = _get_embedding_model()
    query_embedding = model.encode([diff_summary]).tolist()

    feedback_where = {"org_id": org_id} if org_id else None
    feedback_docs, feedback_metas = _query_collection(
        client, FEEDBACK_COLLECTION_NAME, query_embedding, feedback_k, where=feedback_where
    )
    corpus_docs, corpus_metas = _query_collection(
        client, COLLECTION_NAME, query_embedding, k * _DIVERSITY_OVERFETCH_FACTOR
    )

    fragments = [
        _to_fragment(text, meta, default_origin="feedback")
        for text, meta in zip(feedback_docs, feedback_metas, strict=True)
    ]
    seen_cases: set[str] = set()
    for text, meta in zip(corpus_docs, corpus_metas, strict=True):
        case_name = str(meta.get("case_name", "desconocido"))
        if case_name in seen_cases:
            continue
        seen_cases.add(case_name)
        fragments.append(_to_fragment(text, meta, default_origin="corpus"))
        if len(seen_cases) >= k:
            break
    return fragments
