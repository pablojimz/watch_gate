"""Ejercita la Engine DB (`watchgate/db/`) contra un Postgres real, mismo
motivo que `test_dashboard_postgres.py` para la Dashboard DB: el esquema/las
funciones que la usan deben funcionar de verdad contra Postgres, no solo
contra SQLite.

Se salta automáticamente (no falla) si `WATCHGATE_DATABASE_URL` no apunta a
Postgres -- mismo patrón de `pytestmark` que `test_dashboard_postgres.py`,
pero con la variable de entorno de la Engine DB (`watchgate.db.connection`),
no `WATCHGATE_DASHBOARD_DATABASE_URL` (esa es de la Dashboard DB, un
esquema/base de datos distinto -- ver el docstring de
`compute_agent_metrics()` en `watchgate/dashboard/backend/db.py`).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlmodel import Session

pytestmark = pytest.mark.skipif(
    not os.environ.get("WATCHGATE_DATABASE_URL", "").startswith(("postgres://", "postgresql://")),
    reason="WATCHGATE_DATABASE_URL no apunta a Postgres.",
)


@pytest.fixture()
def engine_session():
    from watchgate.db.connection import build_engine, init_db

    # Motor propio (no el singleton `default_engine`, ya construido al
    # importar `watchgate.db.connection` -- fijar la variable de entorno
    # aquí no tendría ningún efecto sobre él, mismo motivo que
    # `test_dashboard_api_keys.py` parchea `default_engine` en vez de
    # depender de la variable de entorno para la app real).
    engine = build_engine(os.environ["WATCHGATE_DATABASE_URL"])
    init_db(engine)
    with Session(engine) as session:
        yield session


def test_compute_agent_metrics_aggregates_in_postgres(engine_session: Session) -> None:
    """compute_agent_metrics() pasó de traer TODO `pr_scores`/
    `user_token_usage` fila a fila y sumar en Python a AVG()/SUM()/GROUP BY
    en SQL (perf(dashboard): agregación en SQL en vez de en Python, mismo
    patrón que compute_org_metrics()). Merece un test contra Postgres real
    y no solo SQLite porque `AVG()` sobre una columna INTEGER devuelve
    `NUMERIC` (`Decimal` en psycopg), no `float` como en SQLite --
    `compute_agent_metrics()` convierte explícitamente con `float()` antes
    de `round()` (ver su código) para no propagar ese `Decimal` por el
    resto de la función. Nota: en la práctica, quitar ese `float()` no
    hace que este test falle con una excepción -- Pydantic coacciona
    `Decimal` a `float` en silencio al construir `AgentMetricRow`, así que
    el fallo real de omitir la conversión sería de tipado (mypy) o de un
    futuro cambio que combine ese valor con un `float` nativo en Python
    puro (`Decimal + float` sí lanza `TypeError`, a diferencia de
    `Decimal + int`). Este test fija igualmente el comportamiento numérico
    esperado contra Postgres real, no solo contra SQLite."""
    from watchgate.dashboard.backend.db import compute_agent_metrics
    from watchgate.db.models import PRScore
    from watchgate.db.repository import record_token_usage

    agent_a = f"agent-{uuid.uuid4().hex[:8]}"
    agent_b = f"agent-{uuid.uuid4().hex[:8]}"

    # `total_tokens_used` sí suma sobre TODA la tabla (no hay filtro por
    # agente/organización, a diferencia de `compute_org_metrics()` que
    # filtra por `repos`) -- contra este Postgres real y compartido puede
    # haber filas de otras ejecuciones de este mismo test. Se compara por
    # delta contra una línea base, no por un valor absoluto.
    baseline_total_tokens = compute_agent_metrics(engine_session).total_tokens_used

    def _seed_score(pr_id: str, agent_id: str, score: int) -> None:
        engine_session.add(
            PRScore(
                id=f"{agent_id}-{pr_id}",
                repo="acme/repo",
                pr_id=pr_id,
                agent_id=agent_id,
                score=score,
                semaforo="verde",
                layer_results_json="{}",
                weights_used_json="{}",
            )
        )
        engine_session.commit()

    _seed_score("1", agent_a, 10)
    _seed_score("2", agent_a, 25)
    _seed_score("3", agent_b, 99)

    record_token_usage(engine_session, user_id=agent_a, tokens_used=100, month="2026-06")
    record_token_usage(engine_session, user_id=agent_a, tokens_used=50, month="2026-07")

    metrics = compute_agent_metrics(engine_session)

    by_agent = {row.agent_id: row for row in metrics.by_agent}
    assert agent_a in by_agent
    assert agent_b in by_agent

    row_a = by_agent[agent_a]
    assert row_a.analyses_count == 2
    assert row_a.avg_score == 17.5  # (10 + 25) / 2, vía AVG() de Postgres real
    assert isinstance(row_a.avg_score, float)
    assert row_a.tokens_used == 150

    row_b = by_agent[agent_b]
    assert row_b.analyses_count == 1
    assert row_b.avg_score == 99.0
    assert row_b.tokens_used == 0

    assert metrics.total_tokens_used - baseline_total_tokens == 150
