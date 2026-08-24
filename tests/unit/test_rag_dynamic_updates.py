"""Tests del RAG dinámico: sync periódico de avisos + indexado del feedback.

Cubre el cableado nuevo (tasks.run_rag_sync / tasks.run_feedback_indexing /
routers.feedback._enqueue_feedback_indexing / main._rag_sync_interval_hours),
con las piezas pesadas (red, embeddings, ChromaDB) monkeypatcheadas -- el
comportamiento real de `add_confirmed_case` ya lo cubre test_rag_feedback.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from watchgate.core.models import Semaforo
from watchgate.dashboard.backend import tasks
from watchgate.dashboard.backend.main import _rag_sync_interval_hours
from watchgate.dashboard.backend.routers import feedback as feedback_router
from watchgate.dashboard.backend.schemas import ScoreOut


def _score(feedback: str = "correcto", justification: str = "Riesgo confirmado.") -> ScoreOut:
    return ScoreOut(
        id=7,
        score=85,
        semaforo=Semaforo.ROJO,
        layer_results={"semantic": {"justification": justification}},
        weights_used={},
        pr_id="42",
        repo="acme/widgets",
        timestamp="2026-08-24T12:00:00",
        human_feedback=feedback,  # type: ignore[arg-type]
    )


class _FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def enqueue(self, *args):
        self.calls.append(args)


def test_run_rag_sync_skips_reindex_when_no_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    import watchgate.core.rag.indexer as indexer
    import watchgate.core.rag.threat_feed as threat_feed

    monkeypatch.setattr(threat_feed, "sync_advisories_to_corpus", lambda corpus_dir: [])
    monkeypatch.setattr(
        indexer,
        "build_index",
        lambda *a, **k: pytest.fail("no debe reindexar sin cambios en el corpus"),
    )
    tasks.run_rag_sync()


def test_run_rag_sync_reindexes_when_new_advisories_arrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import watchgate.core.rag.indexer as indexer
    import watchgate.core.rag.threat_feed as threat_feed

    reindexed: list[bool] = []
    monkeypatch.setattr(
        threat_feed,
        "sync_advisories_to_corpus",
        lambda corpus_dir: [Path("advisory_ghsa-nuevo.md")],
    )
    monkeypatch.setattr(indexer, "build_index", lambda *a, **k: reindexed.append(True) or 3)
    tasks.run_rag_sync()
    assert reindexed == [True]


def test_run_feedback_indexing_calls_add_confirmed_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import watchgate.core.rag.feedback as rag_feedback

    calls: list[dict] = []
    monkeypatch.setattr(
        rag_feedback,
        "add_confirmed_case",
        lambda **kwargs: calls.append(kwargs) or 2,
    )
    tasks.run_feedback_indexing("score_7", "Un título", "Una narrativa", "true_positive")
    assert len(calls) == 1
    assert calls[0]["case_id"] == "score_7"
    assert calls[0]["verdict"] == "true_positive"


def test_run_feedback_indexing_ignores_unknown_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import watchgate.core.rag.feedback as rag_feedback

    monkeypatch.setattr(
        rag_feedback,
        "add_confirmed_case",
        lambda **kwargs: pytest.fail("no debe indexar un verdict desconocido"),
    )
    tasks.run_feedback_indexing("score_7", "t", "n", "loquesea")


def test_enqueue_feedback_indexing_maps_feedback_to_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = _FakeQueue()
    monkeypatch.setattr(tasks, "get_queue", lambda: queue)

    feedback_router._enqueue_feedback_indexing(_score(feedback="correcto"))
    feedback_router._enqueue_feedback_indexing(_score(feedback="falso_positivo"))

    assert len(queue.calls) == 2
    task_path, case_id, title, narrative, verdict = queue.calls[0]
    assert task_path == "watchgate.dashboard.backend.tasks.run_feedback_indexing"
    assert case_id == "score_7"
    assert "acme/widgets" in title
    assert "Riesgo confirmado." in narrative
    assert "85/100" in narrative
    assert verdict == "true_positive"
    assert queue.calls[1][4] == "false_positive"


def test_enqueue_feedback_indexing_never_breaks_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El feedback ya quedó guardado en la BD cuando se encola el indexado:
    Redis caído no debe convertir el click del revisor en un 500."""

    def _broken_queue():
        raise ConnectionError("redis caído")

    monkeypatch.setattr(tasks, "get_queue", _broken_queue)
    feedback_router._enqueue_feedback_indexing(_score())  # no debe lanzar


def test_rag_sync_interval_default_invalid_and_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WATCHGATE_RAG_SYNC_INTERVAL_HOURS", raising=False)
    assert _rag_sync_interval_hours() == 24.0
    monkeypatch.setenv("WATCHGATE_RAG_SYNC_INTERVAL_HOURS", "abc")
    assert _rag_sync_interval_hours() == 24.0
    monkeypatch.setenv("WATCHGATE_RAG_SYNC_INTERVAL_HOURS", "0")
    assert _rag_sync_interval_hours() == 0.0
    monkeypatch.setenv("WATCHGATE_RAG_SYNC_INTERVAL_HOURS", "6")
    assert _rag_sync_interval_hours() == 6.0
