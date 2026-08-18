"""Tests unitarios para `compute_agent_metrics()`
(watchgate/dashboard/backend/db.py).

Antes de esta migración a agregación SQL (mismo patrón que
`compute_org_metrics()`, perf(dashboard): agregación en SQL en vez de en
Python) esta función no tenía cobertura dedicada -- ni unitaria ni de
integración. Se añade aquí, contra la Engine DB en SQLite en memoria
(mismo patrón que `tests/unit/test_mcp_server.py`/`test_quota_degraded.py`),
cubriendo en particular los casos que un GROUP BY/unión mal hecha podría
romper en silencio: un agente que solo tiene `PRScore` pero ningún
`UserTokenUsage` (o viceversa), y consumo de tokens repartido en varios
meses para el mismo `user_id`.
"""

from __future__ import annotations

from sqlmodel import Session, create_engine

from watchgate.dashboard.backend.db import compute_agent_metrics
from watchgate.db.connection import init_db
from watchgate.db.models import PRScore
from watchgate.db.repository import record_token_usage


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(engine)
    return Session(engine)


def _seed_pr_score(session: Session, *, id_: str, agent_id: str | None, score: int) -> None:
    session.add(
        PRScore(
            id=id_,
            repo="acme/repo",
            pr_id=id_,
            agent_id=agent_id,
            score=score,
            semaforo="verde",
            layer_results_json="{}",
            weights_used_json="{}",
        )
    )
    session.commit()


def test_compute_agent_metrics_defaults_to_default_agent_when_empty() -> None:
    """Sin ningún PRScore/UserTokenUsage, `all_agent_ids` cae al fallback
    `{"default-agent"}` -- comportamiento preexistente, preservado tal cual
    por la migración a SQL."""
    session = _memory_session()

    metrics = compute_agent_metrics(session)

    assert metrics.agents_count == 1
    assert metrics.total_tokens_used == 0
    row = metrics.by_agent[0]
    assert row.agent_id == "default-agent"
    assert row.analyses_count == 0
    assert row.avg_score == 0.0
    assert row.tokens_used == 0


def test_compute_agent_metrics_ignores_null_and_empty_agent_id() -> None:
    """El filtro `agent_id IS NOT NULL AND agent_id != ''` debe seguir
    excluyendo filas sin agente real, igual que antes de la migración a
    SQL (ahora expresado en el `WHERE` de la propia consulta agregada)."""
    session = _memory_session()
    _seed_pr_score(session, id_="1", agent_id=None, score=10)
    _seed_pr_score(session, id_="2", agent_id="", score=20)
    _seed_pr_score(session, id_="3", agent_id="agent-a", score=30)

    metrics = compute_agent_metrics(session)

    assert metrics.agents_count == 1
    row = metrics.by_agent[0]
    assert row.agent_id == "agent-a"
    assert row.analyses_count == 1
    assert row.avg_score == 30.0


def test_compute_agent_metrics_multiple_agents_group_by_and_average() -> None:
    """Más de un agente con más de una fila cada uno -- ejercita de verdad
    el `GROUP BY agent_id` (no solo el caso trivial de una fila)."""
    session = _memory_session()
    _seed_pr_score(session, id_="1", agent_id="agent-a", score=10)
    _seed_pr_score(session, id_="2", agent_id="agent-a", score=30)
    _seed_pr_score(session, id_="3", agent_id="agent-b", score=51)
    _seed_pr_score(session, id_="4", agent_id="agent-b", score=52)
    _seed_pr_score(session, id_="5", agent_id="agent-b", score=53)

    metrics = compute_agent_metrics(session)

    by_agent = {row.agent_id: row for row in metrics.by_agent}
    assert metrics.agents_count == 2
    assert by_agent["agent-a"].analyses_count == 2
    assert by_agent["agent-a"].avg_score == 20.0
    assert by_agent["agent-b"].analyses_count == 3
    # (51 + 52 + 53) / 3 = 52.0 -- redondeo a 1 decimal no debería alterar
    # un resultado exacto.
    assert by_agent["agent-b"].avg_score == 52.0


def test_compute_agent_metrics_unions_score_only_and_token_only_agents() -> None:
    """`agent_id` (pr_scores) y `user_id` (user_token_usage) comparten el
    mismo espacio de claves -- comportamiento preexistente, no algo que
    "arreglar" aquí. Un agente con analyses pero sin tokens, o con tokens
    pero sin analyses, debe seguir apareciendo en el resultado (la UNIÓN de
    ambos conjuntos), y el consumo de tokens de varios meses del mismo
    user_id debe sumarse, no quedarse solo con el último mes."""
    session = _memory_session()
    _seed_pr_score(session, id_="1", agent_id="agent-with-only-scores", score=40)
    record_token_usage(session, user_id="agent-with-only-tokens", tokens_used=100, month="2026-06")
    record_token_usage(session, user_id="agent-with-only-tokens", tokens_used=50, month="2026-07")
    record_token_usage(session, user_id="agent-with-only-scores", tokens_used=25, month="2026-06")

    metrics = compute_agent_metrics(session)

    by_agent = {row.agent_id: row for row in metrics.by_agent}
    assert metrics.agents_count == 2

    scores_only = by_agent["agent-with-only-scores"]
    assert scores_only.analyses_count == 1
    assert scores_only.avg_score == 40.0
    assert scores_only.tokens_used == 25

    tokens_only = by_agent["agent-with-only-tokens"]
    assert tokens_only.analyses_count == 0
    assert tokens_only.avg_score == 0.0
    assert tokens_only.tokens_used == 150

    assert metrics.total_tokens_used == 175
