"""db_postgres.py — driver Postgres para el dashboard (spec §13, migración).

`db.py` tiene ~40 funciones de acceso a datos escritas contra la interfaz de
`sqlite3.Connection` (`.execute(sql, params).fetchone()/.fetchall()`,
`.commit()`, filas indexables por nombre de columna). En vez de reescribir
cada una contra un ORM, `PostgresConnection` envuelve `psycopg` para exponer
esa misma superficie mínima -- así `db.py` solo necesita ramificar por
motor en dos sitios (`connect()` e `init_db()`; `insert_aggregated()` para
el equivalente de `lastrowid`), y las otras ~35 funciones no cambian.

El SQL de `db.py` usa `?` como placeholder (estilo sqlite3); `execute()`
aquí lo traduce a `%s` (estilo psycopg) antes de ejecutar.
"""

from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import DictRow, dict_row

_PLACEHOLDER_RE = re.compile(r"\?")


def _to_pg_params(sql: str) -> str:
    return _PLACEHOLDER_RE.sub("%s", sql)


class PostgresCursor:
    def __init__(self, cursor: psycopg.Cursor[DictRow]) -> None:
        self._cursor = cursor

    def fetchone(self) -> DictRow | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return list(self._cursor.fetchall())

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)


class PostgresConnection:
    """Envoltorio de `psycopg.Connection` con la interfaz mínima que usa db.py."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = ()) -> PostgresCursor:
        cursor = self._conn.cursor(row_factory=dict_row)
        cursor.execute(_to_pg_params(sql), params)
        return PostgresCursor(cursor)

    def executescript(self, script: str) -> None:
        """Ejecuta cada sentencia por separado -- equivalente al
        `executescript` de sqlite3 (que sí soporta varias sentencias en una
        sola llamada), ya que psycopg no ofrece un batch multi-sentencia."""
        with self._conn.cursor() as cursor:
            for statement in script.split(";"):
                statement = statement.strip()
                if statement:
                    cursor.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def connect(database_url: str) -> PostgresConnection:
    conn = psycopg.connect(database_url, autocommit=False)
    return PostgresConnection(conn)


# Mismas tablas que SCHEMA (db.py) salvo lo que SQLite y Postgres no
# comparten: AUTOINCREMENT -> SERIAL. `timestamp` se queda TEXT (no
# TIMESTAMP): en SQLite ya se comporta como TEXT gracias a su tipado
# dinámico (guarda el ISO 8601 tal cual, sin parsear), y todo el código que
# lo consume (agrupar por día, ordenar) trabaja con el string en Python
# (`str(row["timestamp"])[:10]`, ver compute_org_metrics) -- si aquí fuese
# un TIMESTAMP real, psycopg lo devolvería como `datetime.datetime`, no
# `str`, y rompería la validación de `AggregatedResult.timestamp: str`.
#
# Columnas booleanas: a diferencia de SQLite (sin tipado real, cualquier
# valor Python vale), Postgres exige que el tipo de columna case con el tipo
# del parámetro enlazado -- no hay cast implícito bool<->integer en ningún
# sentido. `insert_aggregated()` en db.py enlaza los *_skipped como `bool`
# de Python (`skipped_of()`), así que esas columnas son BOOLEAN de verdad;
# `set_settings()`/`set_org_settings()` enlazan block_on_high /
# require_feedback_on_high ya convertidos con `int(...)`, así que esas se
# quedan INTEGER para que el binding siga encajando sin tocar esos call
# sites.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_scores (
  id SERIAL PRIMARY KEY,
  repo TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  timestamp TEXT NOT NULL,
  score INTEGER NOT NULL,
  semaforo TEXT NOT NULL,
  static_score INTEGER, static_skipped BOOLEAN,
  deps_score INTEGER, deps_skipped BOOLEAN,
  reputation_score INTEGER, reputation_skipped BOOLEAN,
  semantic_score INTEGER, semantic_skipped BOOLEAN, semantic_justification TEXT,
  weights_json TEXT NOT NULL DEFAULT '{}',
  author_login TEXT,
  human_feedback TEXT CHECK(
    human_feedback IN ('correcto','falso_positivo') OR human_feedback IS NULL
  ),
  accepted_by TEXT,
  accepted_at TEXT,
  findings_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_repo_timestamp ON pr_scores(repo, timestamp);

CREATE TABLE IF NOT EXISTS repo_roles (
  user_login TEXT NOT NULL, repo TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin_organizacion','mantenedor','revisor')),
  PRIMARY KEY (user_login, repo)
);

CREATE TABLE IF NOT EXISTS repo_settings (
  repo TEXT PRIMARY KEY,
  weights_json TEXT NOT NULL,
  thresholds_json TEXT NOT NULL,
  layers_enabled_json TEXT NOT NULL DEFAULT '{}',
  risk_colors_json TEXT NOT NULL DEFAULT '{}',
  block_on_high INTEGER NOT NULL DEFAULT 1,
  require_feedback_on_high INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS org_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  weights_json TEXT NOT NULL,
  thresholds_json TEXT NOT NULL,
  layers_enabled_json TEXT NOT NULL,
  risk_colors_json TEXT NOT NULL DEFAULT '{}',
  block_on_high INTEGER NOT NULL DEFAULT 1,
  require_feedback_on_high INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dashboard_users (
  login TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  base_url TEXT,
  api_key TEXT,
  monthly_budget_tokens INTEGER,
  max_diff_tokens INTEGER
);

CREATE TABLE IF NOT EXISTS ui_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  primary_color TEXT NOT NULL,
  accent_color TEXT NOT NULL,
  radius TEXT NOT NULL,
  font_scale TEXT NOT NULL,
  density TEXT NOT NULL,
  default_theme TEXT NOT NULL
);
"""
