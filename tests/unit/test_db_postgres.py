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

from watchgate.dashboard.backend.db_postgres import POSTGRES_SCHEMA, _to_pg_params


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
