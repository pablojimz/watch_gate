"""db.py — esquema y acceso a la base de datos histórica.

SQLite por defecto (fichero local, cero configuración). Si
``WATCHGATE_DASHBOARD_DATABASE_URL`` apunta a una URL ``postgres(ql)://``,
``connect()`` usa Postgres en su lugar (ver `db_postgres.py`): las ~40
funciones de este módulo no saben contra qué motor hablan, solo `connect()`,
`init_db()` e `insert_aggregated()` (el único sitio que usa `lastrowid`,
sin equivalente directo en Postgres) ramifican por motor.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from watchgate.core.models import (
    AggregatedResult,
    Confidence,
    Finding,
    LayerResult,
    RiskCategory,
    Semaforo,
    ThreatNature,
)
from watchgate.dashboard.backend import db_postgres
from watchgate.dashboard.backend.db_postgres import PostgresConnection
from watchgate.dashboard.backend.schemas import (
    AgentMetricRow,
    AgentUsageMetrics,
    FeedbackValue,
    LlmSettingsIn,
    LlmSettingsOut,
    OrgMetrics,
    RepoMetricRow,
    RepoSettings,
    RoleName,
    ScoreOut,
    TrendPoint,
    UiSettings,
    normalize_login,
)

DBConnection = sqlite3.Connection | PostgresConnection
# Fila devuelta por `conn.execute(...).fetchone()/.fetchall()`: sqlite3.Row
# en SQLite, dict en Postgres (ver PostgresCursor en db_postgres.py) -- ambas
# soportan `row["columna"]` y `.keys()`, que es todo lo que este módulo usa.
Row = sqlite3.Row | dict[str, Any]

SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  timestamp DATETIME NOT NULL,
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
  block_on_high BOOLEAN NOT NULL DEFAULT 1,
  require_feedback_on_high BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS org_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  weights_json TEXT NOT NULL,
  thresholds_json TEXT NOT NULL,
  layers_enabled_json TEXT NOT NULL,
  risk_colors_json TEXT NOT NULL DEFAULT '{}',
  block_on_high BOOLEAN NOT NULL DEFAULT 1,
  require_feedback_on_high BOOLEAN NOT NULL DEFAULT 0
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

DEFAULT_WEIGHTS = {
    "static": 0.25,
    "deps": 0.15,
    "vulnerabilities": 0.10,
    "reputation": 0.15,
    "semantic": 0.35,
}
DEFAULT_THRESHOLDS = {"amarillo": 34, "rojo": 66}
DEFAULT_LAYERS = {
    "static": True,
    "deps": True,
    "vulnerabilities": True,
    "reputation": True,
    "semantic": True,
}
DEFAULT_RISK_COLORS = {"verde": "#3d9b5f", "amarillo": "#d4a017", "rojo": "#c23b3b"}
DEFAULT_LLM = {
    "provider": "anthropic",
    "model": "claude-sonnet-5",
    "base_url": None,
    "monthly_budget_tokens": 2_000_000,
    "max_diff_tokens": 80_000,
}
DEFAULT_UI = UiSettings()
_LAYER_COLS = (
    ("static", "static_score", "static_skipped"),
    ("deps", "deps_score", "deps_skipped"),
    ("vulnerabilities", "vulnerabilities_score", "vulnerabilities_skipped"),
    ("reputation", "reputation_score", "reputation_skipped"),
    ("semantic", "semantic_score", "semantic_skipped"),
)


def default_db_path() -> Path:
    raw = os.environ.get("WATCHGATE_DASHBOARD_DB")
    if raw:
        return Path(raw)
    return Path(".watchgate") / "dashboard.db"


def connect(db_path: Path | None = None) -> DBConnection:
    database_url = os.environ.get("WATCHGATE_DASHBOARD_DATABASE_URL")
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        return db_postgres.connect(database_url)

    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connection_target(db_path: Path | None) -> str:
    """Identificador estable de a qué base de datos apunta `connect(db_path)`
    -- mismo criterio que usa `connect()` para decidir Postgres vs SQLite,
    duplicado aquí a propósito para no acoplar el guard de `db_session()` a
    cambios de firma de `connect()`."""
    database_url = os.environ.get("WATCHGATE_DASHBOARD_DATABASE_URL")
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        return database_url
    return str(db_path or default_db_path())


def _init_db_postgres(conn: PostgresConnection) -> None:
    conn.executescript(db_postgres.POSTGRES_SCHEMA)
    # A diferencia de SQLite, Postgres soporta IF NOT EXISTS en ADD COLUMN de
    # forma nativa -- no hace falta el sondeo vía PRAGMA table_info de abajo.
    conn.execute("ALTER TABLE pr_scores ADD COLUMN IF NOT EXISTS author_login TEXT")
    conn.execute("ALTER TABLE pr_scores ADD COLUMN IF NOT EXISTS vulnerabilities_score INTEGER")
    conn.execute("ALTER TABLE pr_scores ADD COLUMN IF NOT EXISTS vulnerabilities_skipped BOOLEAN")
    conn.execute("ALTER TABLE pr_scores ADD COLUMN IF NOT EXISTS accepted_by TEXT")
    conn.execute("ALTER TABLE pr_scores ADD COLUMN IF NOT EXISTS accepted_at TEXT")
    conn.execute("ALTER TABLE pr_scores ADD COLUMN IF NOT EXISTS findings_json TEXT")
    conn.execute(
        "ALTER TABLE repo_settings ADD COLUMN IF NOT EXISTS "
        "layers_enabled_json TEXT NOT NULL DEFAULT '{}'"
    )
    conn.execute(
        "ALTER TABLE repo_settings ADD COLUMN IF NOT EXISTS "
        "block_on_high INTEGER NOT NULL DEFAULT 1"
    )
    conn.execute(
        "ALTER TABLE repo_settings ADD COLUMN IF NOT EXISTS "
        "require_feedback_on_high INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE repo_settings ADD COLUMN IF NOT EXISTS "
        "risk_colors_json TEXT NOT NULL DEFAULT '{}'"
    )
    conn.execute(
        "ALTER TABLE org_settings ADD COLUMN IF NOT EXISTS "
        "risk_colors_json TEXT NOT NULL DEFAULT '{}'"
    )
    conn.execute("ALTER TABLE ui_settings ADD COLUMN IF NOT EXISTS logo_data_url TEXT")
    conn.commit()
    ensure_org_settings(conn)
    ensure_llm_settings(conn)
    ensure_ui_settings(conn)


def init_db(conn: DBConnection) -> None:
    if isinstance(conn, PostgresConnection):
        _init_db_postgres(conn)
        return
    conn.executescript(SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(pr_scores)").fetchall()}
    if "author_login" not in cols:
        conn.execute("ALTER TABLE pr_scores ADD COLUMN author_login TEXT")
    if "vulnerabilities_score" not in cols:
        conn.execute("ALTER TABLE pr_scores ADD COLUMN vulnerabilities_score INTEGER")
    if "vulnerabilities_skipped" not in cols:
        conn.execute("ALTER TABLE pr_scores ADD COLUMN vulnerabilities_skipped BOOLEAN")
    if "accepted_by" not in cols:
        conn.execute("ALTER TABLE pr_scores ADD COLUMN accepted_by TEXT")
    if "accepted_at" not in cols:
        conn.execute("ALTER TABLE pr_scores ADD COLUMN accepted_at TEXT")
    if "findings_json" not in cols:
        conn.execute("ALTER TABLE pr_scores ADD COLUMN findings_json TEXT")
    repo_cols = {row[1] for row in conn.execute("PRAGMA table_info(repo_settings)").fetchall()}
    if "layers_enabled_json" not in repo_cols:
        conn.execute(
            "ALTER TABLE repo_settings ADD COLUMN layers_enabled_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "block_on_high" not in repo_cols:
        conn.execute(
            "ALTER TABLE repo_settings ADD COLUMN block_on_high BOOLEAN NOT NULL DEFAULT 1"
        )
    if "require_feedback_on_high" not in repo_cols:
        conn.execute(
            "ALTER TABLE repo_settings "
            "ADD COLUMN require_feedback_on_high BOOLEAN NOT NULL DEFAULT 0"
        )
    if "risk_colors_json" not in repo_cols:
        conn.execute(
            "ALTER TABLE repo_settings ADD COLUMN risk_colors_json TEXT NOT NULL DEFAULT '{}'"
        )
    org_cols = {row[1] for row in conn.execute("PRAGMA table_info(org_settings)").fetchall()}
    if org_cols and "risk_colors_json" not in org_cols:
        conn.execute(
            "ALTER TABLE org_settings ADD COLUMN risk_colors_json TEXT NOT NULL DEFAULT '{}'"
        )
    ui_cols = {row[1] for row in conn.execute("PRAGMA table_info(ui_settings)").fetchall()}
    if ui_cols and "logo_data_url" not in ui_cols:
        conn.execute("ALTER TABLE ui_settings ADD COLUMN logo_data_url TEXT")
    conn.commit()
    ensure_org_settings(conn)
    ensure_llm_settings(conn)
    ensure_ui_settings(conn)


_initialized_targets: set[str] = set()
_init_lock = threading.Lock()


@contextmanager
def db_session(db_path: Path | None = None) -> Iterator[DBConnection]:
    conn = connect(db_path)
    target = _connection_target(db_path)
    try:
        # Bug real encontrado desplegando contra Postgres real: `init_db()`
        # (incluye `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, DDL que exige
        # un lock exclusivo) se ejecutaba en CADA llamada a `db_session()` --
        # es decir, en cada request de cada router. Bajo tráfico concurrente
        # real (varias pestañas/peticiones en paralelo cargando el
        # Dashboard, exactamente lo que hace un navegador), dos peticiones
        # ejecutando el mismo ALTER TABLE a la vez podían deadlockear de
        # verdad entre sí (`psycopg.errors.DeadlockDetected`, reproducido en
        # vivo). SQLite nunca lo mostró porque su locking es de fichero
        # completo, no por fila/tabla como Postgres.
        #
        # `init_db()` en sí ya es idempotente en efecto (todo `IF NOT
        # EXISTS`), pero eso no evita la carrera de dos conexiones
        # comprobando y alterando el mismo esquema a la vez -- el problema
        # no era el resultado final, era ejecutarlo más de una vez por
        # proceso sin necesidad. Con double-checked locking, por cada base
        # de datos destino (`target`) real solo la primera llamada del
        # proceso ejecuta la migración; el resto la salta.
        if target not in _initialized_targets:
            with _init_lock:
                if target not in _initialized_targets:
                    init_db(conn)
                    _initialized_targets.add(target)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _pr_number_from_pr_id(pr_id: str) -> int:
    digits = "".join(ch for ch in pr_id if ch.isdigit())
    return int(digits) if digits else 0


def _serialize_findings(layers: dict[str, LayerResult]) -> str | None:
    """Guarda lo que las columnas planas de `pr_scores` no capturan
    (`findings` con fichero/línea/regla, `category`, `confidence`,
    `threat_nature` por capa) -- sin esto, el histórico del dashboard
    perdía toda la sustancia de un hallazgo (dónde está, qué regla lo
    disparó) en cuanto se insertaba, aunque el propio `AggregatedResult` la
    tuviera en el momento del análisis. `None` si no hay nada que guardar,
    para no ensuciar filas de capas sin hallazgos con un JSON vacío."""
    payload = {
        name: {
            "findings": [f.model_dump(mode="json") for f in layer.findings],
            "category": layer.category.value if layer.category else None,
            "confidence": layer.confidence.value if layer.confidence else None,
            "threat_nature": layer.threat_nature.value if layer.threat_nature else None,
        }
        for name, layer in layers.items()
        if layer.findings or layer.category or layer.confidence or layer.threat_nature
    }
    return json.dumps(payload) if payload else None


def insert_aggregated(
    conn: DBConnection,
    result: AggregatedResult,
    *,
    author_login: str | None = None,
) -> int:
    layers = result.layer_results

    def _get_layer(name: str) -> Any:
        if name in layers:
            return layers[name]
        if name == "deps" and "dependencies" in layers:
            return layers["dependencies"]
        if name == "dependencies" and "deps" in layers:
            return layers["deps"]
        return None

    def score_of(name: str) -> int | None:
        layer = _get_layer(name)
        return None if layer is None else layer.risk_score

    def skipped_of(name: str) -> bool:
        layer = _get_layer(name)
        return True if layer is None else layer.skipped

    semantic = layers.get("semantic")
    justification = semantic.justification if semantic is not None else None

    insert_sql = """
        INSERT INTO pr_scores (
          repo, pr_number, timestamp, score, semaforo,
          static_score, static_skipped,
          deps_score, deps_skipped,
          vulnerabilities_score, vulnerabilities_skipped,
          reputation_score, reputation_skipped,
          semantic_score, semantic_skipped, semantic_justification,
          weights_json, author_login, human_feedback, findings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """
    params = (
        result.repo,
        _pr_number_from_pr_id(result.pr_id),
        result.timestamp,
        result.score,
        result.semaforo.value,
        score_of("static"),
        skipped_of("static"),
        score_of("deps"),
        skipped_of("deps"),
        score_of("vulnerabilities"),
        skipped_of("vulnerabilities"),
        score_of("reputation"),
        skipped_of("reputation"),
        score_of("semantic"),
        skipped_of("semantic"),
        justification,
        json.dumps(result.weights_used),
        author_login,
        _serialize_findings(layers),
    )

    if isinstance(conn, PostgresConnection):
        # sqlite3.Cursor.lastrowid no tiene equivalente en psycopg -- pedimos
        # el id insertado explícitamente en la misma sentencia.
        row = conn.execute(insert_sql + " RETURNING id", params).fetchone()
        assert row is not None
        new_id = int(row["id"])
    else:
        cur = conn.execute(insert_sql, params)
        new_id = int(cur.lastrowid or 0)
    conn.commit()
    return new_id


def _row_to_score_out(row: Row) -> ScoreOut:
    keys = row.keys()
    findings_raw = row["findings_json"] if "findings_json" in keys else None
    findings_by_layer: dict[str, dict[str, Any]] = json.loads(findings_raw) if findings_raw else {}

    layer_results: dict[str, LayerResult] = {}
    for name, score_col, skip_col in _LAYER_COLS:
        skipped = bool(row[skip_col]) if row[skip_col] is not None else True
        raw_score = row[score_col]
        justification = ""
        if name == "semantic":
            justification = row["semantic_justification"] or ""

        extra = findings_by_layer.get(name, {})
        findings = [Finding.model_validate(f) for f in extra.get("findings", [])]
        category = RiskCategory(extra["category"]) if extra.get("category") else None
        confidence = Confidence(extra["confidence"]) if extra.get("confidence") else None
        threat_nature = ThreatNature(extra["threat_nature"]) if extra.get("threat_nature") else None

        layer_results[name] = LayerResult(
            layer_name=name,
            risk_score=int(raw_score) if raw_score is not None else 0,
            justification=justification,
            findings=findings,
            category=category,
            confidence=confidence,
            threat_nature=threat_nature,
            skipped=skipped,
            skip_reason="omitida" if skipped else None,
        )

    weights_raw = row["weights_json"] if "weights_json" in keys else "{}"
    weights = json.loads(weights_raw or "{}")
    author = row["author_login"] if "author_login" in keys else None
    result = AggregatedResult(
        score=int(row["score"]),
        semaforo=Semaforo(row["semaforo"]),
        layer_results=layer_results,
        weights_used=weights,
        pr_id=str(row["pr_number"]),
        repo=row["repo"],
        timestamp=row["timestamp"],
    )
    feedback = row["human_feedback"]
    accepted_by = row["accepted_by"] if "accepted_by" in keys else None
    accepted_at = row["accepted_at"] if "accepted_at" in keys else None
    return ScoreOut.from_aggregated(
        score_id=int(row["id"]),
        result=result,
        human_feedback=feedback,
        author_login=author,
        accepted_by=accepted_by,
        accepted_at=accepted_at,
    )


def list_scores(conn: DBConnection, repo: str) -> list[ScoreOut]:
    rows = conn.execute(
        "SELECT * FROM pr_scores WHERE repo = ? ORDER BY timestamp DESC",
        (repo,),
    ).fetchall()
    return [_row_to_score_out(row) for row in rows]


def get_score(conn: DBConnection, score_id: int) -> ScoreOut | None:
    row = conn.execute("SELECT * FROM pr_scores WHERE id = ?", (score_id,)).fetchone()
    return None if row is None else _row_to_score_out(row)


def set_feedback(conn: DBConnection, score_id: int, feedback: FeedbackValue) -> ScoreOut | None:
    cur = conn.execute(
        "UPDATE pr_scores SET human_feedback = ? WHERE id = ?",
        (feedback, score_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_score(conn, score_id)


def set_accepted(conn: DBConnection, score_id: int, user_login: str) -> ScoreOut | None:
    """Gate de aprobación manual: un mantenedor/admin marca un PR en amarillo/
    rojo como revisado y aceptado a sabiendas del riesgo. Distinto del
    `human_feedback` de arriba (que valora si el ANÁLISIS acertó, no si el
    riesgo real se acepta) -- deliberadamente independiente para no mezclar
    "el score está mal" con "el score está bien pero seguimos adelante"."""
    cur = conn.execute(
        "UPDATE pr_scores SET accepted_by = ?, accepted_at = ? WHERE id = ?",
        (normalize_login(user_login), datetime.now(UTC).isoformat(), score_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_score(conn, score_id)


def clear_accepted(conn: DBConnection, score_id: int) -> ScoreOut | None:
    cur = conn.execute(
        "UPDATE pr_scores SET accepted_by = NULL, accepted_at = NULL WHERE id = ?",
        (score_id,),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_score(conn, score_id)


def get_role(conn: DBConnection, user_login: str, repo: str) -> RoleName | None:
    row = conn.execute(
        "SELECT role FROM repo_roles WHERE user_login = ? AND repo = ?",
        (normalize_login(user_login), repo),
    ).fetchone()
    if row is None:
        return None
    res_role: str = row["role"]
    return cast(RoleName, res_role)


def upsert_role(conn: DBConnection, user_login: str, repo: str, role: RoleName) -> None:
    conn.execute(
        """
        INSERT INTO repo_roles (user_login, repo, role) VALUES (?, ?, ?)
        ON CONFLICT(user_login, repo) DO UPDATE SET role = excluded.role
        """,
        (normalize_login(user_login), repo, role),
    )
    conn.commit()


def delete_role(conn: DBConnection, user_login: str, repo: str) -> bool:
    cur = conn.execute(
        "DELETE FROM repo_roles WHERE user_login = ? AND repo = ?",
        (normalize_login(user_login), repo),
    )
    conn.commit()
    return cur.rowcount > 0


def list_roles(conn: DBConnection, repo: str | None = None) -> list[Row]:
    # sqlite3.Cursor.fetchall() está tipado como list[Any] en sus stubs (no
    # conoce row_factory=sqlite3.Row en tiempo de tipado) -- cast explícito a
    # la interfaz real que devuelve en ejecución.
    if repo is None:
        rows = conn.execute(
            "SELECT user_login, repo, role FROM repo_roles ORDER BY repo, user_login"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT user_login, repo, role FROM repo_roles WHERE repo = ? ORDER BY user_login",
            (repo,),
        ).fetchall()
    return cast("list[Row]", rows)


def list_repos_for_user(conn: DBConnection, user_login: str, is_admin: bool) -> list[str]:
    if is_admin:
        from_scores = {
            r["repo"] for r in conn.execute("SELECT DISTINCT repo FROM pr_scores").fetchall()
        }
        from_roles = {
            r["repo"] for r in conn.execute("SELECT DISTINCT repo FROM repo_roles").fetchall()
        }
        from_settings = {
            r["repo"] for r in conn.execute("SELECT DISTINCT repo FROM repo_settings").fetchall()
        }
        return sorted(from_scores | from_roles | from_settings)

    rows = conn.execute(
        "SELECT DISTINCT repo FROM repo_roles WHERE user_login = ? ORDER BY repo",
        (normalize_login(user_login),),
    ).fetchall()
    return [r["repo"] for r in rows]


def user_is_org_admin(conn: DBConnection, user_login: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM repo_roles
        WHERE user_login = ? AND role = 'admin_organizacion'
        LIMIT 1
        """,
        (normalize_login(user_login),),
    ).fetchone()
    return row is not None


def ensure_org_settings(conn: DBConnection) -> None:
    row = conn.execute("SELECT 1 FROM org_settings WHERE id = 1").fetchone()
    if row is not None:
        return
    conn.execute(
        """
        INSERT INTO org_settings (
          id, weights_json, thresholds_json, layers_enabled_json, risk_colors_json,
          block_on_high, require_feedback_on_high
        ) VALUES (1, ?, ?, ?, ?, 1, 0)
        """,
        (
            json.dumps(DEFAULT_WEIGHTS),
            json.dumps(DEFAULT_THRESHOLDS),
            json.dumps(DEFAULT_LAYERS),
            json.dumps(DEFAULT_RISK_COLORS),
        ),
    )
    conn.commit()


def _settings_from_row(row: Row | None, *, source: Literal["default", "repo"]) -> RepoSettings:
    if row is None:
        return RepoSettings(
            weights=dict(DEFAULT_WEIGHTS),
            thresholds=dict(DEFAULT_THRESHOLDS),
            layers_enabled=dict(DEFAULT_LAYERS),
            risk_colors=dict(DEFAULT_RISK_COLORS),
            block_on_high=True,
            require_feedback_on_high=False,
            source=source,
        )
    keys = row.keys()
    layers_raw = row["layers_enabled_json"] if "layers_enabled_json" in keys else "{}"
    layers = json.loads(layers_raw or "{}") or dict(DEFAULT_LAYERS)
    colors_raw = row["risk_colors_json"] if "risk_colors_json" in keys else "{}"
    colors = json.loads(colors_raw or "{}") or dict(DEFAULT_RISK_COLORS)
    merged_colors = {**DEFAULT_RISK_COLORS, **colors}
    return RepoSettings(
        weights=json.loads(row["weights_json"]),
        thresholds=json.loads(row["thresholds_json"]),
        layers_enabled=layers,
        risk_colors=merged_colors,
        block_on_high=bool(row["block_on_high"]) if "block_on_high" in keys else True,
        require_feedback_on_high=(
            bool(row["require_feedback_on_high"]) if "require_feedback_on_high" in keys else False
        ),
        source=source,
    )


def get_org_settings(conn: DBConnection) -> RepoSettings:
    ensure_org_settings(conn)
    row = conn.execute("SELECT * FROM org_settings WHERE id = 1").fetchone()
    return _settings_from_row(row, source="default")


def set_org_settings(conn: DBConnection, settings: RepoSettings) -> RepoSettings:
    ensure_org_settings(conn)
    conn.execute(
        """
        UPDATE org_settings SET
          weights_json = ?,
          thresholds_json = ?,
          layers_enabled_json = ?,
          risk_colors_json = ?,
          block_on_high = ?,
          require_feedback_on_high = ?
        WHERE id = 1
        """,
        (
            json.dumps(settings.weights),
            json.dumps(settings.thresholds),
            json.dumps(settings.layers_enabled),
            json.dumps(settings.risk_colors),
            int(settings.block_on_high),
            int(settings.require_feedback_on_high),
        ),
    )
    conn.commit()
    return get_org_settings(conn)


def get_settings(conn: DBConnection, repo: str) -> RepoSettings:
    row = conn.execute("SELECT * FROM repo_settings WHERE repo = ?", (repo,)).fetchone()
    if row is None:
        defaults = get_org_settings(conn)
        return defaults.model_copy(update={"source": "default"})
    return _settings_from_row(row, source="repo")


def set_settings(conn: DBConnection, repo: str, settings: RepoSettings) -> RepoSettings:
    conn.execute(
        """
        INSERT INTO repo_settings (
          repo, weights_json, thresholds_json, layers_enabled_json, risk_colors_json,
          block_on_high, require_feedback_on_high
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo) DO UPDATE SET
          weights_json = excluded.weights_json,
          thresholds_json = excluded.thresholds_json,
          layers_enabled_json = excluded.layers_enabled_json,
          risk_colors_json = excluded.risk_colors_json,
          block_on_high = excluded.block_on_high,
          require_feedback_on_high = excluded.require_feedback_on_high
        """,
        (
            repo,
            json.dumps(settings.weights),
            json.dumps(settings.thresholds),
            json.dumps(settings.layers_enabled),
            json.dumps(settings.risk_colors),
            int(settings.block_on_high),
            int(settings.require_feedback_on_high),
        ),
    )
    conn.commit()
    return get_settings(conn, repo)


def clear_repo_settings(conn: DBConnection, repo: str) -> RepoSettings:
    conn.execute("DELETE FROM repo_settings WHERE repo = ?", (repo,))
    conn.commit()
    return get_settings(conn, repo)


def _mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "••••••••"
    return f"{api_key[:4]}…{api_key[-4:]}"


def ensure_llm_settings(conn: DBConnection) -> None:
    row = conn.execute("SELECT 1 FROM llm_settings WHERE id = 1").fetchone()
    if row is not None:
        return
    conn.execute(
        """
        INSERT INTO llm_settings (
          id, provider, model, base_url, api_key, monthly_budget_tokens, max_diff_tokens
        ) VALUES (1, ?, ?, ?, NULL, ?, ?)
        """,
        (
            DEFAULT_LLM["provider"],
            DEFAULT_LLM["model"],
            DEFAULT_LLM["base_url"],
            DEFAULT_LLM["monthly_budget_tokens"],
            DEFAULT_LLM["max_diff_tokens"],
        ),
    )
    conn.commit()


def get_llm_settings(conn: DBConnection) -> LlmSettingsOut:
    ensure_llm_settings(conn)
    row = conn.execute("SELECT * FROM llm_settings WHERE id = 1").fetchone()
    assert row is not None
    api_key = row["api_key"]
    return LlmSettingsOut(
        provider=row["provider"],
        model=row["model"],
        base_url=row["base_url"],
        api_key_set=bool(api_key),
        api_key_masked=_mask_api_key(api_key),
        monthly_budget_tokens=row["monthly_budget_tokens"],
        max_diff_tokens=row["max_diff_tokens"],
    )


def set_llm_settings(conn: DBConnection, body: LlmSettingsIn) -> LlmSettingsOut:
    ensure_llm_settings(conn)
    current = conn.execute("SELECT api_key FROM llm_settings WHERE id = 1").fetchone()
    current_key = current["api_key"] if current is not None else None
    if body.clear_api_key:
        new_key = None
    elif body.api_key is not None and body.api_key.strip():
        new_key = body.api_key.strip()
    else:
        new_key = current_key
    conn.execute(
        """
        UPDATE llm_settings SET
          provider = ?,
          model = ?,
          base_url = ?,
          api_key = ?,
          monthly_budget_tokens = ?,
          max_diff_tokens = ?
        WHERE id = 1
        """,
        (
            body.provider,
            body.model,
            body.base_url,
            new_key,
            body.monthly_budget_tokens,
            body.max_diff_tokens,
        ),
    )
    conn.commit()
    return get_llm_settings(conn)


def ensure_ui_settings(conn: DBConnection) -> None:
    row = conn.execute("SELECT 1 FROM ui_settings WHERE id = 1").fetchone()
    if row is not None:
        return
    defaults = DEFAULT_UI
    conn.execute(
        """
        INSERT INTO ui_settings (
          id, primary_color, accent_color, radius, font_scale, density, default_theme
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        (
            defaults.primary_color,
            defaults.accent_color,
            defaults.radius,
            defaults.font_scale,
            defaults.density,
            defaults.default_theme,
        ),
    )
    conn.commit()


def get_ui_settings(conn: DBConnection) -> UiSettings:
    ensure_ui_settings(conn)
    row = conn.execute("SELECT * FROM ui_settings WHERE id = 1").fetchone()
    assert row is not None
    return UiSettings(
        primary_color=row["primary_color"],
        accent_color=row["accent_color"],
        radius=row["radius"],
        font_scale=row["font_scale"],
        density=row["density"],
        default_theme=row["default_theme"],
        logo_data_url=row["logo_data_url"],
    )


def set_ui_settings(conn: DBConnection, settings: UiSettings) -> UiSettings:
    ensure_ui_settings(conn)
    conn.execute(
        """
        UPDATE ui_settings SET
          primary_color = ?,
          accent_color = ?,
          radius = ?,
          font_scale = ?,
          density = ?,
          default_theme = ?,
          logo_data_url = ?
        WHERE id = 1
        """,
        (
            settings.primary_color,
            settings.accent_color,
            settings.radius,
            settings.font_scale,
            settings.density,
            settings.default_theme,
            settings.logo_data_url,
        ),
    )
    conn.commit()
    return get_ui_settings(conn)


def compute_org_metrics(conn: DBConnection, repos: list[str]) -> OrgMetrics:
    if not repos:
        return OrgMetrics(
            total_prs=0,
            avg_score=0.0,
            repos_count=0,
            by_semaforo={"verde": 0, "amarillo": 0, "rojo": 0},
            feedback_correct=0,
            feedback_false_positive=0,
            feedback_pending=0,
            layer_avg={
                "static": 0.0,
                "deps": 0.0,
                "vulnerabilities": 0.0,
                "reputation": 0.0,
                "semantic": 0.0,
            },
            by_repo=[],
            trend=[],
        )

    placeholders = ",".join("?" for _ in repos)
    rows = conn.execute(
        f"SELECT * FROM pr_scores WHERE repo IN ({placeholders}) ORDER BY timestamp ASC",
        repos,
    ).fetchall()

    total = len(rows)
    avg_score = round(sum(int(r["score"]) for r in rows) / total, 1) if total else 0.0
    by_semaforo = {"verde": 0, "amarillo": 0, "rojo": 0}
    feedback_correct = 0
    feedback_fp = 0
    feedback_pending = 0
    layer_sums: dict[str, list[int]] = {
        "static": [],
        "deps": [],
        "vulnerabilities": [],
        "reputation": [],
        "semantic": [],
    }
    per_repo: dict[str, dict[str, int | float]] = {}
    by_day: dict[str, list[int]] = {}

    for r in rows:
        sem = r["semaforo"]
        if sem in by_semaforo:
            by_semaforo[sem] += 1
        fb = r["human_feedback"]
        if fb == "correcto":
            feedback_correct += 1
        elif fb == "falso_positivo":
            feedback_fp += 1
        else:
            feedback_pending += 1

        # Misma tripleta (nombre, columna score, columna skipped) que
        # _LAYER_COLS -- reutilizada en vez de duplicada, para no tener que
        # acordarse de actualizar dos sitios el día que cambien las capas
        # (ya pasaba antes de esta ronda: esta tupla vivía por su cuenta,
        # desincronizada de _LAYER_COLS aunque tuviera la misma forma).
        for layer, score_col, skip_col in _LAYER_COLS:
            if not r[skip_col] and r[score_col] is not None:
                layer_sums[layer].append(int(r[score_col]))

        repo = r["repo"]
        bucket = per_repo.setdefault(
            repo,
            {
                "prs": 0,
                "score_sum": 0,
                "verde": 0,
                "amarillo": 0,
                "rojo": 0,
                "feedback_pending": 0,
            },
        )
        bucket["prs"] = int(bucket["prs"]) + 1
        bucket["score_sum"] = float(bucket["score_sum"]) + int(r["score"])
        if sem in ("verde", "amarillo", "rojo"):
            bucket[sem] = int(bucket[sem]) + 1
        if fb is None:
            bucket["feedback_pending"] = int(bucket["feedback_pending"]) + 1

        day = str(r["timestamp"])[:10]
        by_day.setdefault(day, []).append(int(r["score"]))

    layer_avg = {k: round(sum(v) / len(v), 1) if v else 0.0 for k, v in layer_sums.items()}
    by_repo = [
        RepoMetricRow(
            repo=repo,
            prs=int(data["prs"]),
            avg_score=round(float(data["score_sum"]) / int(data["prs"]), 1),
            verde=int(data["verde"]),
            amarillo=int(data["amarillo"]),
            rojo=int(data["rojo"]),
            feedback_pending=int(data["feedback_pending"]),
        )
        for repo, data in sorted(per_repo.items())
    ]
    trend = [
        TrendPoint(
            day=day,
            avg_score=round(sum(scores) / len(scores), 1),
            count=len(scores),
        )
        for day, scores in sorted(by_day.items())
    ]

    return OrgMetrics(
        total_prs=total,
        avg_score=avg_score,
        repos_count=len(repos),
        by_semaforo=by_semaforo,
        feedback_correct=feedback_correct,
        feedback_false_positive=feedback_fp,
        feedback_pending=feedback_pending,
        layer_avg=layer_avg,
        by_repo=by_repo,
        trend=trend,
    )


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash PBKDF2-SHA256 con sal. Formato: ``pbkdf2$iters$salt$digest``."""
    salt_hex = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), 120_000
    ).hex()
    return f"pbkdf2$120000${salt_hex}${digest}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2":
        return False
    _, iters_s, salt_hex, expected = parts
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), int(iters_s)
    ).hex()
    return secrets.compare_digest(digest, expected)


def upsert_user(conn: DBConnection, login: str, password: str, display_name: str) -> None:
    conn.execute(
        """
        INSERT INTO dashboard_users (login, password_hash, display_name)
        VALUES (?, ?, ?)
        ON CONFLICT(login) DO UPDATE SET
          password_hash = excluded.password_hash,
          display_name = excluded.display_name
        """,
        (normalize_login(login), hash_password(password), display_name),
    )
    conn.commit()


# Hash de relleno con el mismo coste (120.000 iteraciones PBKDF2) que un
# hash real, para que `authenticate_user` tarde lo mismo tanto si el login
# existe como si no -- ver el comentario dentro de la función.
_DUMMY_PASSWORD_HASH = hash_password("watchgate-dummy-timing-safe-password")


def authenticate_user(conn: DBConnection, login: str, password: str) -> bool:
    """Antes, un login inexistente devolvía `False` de inmediato, mientras
    que uno existente calculaba un PBKDF2 de 120.000 iteraciones (lento a
    propósito) antes de comparar -- la diferencia de tiempo es medible y
    permite enumerar logins válidos contra `/api/auth/login`, más aún sin
    ningún rate limiting delante. Ahora siempre se ejecuta un PBKDF2 de
    verdad, exista o no el usuario, comparando contra un hash de relleno
    fijo cuando no existe."""
    row = conn.execute(
        "SELECT password_hash FROM dashboard_users WHERE login = ?",
        (normalize_login(login),),
    ).fetchone()
    if row is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return False
    return verify_password(password, row["password_hash"])


def _insert_sample(
    conn: DBConnection,
    *,
    repo: str,
    pr: int,
    semaforo: Semaforo,
    layers: dict[str, tuple[int, bool]],
    justification: str | None,
    weights: dict[str, float],
    timestamp: str,
    author_login: str,
    feedback: FeedbackValue | None = None,
) -> None:
    layer_results = {
        name: LayerResult(
            layer_name=name,
            risk_score=score,
            justification=justification or "",
            skipped=skipped,
            skip_reason="omitida" if skipped else None,
        )
        for name, (score, skipped) in layers.items()
    }
    score = int(
        sum(layer_results[n].risk_score * weights[n] for n in weights) / sum(weights.values())
    )
    score_id = insert_aggregated(
        conn,
        AggregatedResult(
            score=min(100, score),
            semaforo=semaforo,
            layer_results=layer_results,
            weights_used=weights,
            pr_id=str(pr),
            repo=repo,
            timestamp=timestamp,
        ),
        author_login=author_login,
    )
    if feedback is not None:
        set_feedback(conn, score_id, feedback)


def seed_demo(conn: DBConnection) -> None:
    """Usuarios locales + histórico falso para probar el dashboard sin CI."""
    # Cuentas locales (usuario / contraseña) — independientes de GitHub/GitLab.
    upsert_user(conn, "admin", "admin123", "Admin demo")
    upsert_user(conn, "maintainer", "maint123", "Mantenedor demo")
    upsert_user(conn, "reviewer", "review123", "Revisor demo")

    upsert_role(conn, "admin", "acme/payments-api", "admin_organizacion")
    upsert_role(conn, "admin", "acme/auth-service", "admin_organizacion")
    upsert_role(conn, "admin", "acme/infra-terraform", "admin_organizacion")
    upsert_role(conn, "maintainer", "acme/payments-api", "mantenedor")
    upsert_role(conn, "maintainer", "acme/auth-service", "mantenedor")
    upsert_role(conn, "reviewer", "acme/payments-api", "revisor")
    upsert_role(conn, "reviewer", "acme/auth-service", "revisor")

    existing = conn.execute("SELECT COUNT(*) AS n FROM pr_scores").fetchone()
    if existing and int(existing["n"]) > 0:
        return

    now = datetime.now(UTC)
    weights = dict(DEFAULT_WEIGHTS)

    def layers(
        static: int,
        deps: int,
        reputation: int,
        semantic: int,
        *,
        deps_skipped: bool = False,
        vulnerabilities: int = 0,
        vulnerabilities_skipped: bool = False,
    ) -> dict[str, tuple[int, bool]]:
        return {
            "static": (static, False),
            "deps": (deps, deps_skipped),
            "vulnerabilities": (vulnerabilities, vulnerabilities_skipped),
            "reputation": (reputation, False),
            "semantic": (semantic, False),
        }

    samples: list[
        tuple[
            str,
            int,
            Semaforo,
            dict[str, tuple[int, bool]],
            str | None,
            str,
            FeedbackValue | None,
        ]
    ] = [
        (
            "acme/payments-api",
            12,
            Semaforo.VERDE,
            layers(8, 5, 10, 12),
            "Refactor de logging sin superficie de ataque nueva.",
            "ana.lopez",
            "correcto",
        ),
        (
            "acme/payments-api",
            15,
            Semaforo.VERDE,
            layers(12, 8, 14, 18),
            "Actualización menor de dependencias ya auditadas.",
            "ana.lopez",
            "correcto",
        ),
        (
            "acme/payments-api",
            18,
            Semaforo.AMARILLO,
            layers(40, 55, 20, 48),
            "Dependencia con CVE media y eval() en util de parsing.",
            "carlos.rui",
            None,
        ),
        (
            "acme/payments-api",
            21,
            Semaforo.AMARILLO,
            layers(35, 60, 25, 44),
            "Paquete nuevo a distancia tipográfica de 'requests' (posible typosquat).",
            "carlos.rui",
            None,
        ),
        (
            "acme/payments-api",
            24,
            Semaforo.ROJO,
            layers(85, 70, 60, 92),
            "Payload ofuscado en script de build; posible exfiltración.",
            "ext-bot-91",
            None,
        ),
        (
            "acme/payments-api",
            27,
            Semaforo.ROJO,
            layers(78, 40, 72, 88),
            "curl | bash en Dockerfile + autor con cuenta de 2 días.",
            "ext-bot-91",
            None,
        ),
        (
            "acme/auth-service",
            7,
            Semaforo.VERDE,
            layers(4, 0, 15, 10, deps_skipped=True),
            "Cambio de tests; capa de deps omitida (sin lockfile tocado).",
            "maria.sanz",
            "correcto",
        ),
        (
            "acme/auth-service",
            9,
            Semaforo.AMARILLO,
            layers(30, 45, 50, 42),
            "Autor reciente con pocos commits firmados.",
            "nuevo-dev",
            None,
        ),
        (
            "acme/auth-service",
            11,
            Semaforo.VERDE,
            layers(15, 10, 20, 22),
            "Añade rate-limiting; sin hallazgos críticos.",
            "maria.sanz",
            None,
        ),
        (
            "acme/auth-service",
            14,
            Semaforo.ROJO,
            layers(90, 20, 55, 95),
            "Backdoor sutil: exfiltra tokens vía DNS en hook de install.",
            "ext-bot-91",
            None,
        ),
        (
            "acme/infra-terraform",
            3,
            Semaforo.VERDE,
            layers(6, 0, 8, 14, deps_skipped=True),
            "Cambio de tags en módulos Terraform.",
            "ops.irene",
            "correcto",
        ),
        (
            "acme/infra-terraform",
            5,
            Semaforo.AMARILLO,
            layers(50, 0, 30, 55, deps_skipped=True),
            "Apertura de security group 0.0.0.0/0 en un puerto no documentado.",
            "ops.irene",
            None,
        ),
        (
            "acme/infra-terraform",
            8,
            Semaforo.ROJO,
            layers(70, 0, 80, 85, deps_skipped=True),
            "Secret hardcodeado (AWS key) en variable de entorno del módulo.",
            "nuevo-dev",
            None,
        ),
    ]

    for i, (repo, pr, semaforo, layer_map, justification, author, feedback) in enumerate(samples):
        ts = (now - timedelta(days=len(samples) - i)).isoformat()
        _insert_sample(
            conn,
            repo=repo,
            pr=pr,
            semaforo=semaforo,
            layers=layer_map,
            justification=justification,
            weights=weights,
            timestamp=ts,
            author_login=author,
            feedback=feedback,
        )

    set_org_settings(
        conn,
        RepoSettings(
            weights=weights,
            thresholds={"amarillo": 34, "rojo": 66},
            layers_enabled=dict(DEFAULT_LAYERS),
            risk_colors=dict(DEFAULT_RISK_COLORS),
            block_on_high=True,
            require_feedback_on_high=False,
            source="default",
        ),
    )
    # Un repo con override de ejemplo; el resto hereda el default de organización.
    set_settings(
        conn,
        "acme/payments-api",
        RepoSettings(
            weights={
                "static": 0.3,
                "deps": 0.2,
                "vulnerabilities": 0.1,
                "reputation": 0.1,
                "semantic": 0.3,
            },
            thresholds={"amarillo": 30, "rojo": 70},
            layers_enabled=dict(DEFAULT_LAYERS),
            risk_colors={
                "verde": "#2f855a",
                "amarillo": "#c05621",
                "rojo": "#c53030",
            },
            block_on_high=True,
            require_feedback_on_high=True,
            source="repo",
        ),
    )


def compute_agent_metrics(conn: DBConnection) -> AgentUsageMetrics:
    try:
        rows = conn.execute(
            "SELECT agent_id, score FROM pr_scores WHERE agent_id IS NOT NULL AND agent_id != ''"
        ).fetchall()
    except Exception:
        rows = []

    agent_data: dict[str, dict[str, Any]] = {}
    for r in rows:
        agent_id = str(r["agent_id"])
        bucket = agent_data.setdefault(agent_id, {"count": 0, "score_sum": 0.0})
        bucket["count"] += 1
        bucket["score_sum"] += float(r["score"])

    token_usage: dict[str, int] = {}
    try:
        tu_rows = conn.execute("SELECT user_id, tokens_used FROM user_token_usage").fetchall()
        for tr in tu_rows:
            u_id = str(tr["user_id"])
            token_usage[u_id] = token_usage.get(u_id, 0) + int(tr["tokens_used"])
    except Exception:
        pass

    agent_rows: list[AgentMetricRow] = []
    total_tokens = sum(token_usage.values())

    all_agent_ids = set(agent_data.keys()).union(token_usage.keys())
    if not all_agent_ids:
        all_agent_ids = {"default-agent"}

    for aid in sorted(all_agent_ids):
        info = agent_data.get(aid, {"count": 0, "score_sum": 0.0})
        cnt = info["count"]
        avg_s = round(info["score_sum"] / cnt, 1) if cnt > 0 else 0.0
        toks = token_usage.get(aid, 0)
        agent_rows.append(
            AgentMetricRow(
                agent_id=aid,
                tokens_used=toks,
                analyses_count=cnt,
                avg_score=avg_s,
            )
        )

    return AgentUsageMetrics(
        total_tokens_used=total_tokens,
        agents_count=len(agent_rows),
        by_agent=agent_rows,
    )
