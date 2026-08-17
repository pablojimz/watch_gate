"""Ejercita el Dashboard DB (`watchgate/dashboard/backend/db.py`) contra un
Postgres real (spec §13, migración a ORM).

Antes esto vivía en `tests/unit/test_db_postgres.py`, probando el wrapper
`db_postgres.PostgresConnection` (traducción de placeholders `?`->`%s`,
pool de conexiones) sin conexión real -- ese módulo ya no existe: el
Dashboard DB usa el mismo motor SQLAlchemy 2.0 ORM que la Engine DB en
ambos dialectos (`watchgate.db.connection.build_engine`, que ya resuelve
`postgresql+psycopg://`), así que ya no hay traducción de SQL propia que
probar de forma aislada. Lo que sí merece un test dedicado es que el
esquema/las ~40 funciones de `db.py` funcionan de verdad contra Postgres,
no solo contra SQLite -- el job `postgres-test` de CI
(`.github/workflows/ci.yml`) levanta un servicio Postgres real y fija
`WATCHGATE_DASHBOARD_DATABASE_URL` antes de correr este fichero.

Se salta automáticamente (no falla) si esa variable no apunta a Postgres --
así este fichero puede formar parte también de la suite normal de
`pytest --cov` (que no tiene Postgres disponible) sin romperla.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("WATCHGATE_DASHBOARD_DATABASE_URL", "").startswith(
        ("postgres://", "postgresql://")
    ),
    reason="WATCHGATE_DASHBOARD_DATABASE_URL no apunta a Postgres -- ver postgres-test en CI.",
)


@pytest.fixture()
def dashboard_session():
    from watchgate.dashboard.backend import db as database

    # Fila/base únicas por test (`uuid`) -- varios tests corren contra el
    # MISMO Postgres real del servicio de CI, sin aislamiento de fichero
    # por test como en SQLite.
    with database.db_session() as session:
        database.init_db(session)
        yield session


def test_schema_creates_all_dashboard_tables_in_postgres(dashboard_session) -> None:
    from sqlalchemy import inspect

    inspector = inspect(dashboard_session.get_bind())
    tables = set(inspector.get_table_names())
    for table in (
        "pr_scores",
        "repo_roles",
        "repo_settings",
        "org_settings",
        "dashboard_users",
        "llm_settings",
        "ui_settings",
    ):
        assert table in tables


def test_upsert_role_and_get_role_roundtrip_in_postgres(dashboard_session) -> None:
    from watchgate.dashboard.backend import db as database

    user_login = f"pg-user-{uuid.uuid4().hex[:8]}"
    repo = f"acme/{uuid.uuid4().hex[:8]}"

    assert database.get_role(dashboard_session, user_login, repo) is None
    database.upsert_role(dashboard_session, user_login, repo, "mantenedor")
    assert database.get_role(dashboard_session, user_login, repo) == "mantenedor"

    # El upsert debe actualizar, no duplicar (ON CONFLICT DO UPDATE real
    # contra Postgres, no solo contra SQLite).
    database.upsert_role(dashboard_session, user_login, repo, "admin_organizacion")
    assert database.get_role(dashboard_session, user_login, repo) == "admin_organizacion"


def test_insert_aggregated_returns_autoincrement_id_in_postgres(dashboard_session) -> None:
    from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
    from watchgate.dashboard.backend import db as database

    repo = f"acme/{uuid.uuid4().hex[:8]}"
    layers = {
        name: LayerResult(layer_name=name, risk_score=10, justification="", skipped=False)
        for name in ("static", "deps", "reputation", "semantic")
    }
    score_id = database.insert_aggregated(
        dashboard_session,
        AggregatedResult(
            score=10,
            semaforo=Semaforo.VERDE,
            layer_results=layers,
            weights_used={"static": 0.25, "deps": 0.25, "reputation": 0.15, "semantic": 0.35},
            pr_id="7",
            repo=repo,
            timestamp="2026-08-17T12:00:00+00:00",
        ),
    )
    assert isinstance(score_id, int)
    assert score_id > 0

    fetched = database.get_score(dashboard_session, score_id)
    assert fetched is not None
    assert fetched.repo == repo
    assert fetched.pr_id == "7"


def test_authenticate_user_roundtrip_in_postgres(dashboard_session) -> None:
    from watchgate.dashboard.backend import db as database

    login = f"pg-auth-{uuid.uuid4().hex[:8]}"
    database.upsert_user(dashboard_session, login, "correct-horse", "Test User")

    assert database.authenticate_user(dashboard_session, login, "wrong-password") is False
    assert database.authenticate_user(dashboard_session, login, "correct-horse") is True
