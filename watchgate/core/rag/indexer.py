"""Indexado del corpus local en ChromaDB (§7.4, A.3.2).

Lee el corpus de casos documentados (`core/rag/corpus/*.md`), lo trocea,
genera embeddings con sentence-transformers (CPU, sin API externa) y los
persiste en una colección ChromaDB local. Este indexado se ejecuta una vez
(`watchgate rag reindex`), no en cada análisis de PR.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
DEFAULT_INDEX_PATH = ".watchgate/rag_index"
COLLECTION_NAME = "attack_patterns"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# ~200-300 tokens de referencia en la spec; sin tokenizer a mano, se aproxima
# con un tamaño en caracteres (~4 caracteres/token de media en inglés/español).
_CHUNK_SIZE_CHARS = 1000
_CHUNK_OVERLAP_CHARS = 100


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

    from sentence_transformers import SentenceTransformer

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

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    embeddings = model.encode(texts).tolist()

    client = chromadb.PersistentClient(path=index_path)
    # Reindex limpio: si un documento encoge entre dos ejecuciones, sus
    # fragmentos sobrantes no deben quedar huérfanos en la colección.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:  # noqa: BLE001 - no existe todavía en la primera ejecución
        pass
    collection = client.create_collection(COLLECTION_NAME)
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(ids)


if __name__ == "__main__":
    count = build_index()
    print(f"Indexados {count} fragmentos en '{COLLECTION_NAME}' ({DEFAULT_INDEX_PATH}).")
