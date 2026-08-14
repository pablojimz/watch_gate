"""Indexado del corpus local en ChromaDB (§7.4, A.3.2).

Lee el corpus de casos documentados (`core/rag/corpus/*.md`), lo trocea,
genera embeddings con sentence-transformers (CPU, sin API externa) y los
persiste en una colección ChromaDB local. Este indexado se ejecuta una vez
(`watchgate rag reindex`), no en cada análisis de PR.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
DEFAULT_INDEX_PATH = ".watchgate/rag_index"
COLLECTION_NAME = "attack_patterns"
# Colección separada para casos confirmados por revisión humana (rag/feedback.py).
# Vive en el mismo cliente/ruta persistida que COLLECTION_NAME -- ChromaDB permite
# varias colecciones nombradas dentro de un mismo PersistentClient -- pero aparte,
# para que el corpus público (grande, en crecimiento) nunca desplace a un caso
# confirmado del propio historial de revisión, que es la señal más directa que
# existe. retriever.py consulta las dos y las combina.
FEEDBACK_COLLECTION_NAME = "feedback_cases"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Sin esto, `create_collection` usa el default de ChromaDB (L2 al cuadrado),
# pensado para embeddings arbitrarios -- no para los que produce
# sentence-transformers, que se comparan por similitud coseno (el propio
# model card de `all-MiniLM-L6-v2` lo especifica). Reproducido en vivo:
# con L2 las distancias de consultas relevantes e irrelevantes caían en la
# misma banda estrecha (~0.9-1.4) sin separación real -- una consulta de
# "typo en el README", totalmente benigna, salía más "cercana" a un caso de
# ataque que una consulta de un ataque real genérico. `hnsw:space: cosine`
# hace que ChromaDB normalice internamente antes de comparar, dando una
# métrica acotada [0, 2] mucho más discriminativa.
COLLECTION_METADATA: dict[str, str] = {"hnsw:space": "cosine"}

# ~200-300 tokens de referencia en la spec; sin tokenizer a mano, se aproxima
# con un tamaño en caracteres (~4 caracteres/token de media en inglés/español).
_CHUNK_SIZE_CHARS = 1000
_CHUNK_OVERLAP_CHARS = 100


def get_chroma_client(index_path: str = DEFAULT_INDEX_PATH) -> Any:
    """Retorna un cliente de ChromaDB.

    Si la variable de entorno `WATCHGATE_CHROMA_URL` (o `CHROMA_URL`) está definida,
    instancia un `chromadb.HttpClient` para RAG distribuido en la nube / VPC.
    En caso contrario, utiliza `chromadb.PersistentClient(path=index_path)`.
    """
    chroma_url = os.environ.get("WATCHGATE_CHROMA_URL") or os.environ.get("CHROMA_URL")
    if chroma_url:
        parsed = urlparse(chroma_url)
        host = parsed.hostname or chroma_url
        port = parsed.port or (443 if parsed.scheme == "https" else 8000)
        ssl = parsed.scheme == "https"
        return chromadb.HttpClient(host=host, port=port, ssl=ssl)
    return chromadb.PersistentClient(path=index_path)


def load_corpus_documents(corpus_dir: Path = CORPUS_DIR) -> list[tuple[str, str]]:
    """Devuelve (case_name, contenido) por cada .md del corpus, uno por caso."""
    return [
        (path.stem, path.read_text(encoding="utf-8")) for path in sorted(corpus_dir.glob("*.md"))
    ]


def chunk_document(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE_CHARS, chunk_overlap=_CHUNK_OVERLAP_CHARS
    )
    return splitter.split_text(text)


def build_index(corpus_dir: Path = CORPUS_DIR, index_path: str = DEFAULT_INDEX_PATH) -> int:
    """Trocea el corpus, genera embeddings y los persiste en la colección
    `attack_patterns` de ChromaDB. Devuelve el número de fragmentos indexados."""
    documents = load_corpus_documents(corpus_dir)
    if not documents:
        return 0

    # Import diferido (evita el ciclo indexer<->retriever a nivel de módulo,
    # retriever.py ya importa de aquí) para reusar el mismo modelo cacheado
    # con locking que usa `retrieve_relevant_context` en cada análisis real
    # -- sin esto, cada `watchgate rag reindex` cargaba de disco una
    # instancia de SentenceTransformer aparte (coste real, no solo teórico:
    # cientos de ms a segundos) que nunca se reutilizaba.
    from watchgate.core.rag.retriever import _get_embedding_model

    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[Mapping[str, str | int | float | bool]] = []
    for case_name, content in documents:
        for i, chunk in enumerate(chunk_document(content)):
            ids.append(f"{case_name}-{i}")
            texts.append(chunk)
            metadatas.append(
                {"source": f"{case_name}.md", "case_name": case_name, "origin": "corpus"}
            )

    model = _get_embedding_model()
    embeddings = model.encode(texts).tolist()

    client = get_chroma_client(index_path=index_path)
    # Reindex limpio: si un documento encoge entre dos ejecuciones, sus
    # fragmentos sobrantes no deben quedar huérfanos en la colección.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:  # noqa: BLE001 - no existe todavía en la primera ejecución
        pass
    collection = client.create_collection(COLLECTION_NAME, metadata=COLLECTION_METADATA)
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(ids)


if __name__ == "__main__":
    count = build_index()
    print(f"Indexados {count} fragmentos en '{COLLECTION_NAME}' ({DEFAULT_INDEX_PATH}).")
