"""Tests de watchgate/dashboard/backend/db_postgres.py (spec §13, migración).

Sin conexión real a Postgres (no hay servicio de Postgres en el entorno de
CI) -- cubre la traducción de placeholders, que es la parte con más riesgo
de regresión silenciosa (una `?` sin traducir rompe la consulta contra
Postgres pero no contra nada que se pueda comprobar sin una conexión real),
y que el esquema no contenga sintaxis específica de SQLite.

La migración se validó manualmente contra un Postgres 16 real durante el
desarrollo (CREATE TABLE, CRUD de las ~15 funciones de db.py ejercitadas,
`RETURNING id` en vez de `lastrowid`, tipos de columna booleanos/enteros,
`rowcount`) -- ver el mensaje del commit que introdujo este fichero. No hay
un test automático de extremo a extremo contra Postgres real porque
requeriría un servicio de base de datos en CI que hoy no existe.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from watchgate.dashboard.backend import db_postgres
from watchgate.dashboard.backend.db_postgres import (
    POSTGRES_SCHEMA,
    PostgresConnection,
    PostgresCursor,
    _to_pg_params,
    connect,
)


@pytest.fixture(autouse=True)
def _reset_pool_cache() -> None:
    """`_pools` es un cache global por `database_url` (mismo motivo que
    `_initialized_targets` en db.py) -- sin limpiarlo entre tests, un pool
    mockeado de un test se colaría en el siguiente que use la misma URL
    falsa."""
    db_postgres._pools.clear()


def test_translates_single_placeholder() -> None:
    assert _to_pg_params("SELECT * FROM t WHERE id = ?") == "SELECT * FROM t WHERE id = %s"


def test_translates_multiple_placeholders_in_order() -> None:
    sql = "INSERT INTO t (a, b, c) VALUES (?, ?, ?)"
    assert _to_pg_params(sql) == "INSERT INTO t (a, b, c) VALUES (%s, %s, %s)"


def test_translates_dynamically_built_in_clause() -> None:
    """Patrón real de compute_org_metrics: placeholders generados en runtime
    según el número de repos, no solo los que aparecen literales en el SQL."""
    placeholders = ",".join("?" for _ in range(3))
    sql = f"SELECT * FROM pr_scores WHERE repo IN ({placeholders})"
    assert _to_pg_params(sql) == "SELECT * FROM pr_scores WHERE repo IN (%s,%s,%s)"


def test_sql_without_placeholders_is_unchanged() -> None:
    sql = "SELECT 1 FROM org_settings WHERE id = 1"
    assert _to_pg_params(sql) == sql


def test_postgres_schema_has_no_sqlite_only_syntax() -> None:
    assert "AUTOINCREMENT" not in POSTGRES_SCHEMA
    assert "DATETIME" not in POSTGRES_SCHEMA


def test_postgres_schema_declares_all_dashboard_tables() -> None:
    for table in (
        "pr_scores",
        "repo_roles",
        "repo_settings",
        "org_settings",
        "dashboard_users",
        "llm_settings",
        "ui_settings",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in POSTGRES_SCHEMA


def test_postgres_cursor_and_connection_wrapper_methods() -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"id": 1, "repo": "acme/api"}
    mock_cursor.fetchall.return_value = [{"id": 1}, {"id": 2}]
    mock_cursor.rowcount = 2

    cursor_wrapper = PostgresCursor(mock_cursor)
    assert cursor_wrapper.fetchone() == {"id": 1, "repo": "acme/api"}
    assert cursor_wrapper.fetchall() == [{"id": 1}, {"id": 2}]
    assert cursor_wrapper.rowcount == 2

    mock_pg_conn = MagicMock()
    mock_pg_conn.cursor.return_value = mock_cursor

    pg_conn = PostgresConnection(mock_pg_conn)
    res = pg_conn.execute("SELECT * FROM pr_scores WHERE id = ?", (1,))
    assert res.fetchone() == {"id": 1, "repo": "acme/api"}

    pg_conn.executescript("CREATE TABLE t1 (a INT); CREATE TABLE t2 (b INT);")
    assert mock_pg_conn.cursor.return_value.execute.call_count > 0

    pg_conn.commit()
    mock_pg_conn.commit.assert_called_once()

    pg_conn.rollback()
    mock_pg_conn.rollback.assert_called_once()

    pg_conn.close()
    mock_pg_conn.close.assert_called_once()


def test_connect_gets_a_connection_from_the_pool() -> None:
    mock_pool_cls = MagicMock()
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool_cls.return_value = mock_pool

    with patch("watchgate.dashboard.backend.db_postgres.ConnectionPool", mock_pool_cls):
        conn = connect("postgresql://user:pass@localhost:5432/db")
        assert isinstance(conn, PostgresConnection)
        mock_pool.getconn.assert_called_once()
        # autocommit=False explícito (comportamiento previo a introducir el
        # pool, ver PostgresConnection) -- va en `kwargs` del pool, no en
        # cada `getconn()` individual.
        assert mock_pool_cls.call_args.kwargs["kwargs"] == {"autocommit": False}


def test_connect_reuses_the_same_pool_for_the_same_database_url() -> None:
    """Regresión: sin pool, cada `db_session()` (db.py) abría una conexión
    TCP+auth física nueva contra Postgres -- una por cada request de cada
    router. `_get_pool` debe crear el `ConnectionPool` una sola vez por
    `database_url` y reusarlo en llamadas posteriores a `connect()`, no uno
    nuevo cada vez."""
    mock_pool_cls = MagicMock()
    mock_pool_cls.return_value.getconn.return_value = MagicMock()
    url = "postgresql://user:pass@localhost:5432/db"

    with patch("watchgate.dashboard.backend.db_postgres.ConnectionPool", mock_pool_cls):
        connect(url)
        connect(url)
        connect(url)

    mock_pool_cls.assert_called_once()
    assert mock_pool_cls.return_value.getconn.call_count == 3


def test_close_returns_the_connection_to_the_pool_instead_of_closing_it() -> None:
    """`close()` en una conexión sin pool (p. ej. el test de arriba,
    `test_postgres_cursor_and_connection_wrapper_methods`) sigue cerrando
    de verdad -- solo una conexión de un pool real debe devolverse en vez
    de cerrarse, o el pool se quedaría sin conexiones que reutilizar."""
    mock_pool = MagicMock()
    mock_conn = MagicMock()

    conn = PostgresConnection(mock_conn, pool=mock_pool)
    conn.close()

    mock_pool.putconn.assert_called_once_with(mock_conn)
    mock_conn.close.assert_not_called()
