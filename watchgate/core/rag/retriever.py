"""Recuperación de contexto relevante para el prompt (§7.4, A.3.2)."""

from __future__ import annotations

from pydantic import BaseModel

from watchgate.core.rag.indexer import COLLECTION_NAME, DEFAULT_INDEX_PATH, EMBEDDING_MODEL_NAME


class RetrievedFragment(BaseModel):
    text: str
    case_name: str
    origin: str = "corpus"
    verdict: str | None = None


def retrieve_relevant_context(
    diff_summary: str, k: int = 3, index_path: str = DEFAULT_INDEX_PATH
) -> list[RetrievedFragment]:
    """Consulta la colección `attack_patterns` y devuelve hasta `k` fragmentos
    relevantes para `diff_summary`. Devuelve lista vacía si el índice no
    existe todavía (no se ha ejecutado `watchgate rag reindex`)."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=index_path)
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        return []

    count = collection.count()
    if count == 0:
        return []

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    query_embedding = model.encode([diff_summary]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=min(k, count))

    documents = results.get("documents") or [[]]
    metadatas = results.get("metadatas") or [[]]
    return [
        RetrievedFragment(
            text=text,
            case_name=str(meta.get("case_name", "desconocido")),
            origin=str(meta.get("origin", "corpus")),
            verdict=str(meta["verdict"]) if meta.get("verdict") else None,
        )
        for text, meta in zip(documents[0], metadatas[0], strict=True)
    ]
