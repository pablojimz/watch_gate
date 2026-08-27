"""db.py — esquema y acceso a la base de datos histórica del Dashboard.

SQLite por defecto (fichero local, cero configuración). Si
``WATCHGATE_DASHBOARD_DATABASE_URL`` apunta a una URL ``postgres(ql)://``,
se usa Postgres en su lugar -- ambos dialectos se resuelven con el mismo
motor SQLAlchemy 2.0 (`watchgate.db.connection.build_engine`, que ya
normaliza el DSN al driver `psycopg` correcto), así que este módulo ya no
necesita ramificar por motor en ningún sitio: es el mismo código ORM tanto
en SQLite como en Postgres.

Las ~40 funciones de este módulo reciben una `Session` de SQLAlchemy (ver
`db_session()`) contra los modelos de `watchgate.dashboard.backend.models`
-- ese módulo documenta por qué usa su propia base declarativa
(`DashboardBase`), separada de `watchgate.db.models`: son dos bases de
datos físicamente distintas.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy import Engine, case, delete, func, select
from sqlalchemy.orm import Session

from watchgate.core.models import (
    AggregatedResult,
    Confidence,
    Finding,
    LayerResult,
    RiskCategory,
    Semaforo,
    ThreatNature,
)
from watchgate.dashboard.backend.models import (
    DashboardBase,
    DashboardPRScore,
    DashboardUser,
    LlmSettingsRow,
    OrgSettingsRow,
    RepoRole,
    RepoSettingsRow,
    UiSettingsRow,
)
from watchgate.dashboard.backend.schemas import (
    AgentMetricRow,
    AgentUsageMetrics,
    FeedbackValue,
    LlmSettingsIn,
    LlmSettingsOut,
    MyRepoRole,
    OrgMetrics,
    RepoMetricRow,
    RepoSettings,
    RoleName,
    ScoreOut,
    TrendPoint,
    UiSettings,
    UserSettingsIn,
    UserSettingsOut,
    normalize_login,
)
from watchgate.db.connection import build_engine
from watchgate.db.models import MonitoredRepo, VCSConnection
from watchgate.db.schema_guard import check_schema_matches_metadata

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


def _database_url(db_path: Path | None) -> str:
    """Mismo criterio de resolución que antes: `WATCHGATE_DASHBOARD_DATABASE_URL`
    (Postgres) tiene prioridad; si no, SQLite contra `db_path` (o
    `default_db_path()`, que a su vez lee `WATCHGATE_DASHBOARD_DB`).
    También sirve de clave de caché de motor -- dos llamadas que resuelven
    a la misma URL comparten el mismo `Engine`/el mismo guard de
    inicialización (ver `db_session()`)."""
    database_url = os.environ.get("WATCHGATE_DASHBOARD_DATABASE_URL")
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        return database_url
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


# Un `Engine` por URL destino (en la práctica, uno solo en producción -- el
# valor real no cambia; varios en tests, que apuntan cada uno a su propio
# fichero SQLite bajo `tmp_path`). Reusa `build_engine()` de
# `watchgate.db.connection` (mismo pooling, mismas pragmas WAL de SQLite,
# misma normalización de dialecto Postgres) en vez de reimplementarlo aquí.
_engines: dict[str, Engine] = {}
_engines_lock = threading.Lock()


def _get_engine(db_path: Path | None) -> Engine:
    target = _database_url(db_path)
    if target not in _engines:
        with _engines_lock:
            if target not in _engines:
                _engines[target] = build_engine(target)
    return _engines[target]


_MIGRATION_HINT = (
    "Aplica la migración pendiente con `alembic -c alembic_dashboard.ini "
    "upgrade head` (o, si es un entorno de desarrollo sin datos que "
    "conservar, borra/recrea la base de datos) antes de arrancar esta "
    "versión. Si la base de datos ya tenía estas tablas de antes de "
    "adoptar Alembic, primero hace falta `alembic -c alembic_dashboard.ini "
    "stamp head` una sola vez -- ver docs/despliegue.md."
)


def _init_schema(target_engine: Engine) -> None:
    check_schema_matches_metadata(
        target_engine, DashboardBase.metadata, migration_hint=_MIGRATION_HINT
    )
    DashboardBase.metadata.create_all(target_engine)
    with Session(target_engine) as session:
        ensure_org_settings(session)
        ensure_llm_settings(session)
        ensure_ui_settings(session)


def init_db(session: Session) -> None:
    """Crea el esquema si falta (idempotente). `db_session()` ya lo hace una
    vez por proceso/motor destino automáticamente (ver ahí el motivo real,
    un deadlock de Postgres reproducido bajo DDL concurrente) -- esta
    función queda pública porque `main.py` (arranque) y los tests la llaman
    también explícitamente, sin coste real de más: `create_all()`/el guard
    de columnas son solo lecturas de catálogo + DDL condicional
    (`CREATE TABLE IF NOT EXISTS`)."""
    engine = session.get_bind()
    assert isinstance(engine, Engine)
    _init_schema(engine)


_initialized_targets: set[str] = set()
_init_lock = threading.Lock()


@contextmanager
def db_session(db_path: Path | None = None) -> Iterator[Session]:
    target_engine = _get_engine(db_path)
    target = _database_url(db_path)
    # Bug real encontrado desplegando contra Postgres real: inicializar el
    # esquema (DDL con lock exclusivo de tabla) en CADA llamada a
    # `db_session()` -- es decir, en cada request de cada router -- hacía
    # que dos peticiones concurrentes ejecutando el mismo DDL a la vez
    # deadlockearan de verdad entre sí (`psycopg.errors.DeadlockDetected`,
    # reproducido en vivo). SQLite nunca lo mostró porque su locking es de
    # fichero completo, no por fila/tabla como Postgres. La inicialización
    # en sí ya es idempotente (`CREATE TABLE IF NOT EXISTS`), pero eso no
    # evita la carrera de dos conexiones comprobando/creando el mismo
    # esquema a la vez -- el problema no era el resultado final, era
    # ejecutarlo más de una vez por proceso sin necesidad. Con
    # double-checked locking, por cada motor destino real solo la primera
    # llamada del proceso inicializa el esquema; el resto la salta.
    if target not in _initialized_targets:
        with _init_lock:
            if target not in _initialized_targets:
                _init_schema(target_engine)
                _initialized_targets.add(target)
    session = Session(target_engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Mismo literal que watchgate.dashboard.backend.tasks.MAIN_BRANCH_SCAN_PR_ID
# -- no se importa desde aquí para no crear un ciclo (tasks.py ya importa
# de este módulo). `pr_number` es un INTEGER NOT NULL (no puede guardar
# "main" tal cual); 0 es un sentinel seguro porque un PR real de GitHub
# nunca es <= 0 -- `_record_to_score_out` deshace el mapeo al leer.
_MAIN_BRANCH_SCAN_PR_ID = "main"
_MAIN_BRANCH_SCAN_PR_NUMBER = 0


def _pr_number_from_pr_id(pr_id: str) -> int:
    if pr_id == _MAIN_BRANCH_SCAN_PR_ID:
        return _MAIN_BRANCH_SCAN_PR_NUMBER
    digits = "".join(ch for ch in pr_id if ch.isdigit())
    return int(digits) if digits else _MAIN_BRANCH_SCAN_PR_NUMBER


def _serialize_findings(layers: dict[str, LayerResult]) -> str | None:
    """Guarda lo que las columnas planas de `pr_scores` no capturan
    (`findings` con fichero/línea/regla, `category`, `confidence`,
    `threat_nature`, `justification` por capa) -- sin esto, el histórico
    del dashboard perdía toda la sustancia de un hallazgo (dónde está, qué
    regla lo disparó, POR QUÉ se dio ese risk_score) en cuanto se
    insertaba, aunque el propio `AggregatedResult` la tuviera en el
    momento del análisis. `None` si no hay nada que guardar, para no
    ensuciar filas de capas sin hallazgos con un JSON vacío.

    Bug real, reproducido: antes esta función no incluía `justification` en
    absoluto (solo se guardaba, en una columna dedicada aparte, la de la
    capa `semantic`) -- el dashboard mostraba el `risk_score` de
    static/dependencies/vulnerabilities/reputation sin ninguna explicación
    de por qué, aunque esas capas SÍ generan una justificación real (p. ej.
    reputation_layer.py siempre construye una frase con las señales
    concretas, o "No se han detectado señales de reputación sospechosas").
    Además, el filtro de qué capas se guardaban ni siquiera consideraba
    `justification` como motivo para incluir la capa -- `reputation`
    normalmente no tiene `category`/`confidence`/`threat_nature`, así que
    se descartaba entera pese a tener texto real que guardar."""
    payload = {
        name: {
            "findings": [f.model_dump(mode="json") for f in layer.findings],
            "category": layer.category.value if layer.category else None,
            "confidence": layer.confidence.value if layer.confidence else None,
            "threat_nature": layer.threat_nature.value if layer.threat_nature else None,
            "justification": layer.justification or None,
        }
        for name, layer in layers.items()
        if layer.findings
        or layer.category
        or layer.confidence
        or layer.threat_nature
        or layer.justification
    }
    return json.dumps(payload) if payload else None


def insert_aggregated(
    session: Session,
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

    static_layer_result = _get_layer("static")
    static_threat_nature = (
        static_layer_result.threat_nature.value
        if static_layer_result is not None and static_layer_result.threat_nature is not None
        else None
    )

    record = DashboardPRScore(
        repo=result.repo,
        pr_number=_pr_number_from_pr_id(result.pr_id),
        timestamp=result.timestamp,
        score=result.score,
        semaforo=result.semaforo.value,
        static_score=score_of("static"),
        static_skipped=skipped_of("static"),
        deps_score=score_of("deps"),
        deps_skipped=skipped_of("deps"),
        vulnerabilities_score=score_of("vulnerabilities"),
        vulnerabilities_skipped=skipped_of("vulnerabilities"),
        reputation_score=score_of("reputation"),
        reputation_skipped=skipped_of("reputation"),
        semantic_score=score_of("semantic"),
        semantic_skipped=skipped_of("semantic"),
        semantic_justification=justification,
        weights_json=json.dumps(result.weights_used),
        author_login=author_login,
        human_feedback=None,
        threat_summary_json=json.dumps(result.threat_summary),
        static_threat_nature=static_threat_nature,
        findings_json=_serialize_findings(layers),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record.id


def _record_to_score_out(record: DashboardPRScore) -> ScoreOut:
    findings_raw = record.findings_json
    findings_by_layer: dict[str, dict[str, Any]] = json.loads(findings_raw) if findings_raw else {}

    layer_results: dict[str, LayerResult] = {}
    for name, score_col, skip_col in _LAYER_COLS:
        skipped_val = getattr(record, skip_col)
        skipped = bool(skipped_val) if skipped_val is not None else True
        raw_score = getattr(record, score_col)

        extra = findings_by_layer.get(name, {})
        # `extra["justification"]` es el camino real desde el fix de este
        # bug (guardado por `_serialize_findings` para TODAS las capas, no
        # solo `semantic`). `record.semantic_justification` sigue de
        # respaldo para filas ya insertadas ANTES de este fix -- esas no
        # tienen "justification" en su blob (el código viejo nunca lo
        # guardó), pero sí conservan la columna dedicada de `semantic`.
        justification = (
            extra.get("justification")
            or (record.semantic_justification if name == "semantic" else None)
            or ""
        )
        findings = [Finding.model_validate(f) for f in extra.get("findings", [])]
        category = RiskCategory(extra["category"]) if extra.get("category") else None
        confidence = Confidence(extra["confidence"]) if extra.get("confidence") else None
        threat_nature = ThreatNature(extra["threat_nature"]) if extra.get("threat_nature") else None
        # Filas antiguas (o insertadas antes de que findings_json existiera)
        # solo tienen la naturaleza de la capa estática en su columna
        # dedicada -- se usa como respaldo cuando el blob no la trae.
        if name == "static" and threat_nature is None and record.static_threat_nature:
            threat_nature = ThreatNature(record.static_threat_nature)

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

    weights = json.loads(record.weights_json or "{}")
    threat_summary = json.loads(record.threat_summary_json or "{}")
    result = AggregatedResult(
        score=int(record.score),
        semaforo=Semaforo(record.semaforo),
        layer_results=layer_results,
        weights_used=weights,
        pr_id=(
            _MAIN_BRANCH_SCAN_PR_ID
            if record.pr_number == _MAIN_BRANCH_SCAN_PR_NUMBER
            else str(record.pr_number)
        ),
        repo=record.repo,
        timestamp=record.timestamp,
        threat_summary=threat_summary,
    )
    return ScoreOut.from_aggregated(
        score_id=record.id,
        result=result,
        human_feedback=cast("FeedbackValue | None", record.human_feedback),
        author_login=record.author_login,
        accepted_by=record.accepted_by,
        accepted_at=record.accepted_at,
        pr_state=record.pr_state,
    )


def list_scores(session: Session, repo: str, limit: int | None = None) -> list[ScoreOut]:
    """`limit=None` (por defecto) trae todo el histórico, como antes -- lo
    usa el propio dashboard. Los callers que ya sabían cuántas filas
    necesitaban (p. ej. `agent_access.py::repo_score_history`) recortaban en
    Python después de traer la tabla entera; pasar `limit` aquí mueve el
    corte al propio SQL (el índice `idx_repo_timestamp` ya cubre el
    WHERE+ORDER BY, así que LIMIT no cuesta un escaneo completo)."""
    stmt = (
        select(DashboardPRScore)
        .where(DashboardPRScore.repo == repo)
        .order_by(DashboardPRScore.timestamp.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    records = session.execute(stmt).scalars().all()
    return [_record_to_score_out(r) for r in records]


def get_score(session: Session, score_id: int) -> ScoreOut | None:
    record = session.get(DashboardPRScore, score_id)
    return None if record is None else _record_to_score_out(record)


def delete_scores_for_repo(session: Session, repo: str) -> int:
    """Borra TODO el histórico de `pr_scores` de un repo -- usado por
    `routers/scores.py::delete_repo_by_path` cuando el usuario elimina un
    repo desde `/repos`. A diferencia de `routers/repos.py::
    delete_external_repo` (que solo borra la fila `MonitoredRepo` y
    preserva el histórico a propósito), esto SÍ es destructivo: muchos
    repos reales llegan aquí solo vía ingesta de CI (`POST /scores`), sin
    fila `MonitoredRepo` de por medio -- para esos, el histórico de scores
    es la ÚNICA representación del repo en el Dashboard, así que "eliminar
    el repo" solo puede significar borrar ese histórico. Devuelve cuántas
    filas se borraron."""
    result = session.execute(delete(DashboardPRScore).where(DashboardPRScore.repo == repo))
    session.commit()
    return result.rowcount or 0  # type: ignore[attr-defined]


def delete_scores_older_than(session: Session, retention_days: int) -> int:
    """Borra `pr_scores` con `timestamp` anterior a `retention_days` días
    -- usado por la purga periódica (`tasks.py::purge_old_scores`).
    `timestamp` se guarda como ISO 8601 en texto (no una columna de
    fecha real, ver `_record_to_score_out`), pero el formato ISO ordena
    lexicográficamente igual que cronológicamente, así que comparar como
    string contra el corte calculado en Python es correcto y evita
    depender de funciones de fecha específicas del dialecto (SQLite vs
    Postgres)."""
    cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
    result = session.execute(delete(DashboardPRScore).where(DashboardPRScore.timestamp < cutoff))
    session.commit()
    return result.rowcount or 0  # type: ignore[attr-defined]


def set_feedback(session: Session, score_id: int, feedback: FeedbackValue) -> ScoreOut | None:
    record = session.get(DashboardPRScore, score_id)
    if record is None:
        return None
    record.human_feedback = feedback
    session.commit()
    session.refresh(record)
    return _record_to_score_out(record)


def set_accepted(session: Session, score_id: int, user_login: str) -> ScoreOut | None:
    """Gate de aprobación manual: un mantenedor/admin marca un PR en amarillo/
    rojo como revisado y aceptado a sabiendas del riesgo. Distinto del
    `human_feedback` de arriba (que valora si el ANÁLISIS acertó, no si el
    riesgo real se acepta) -- deliberadamente independiente para no mezclar
    "el score está mal" con "el score está bien pero seguimos adelante"."""
    record = session.get(DashboardPRScore, score_id)
    if record is None:
        return None
    record.accepted_by = normalize_login(user_login)
    record.accepted_at = datetime.now(UTC).isoformat()
    session.commit()
    session.refresh(record)
    return _record_to_score_out(record)


def clear_accepted(session: Session, score_id: int) -> ScoreOut | None:
    record = session.get(DashboardPRScore, score_id)
    if record is None:
        return None
    record.accepted_by = None
    record.accepted_at = None
    session.commit()
    session.refresh(record)
    return _record_to_score_out(record)


def get_role(session: Session, user_login: str, repo: str) -> RoleName | None:
    record = session.get(RepoRole, (normalize_login(user_login), repo))
    return None if record is None else cast("RoleName", record.role)


def _dialect_insert(session: Session) -> Any:
    """`sqlalchemy.dialects.{postgresql,sqlite}.insert` según el dialecto
    de `session` -- ambos exponen `.on_conflict_do_update(...)`, mismo
    patrón dialect-aware ya establecido en
    `watchgate.db.repository.record_token_usage`, reusado (no reinventado)
    en cada upsert de este módulo."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert

        return _insert
    from sqlalchemy.dialects.sqlite import insert as _insert  # type: ignore[assignment]

    return _insert


def upsert_role(session: Session, user_login: str, repo: str, role: RoleName) -> None:
    table = RepoRole.__table__
    insert_ = _dialect_insert(session)
    stmt = insert_(table).values(user_login=normalize_login(user_login), repo=repo, role=role)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.user_login, table.c.repo],
        set_={"role": stmt.excluded.role},
    )
    session.execute(stmt)
    session.commit()


def delete_role(session: Session, user_login: str, repo: str) -> bool:
    record = session.get(RepoRole, (normalize_login(user_login), repo))
    if record is None:
        return False
    session.delete(record)
    session.commit()
    return True


def list_roles(session: Session, repo: str | None = None) -> list[dict[str, str]]:
    stmt = select(RepoRole)
    if repo is None:
        stmt = stmt.order_by(RepoRole.repo, RepoRole.user_login)
    else:
        stmt = stmt.where(RepoRole.repo == repo).order_by(RepoRole.user_login)
    records = session.execute(stmt).scalars().all()
    return [{"user_login": r.user_login, "repo": r.repo, "role": r.role} for r in records]


def list_roles_for_user(session: Session, user_login: str) -> list[dict[str, str]]:
    """Desglose de `repo_roles` de un usuario concreto, un elemento por
    repo -- distinto de `get_user_highest_role` (un único rol agregado, el
    más alto de todos) y de `list_roles` (todos los usuarios de un repo, o
    todo `repo_roles` entero sin filtrar). Usado por
    `get_user_settings`/`GET /api/settings/user` para que cada quien pueda
    ver en qué repos tiene qué rol, no solo su rol más alto."""
    norm_login = normalize_login(user_login)
    stmt = select(RepoRole.repo, RepoRole.role).where(RepoRole.user_login == norm_login)
    stmt = stmt.order_by(RepoRole.repo)
    return [{"repo": repo, "role": role} for repo, role in session.execute(stmt).all()]


def list_repos_for_user(session: Session, user_login: str, is_admin: bool) -> list[str]:
    if is_admin:
        from_scores = set(session.execute(select(DashboardPRScore.repo).distinct()).scalars().all())
        from_roles = set(session.execute(select(RepoRole.repo).distinct()).scalars().all())
        from_settings = set(
            session.execute(select(RepoSettingsRow.repo).distinct()).scalars().all()
        )
        return sorted(from_scores | from_roles | from_settings)

    stmt = (
        select(RepoRole.repo)
        .distinct()
        .where(RepoRole.user_login == normalize_login(user_login))
        .order_by(RepoRole.repo)
    )
    return list(session.execute(stmt).scalars().all())


def user_is_org_admin(session: Session, user_login: str) -> bool:
    stmt = (
        select(RepoRole)
        .where(
            RepoRole.user_login == normalize_login(user_login),
            RepoRole.role == "admin_organizacion",
        )
        .limit(1)
    )
    return session.execute(stmt).scalars().first() is not None


def ensure_org_settings(session: Session) -> None:
    if session.get(OrgSettingsRow, 1) is not None:
        return
    session.add(
        OrgSettingsRow(
            id=1,
            weights_json=json.dumps(DEFAULT_WEIGHTS),
            thresholds_json=json.dumps(DEFAULT_THRESHOLDS),
            layers_enabled_json=json.dumps(DEFAULT_LAYERS),
            risk_colors_json=json.dumps(DEFAULT_RISK_COLORS),
            block_on_high=True,
            require_feedback_on_high=False,
        )
    )
    session.commit()


def _settings_from_record(
    record: RepoSettingsRow | OrgSettingsRow | None, *, source: Literal["default", "repo"]
) -> RepoSettings:
    if record is None:
        return RepoSettings(
            weights=dict(DEFAULT_WEIGHTS),
            thresholds=dict(DEFAULT_THRESHOLDS),
            layers_enabled=dict(DEFAULT_LAYERS),
            risk_colors=dict(DEFAULT_RISK_COLORS),
            block_on_high=True,
            require_feedback_on_high=False,
            source=source,
        )
    layers = json.loads(record.layers_enabled_json or "{}") or dict(DEFAULT_LAYERS)
    colors = json.loads(record.risk_colors_json or "{}") or dict(DEFAULT_RISK_COLORS)
    merged_colors = {**DEFAULT_RISK_COLORS, **colors}
    return RepoSettings(
        weights=json.loads(record.weights_json),
        thresholds=json.loads(record.thresholds_json),
        layers_enabled=layers,
        risk_colors=merged_colors,
        block_on_high=bool(record.block_on_high),
        require_feedback_on_high=bool(record.require_feedback_on_high),
        source=source,
    )


def get_org_settings(session: Session) -> RepoSettings:
    ensure_org_settings(session)
    return _settings_from_record(session.get(OrgSettingsRow, 1), source="default")


def set_org_settings(session: Session, settings: RepoSettings) -> RepoSettings:
    ensure_org_settings(session)
    record = session.get(OrgSettingsRow, 1)
    assert record is not None
    record.weights_json = json.dumps(settings.weights)
    record.thresholds_json = json.dumps(settings.thresholds)
    record.layers_enabled_json = json.dumps(settings.layers_enabled)
    record.risk_colors_json = json.dumps(settings.risk_colors)
    record.block_on_high = settings.block_on_high
    record.require_feedback_on_high = settings.require_feedback_on_high
    session.commit()
    return get_org_settings(session)


def get_settings(session: Session, repo: str) -> RepoSettings:
    record = session.get(RepoSettingsRow, repo)
    if record is None:
        defaults = get_org_settings(session)
        return defaults.model_copy(update={"source": "default"})
    return _settings_from_record(record, source="repo")


def set_settings(session: Session, repo: str, settings: RepoSettings) -> RepoSettings:
    table = RepoSettingsRow.__table__
    values = {
        "repo": repo,
        "weights_json": json.dumps(settings.weights),
        "thresholds_json": json.dumps(settings.thresholds),
        "layers_enabled_json": json.dumps(settings.layers_enabled),
        "risk_colors_json": json.dumps(settings.risk_colors),
        "block_on_high": settings.block_on_high,
        "require_feedback_on_high": settings.require_feedback_on_high,
    }
    insert_ = _dialect_insert(session)
    stmt = insert_(table).values(**values)
    update_cols = {k: getattr(stmt.excluded, k) for k in values if k != "repo"}
    stmt = stmt.on_conflict_do_update(index_elements=[table.c.repo], set_=update_cols)
    session.execute(stmt)
    session.commit()
    return get_settings(session, repo)


def clear_repo_settings(session: Session, repo: str) -> RepoSettings:
    record = session.get(RepoSettingsRow, repo)
    if record is not None:
        session.delete(record)
        session.commit()
    return get_settings(session, repo)


def _mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "••••••••"
    return f"{api_key[:4]}…{api_key[-4:]}"


def ensure_llm_settings(session: Session) -> None:
    if session.get(LlmSettingsRow, 1) is not None:
        return
    session.add(
        LlmSettingsRow(
            id=1,
            provider=DEFAULT_LLM["provider"],
            model=DEFAULT_LLM["model"],
            base_url=DEFAULT_LLM["base_url"],
            api_key=None,
            monthly_budget_tokens=DEFAULT_LLM["monthly_budget_tokens"],
            max_diff_tokens=DEFAULT_LLM["max_diff_tokens"],
        )
    )
    session.commit()


def get_llm_settings(session: Session) -> LlmSettingsOut:
    ensure_llm_settings(session)
    record = session.get(LlmSettingsRow, 1)
    assert record is not None
    api_key = record.api_key
    gh_token = record.github_token
    return LlmSettingsOut(
        provider=record.provider,  # type: ignore[arg-type]
        model=record.model,
        base_url=record.base_url,
        api_key_set=bool(api_key),
        api_key_masked=_mask_api_key(api_key),
        monthly_budget_tokens=record.monthly_budget_tokens,
        max_diff_tokens=record.max_diff_tokens,
        github_api_url=record.github_api_url or "https://api.github.com",
        github_token_set=bool(gh_token),
        github_token_masked=_mask_api_key(gh_token),
    )


def set_llm_settings(session: Session, body: LlmSettingsIn) -> LlmSettingsOut:
    ensure_llm_settings(session)
    record = session.get(LlmSettingsRow, 1)
    assert record is not None
    current_key = record.api_key
    if body.clear_api_key:
        new_key = None
    elif body.api_key is not None and body.api_key.strip():
        new_key = body.api_key.strip()
    else:
        new_key = current_key

    current_gh_token = record.github_token
    if body.clear_github_token:
        new_gh_token = None
    elif body.github_token is not None and body.github_token.strip():
        new_gh_token = body.github_token.strip()
    else:
        new_gh_token = current_gh_token

    record.provider = body.provider
    record.model = body.model
    record.base_url = body.base_url
    record.api_key = new_key
    record.monthly_budget_tokens = body.monthly_budget_tokens
    record.max_diff_tokens = body.max_diff_tokens
    record.github_api_url = (
        body.github_api_url.strip() if body.github_api_url else "https://api.github.com"
    )
    record.github_token = new_gh_token
    session.commit()
    return get_llm_settings(session)


def get_user_highest_role(session: Session, user_login: str) -> RoleName:
    norm_login = normalize_login(user_login)
    if user_is_org_admin(session, norm_login):
        return "admin_organizacion"
    roles = session.scalars(select(RepoRole.role).where(RepoRole.user_login == norm_login)).all()
    if "mantenedor" in roles:
        return "mantenedor"
    return "revisor"


def get_user_settings(session: Session, login: str) -> UserSettingsOut:
    norm_login = normalize_login(login)
    user = session.get(DashboardUser, norm_login)
    if not user:
        raise ValueError(f"Usuario no encontrado: {login}")

    role = get_user_highest_role(session, norm_login)
    gh_token = user.github_token

    ui_settings = None
    if user.ui_settings_json:
        try:
            ui_settings = UiSettings.model_validate_json(user.ui_settings_json)
        except Exception:
            pass

    repo_roles = [
        MyRepoRole(repo=r["repo"], role=cast("RoleName", r["role"]))
        for r in list_roles_for_user(session, norm_login)
    ]

    return UserSettingsOut(
        login=user.login,
        display_name=user.display_name,
        role=role,
        repo_roles=repo_roles,
        github_api_url=user.github_api_url or "https://api.github.com",
        github_token_set=bool(gh_token),
        github_token_masked=_mask_api_key(gh_token),
        ui_settings=ui_settings,
    )


def set_user_settings(session: Session, login: str, body: UserSettingsIn) -> UserSettingsOut:
    norm_login = normalize_login(login)
    user = session.get(DashboardUser, norm_login)
    if not user:
        raise ValueError(f"Usuario no encontrado: {login}")

    if body.display_name and body.display_name.strip():
        user.display_name = body.display_name.strip()

    if body.github_api_url is not None:
        user.github_api_url = (
            body.github_api_url.strip() if body.github_api_url.strip() else "https://api.github.com"
        )

    if body.clear_github_token:
        user.github_token = None
    elif body.github_token is not None and body.github_token.strip():
        user.github_token = body.github_token.strip()

    if body.ui_settings is not None:
        user.ui_settings_json = body.ui_settings.model_dump_json()

    session.commit()
    return get_user_settings(session, norm_login)


def resolve_github_credentials(
    session: Session,
    user_login: str | None = None,
    repo_path: str | None = None,
) -> tuple[str | None, str]:
    """Cascada de 5 niveles para resolver token y URL de la API de GitHub:
    1. Token Personal del Usuario (user.github_token).
    2. Token de VCSConnection del MonitoredRepo (vcs.access_token).
    3. Token Fallback de la Org (LlmSettingsRow.github_token).
    4. Variables de Entorno (WATCHGATE_GITHUB_TOKEN / GITHUB_TOKEN).
    5. Petición Anónima.
    """
    token: str | None = None
    api_url: str = "https://api.github.com"

    # Nivel 1: Usuario
    if user_login:
        norm_login = normalize_login(user_login)
        user = session.get(DashboardUser, norm_login)
        if user:
            if user.github_token:
                token = user.github_token
            if user.github_api_url:
                api_url = user.github_api_url

    # Nivel 2: VCSConnection del Repositorio -- OJO, `MonitoredRepo`/
    # `VCSConnection` son modelos de la ENGINE DB
    # (`watchgate.db.models`), no de esta base de datos del Dashboard:
    # `session` (el parámetro de esta función) está bound al motor del
    # Dashboard, que no tiene esas tablas -- consultarlas con `session`
    # directamente lanza `OperationalError: no such table: monitored_repos`
    # (reproducido en vivo). Sesión propia y aparte, contra el motor
    # correcto -- mismo motivo/patrón que el fix de `compute_agent_metrics`
    # más abajo en este mismo fichero. `.first()` en vez de
    # `.scalar_one_or_none()`: `repo_path` no es único a secas (dos
    # organizaciones distintas pueden auditar el mismo repo_path, ver
    # comentario en `routers/repos.py::_enqueue_main_branch_scan`), así
    # que más de una fila coincidiendo es un caso real, no un error de
    # integridad -- cualquiera de las dos sirve igual para resolver un
    # token de lectura.
    if not token and repo_path:
        from watchgate.db.connection import get_session as get_engine_session

        with next(get_engine_session()) as engine_session:
            repo = (
                engine_session.execute(
                    select(MonitoredRepo).where(
                        MonitoredRepo.repo_path == repo_path  # type: ignore[arg-type]
                    )
                )
                .scalars()
                .first()
            )
            if repo and repo.vcs_connection_id:
                vcs = engine_session.get(VCSConnection, repo.vcs_connection_id)
                if vcs and vcs.access_token:
                    token = vcs.access_token

    # Nivel 3: Fallback de la Org (LlmSettingsRow)
    ensure_llm_settings(session)
    llm = session.get(LlmSettingsRow, 1)
    if llm:
        if not token and llm.github_token:
            token = llm.github_token
        if api_url == "https://api.github.com" and llm.github_api_url:
            api_url = llm.github_api_url

    # Nivel 4: Variables de entorno
    if not token:
        token = os.environ.get("WATCHGATE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if api_url == "https://api.github.com":
        env_url = os.environ.get("WATCHGATE_GITHUB_API_URL")
        if env_url:
            api_url = env_url

    return token, api_url


def ensure_ui_settings(session: Session) -> None:
    if session.get(UiSettingsRow, 1) is not None:
        return
    defaults = DEFAULT_UI
    session.add(
        UiSettingsRow(
            id=1,
            primary_color=defaults.primary_color,
            accent_color=defaults.accent_color,
            radius=defaults.radius,
            font_scale=defaults.font_scale,
            density=defaults.density,
            default_theme=defaults.default_theme,
        )
    )
    session.commit()


def get_ui_settings(session: Session) -> UiSettings:
    ensure_ui_settings(session)
    record = session.get(UiSettingsRow, 1)
    assert record is not None
    return UiSettings(
        primary_color=record.primary_color,
        accent_color=record.accent_color,
        radius=record.radius,  # type: ignore[arg-type]
        font_scale=record.font_scale,  # type: ignore[arg-type]
        density=record.density,  # type: ignore[arg-type]
        default_theme=record.default_theme,  # type: ignore[arg-type]
        logo_data_url=record.logo_data_url,
    )


def set_ui_settings(session: Session, settings: UiSettings) -> UiSettings:
    ensure_ui_settings(session)
    record = session.get(UiSettingsRow, 1)
    assert record is not None
    record.primary_color = settings.primary_color
    record.accent_color = settings.accent_color
    record.radius = settings.radius
    record.font_scale = settings.font_scale
    record.density = settings.density
    record.default_theme = settings.default_theme
    record.logo_data_url = settings.logo_data_url
    session.commit()
    return get_ui_settings(session)


def compute_org_metrics(session: Session, repos: list[str]) -> OrgMetrics:
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

    # Agregación en SQL en vez de traer TODO el histórico visible de la
    # organización fila a fila y sumar en Python -- antes, una organización
    # con años de PRs analizados cargaba cada score entero a memoria del
    # proceso del dashboard-backend solo para calcular medias y conteos que
    # Postgres/SQLite ya saben hacer en el motor. `func.avg()` ignora NULL
    # solo (no falsos ceros), igual que el filtro `score_val is not None`
    # de la versión anterior; el redondeo a 1 decimal se sigue haciendo en
    # Python (no en SQL) para no depender de que SQLite/Postgres redondeen
    # igual entre sí ni igual que `round()`.
    filters = (DashboardPRScore.repo.in_(repos),)

    def _skipped_or_missing(score_col: str, skip_col: str) -> Any:
        included = (getattr(DashboardPRScore, skip_col).is_not(True)) & (
            getattr(DashboardPRScore, score_col).isnot(None)
        )
        return func.avg(case((included, getattr(DashboardPRScore, score_col)), else_=None))

    # `SUM()` sobre cero filas (un repo recién añadido, sin histórico
    # todavía) devuelve SQL NULL, no 0 -- a diferencia de `COUNT()`, que sí
    # devuelve 0. Sin `coalesce()` aquí, `int(overall.feedback_pending)` (y
    # el resto de sumas) reventaría con `TypeError: int() argument ... NoneType`
    # justo en el caso "repo sin PRs todavía" que el guard `if not repos`
    # de arriba no cubre (ahí `repos` no está vacío, son sus *filas* las
    # que están vacías).
    def _sum_case(*whens: Any, else_: int) -> Any:
        return func.coalesce(func.sum(case(*whens, else_=else_)), 0)

    layer_avg_cols = {layer: f"layer_avg_{layer}" for layer, _, _ in _LAYER_COLS}
    overall_stmt = select(
        func.count().label("total"),
        func.avg(DashboardPRScore.score).label("avg_score"),
        *(
            _sum_case((DashboardPRScore.semaforo == sem, 1), else_=0).label(f"semaforo_{sem}")
            for sem in ("verde", "amarillo", "rojo")
        ),
        _sum_case((DashboardPRScore.human_feedback == "correcto", 1), else_=0).label(
            "feedback_correct"
        ),
        _sum_case((DashboardPRScore.human_feedback == "falso_positivo", 1), else_=0).label(
            "feedback_fp"
        ),
        # Pendiente = ni "correcto" ni "falso_positivo" (incluye NULL) --
        # misma rama `else` que la versión en Python, no solo `IS NULL`.
        _sum_case(
            (DashboardPRScore.human_feedback == "correcto", 0),
            (DashboardPRScore.human_feedback == "falso_positivo", 0),
            else_=1,
        ).label("feedback_pending"),
        *(
            _skipped_or_missing(score_col, skip_col).label(layer_avg_cols[layer])
            for layer, score_col, skip_col in _LAYER_COLS
        ),
    ).where(*filters)
    overall = session.execute(overall_stmt).one()

    def _round_avg(value: float | None) -> float:
        return round(float(value), 1) if value is not None else 0.0

    total = int(overall.total)
    avg_score = _round_avg(overall.avg_score)
    by_semaforo = {
        sem: int(getattr(overall, f"semaforo_{sem}")) for sem in ("verde", "amarillo", "rojo")
    }
    feedback_correct = int(overall.feedback_correct)
    feedback_fp = int(overall.feedback_fp)
    feedback_pending = int(overall.feedback_pending)
    layer_avg = {
        layer: _round_avg(getattr(overall, layer_avg_cols[layer])) for layer, _, _ in _LAYER_COLS
    }

    per_repo_stmt = (
        select(
            DashboardPRScore.repo,
            func.count().label("prs"),
            func.avg(DashboardPRScore.score).label("avg_score"),
            func.sum(case((DashboardPRScore.semaforo == "verde", 1), else_=0)).label("verde"),
            func.sum(case((DashboardPRScore.semaforo == "amarillo", 1), else_=0)).label("amarillo"),
            func.sum(case((DashboardPRScore.semaforo == "rojo", 1), else_=0)).label("rojo"),
            func.sum(case((DashboardPRScore.human_feedback.is_(None), 1), else_=0)).label(
                "feedback_pending"
            ),
        )
        .where(*filters)
        .group_by(DashboardPRScore.repo)
        .order_by(DashboardPRScore.repo)
    )
    by_repo = [
        RepoMetricRow(
            repo=row.repo,
            prs=int(row.prs),
            avg_score=_round_avg(row.avg_score),
            verde=int(row.verde),
            amarillo=int(row.amarillo),
            rojo=int(row.rojo),
            feedback_pending=int(row.feedback_pending),
        )
        for row in session.execute(per_repo_stmt)
    ]

    # `timestamp` se guarda como TEXT ISO 8601 (ver DashboardPRScore), no un
    # tipo temporal real -- `substr(..., 1, 10)` extrae "AAAA-MM-DD" igual
    # en SQLite y Postgres (alias estándar de `substring`), sin depender de
    # funciones de fecha específicas de cada dialecto.
    day_expr = func.substr(DashboardPRScore.timestamp, 1, 10)
    trend_stmt = (
        select(
            day_expr.label("day"),
            func.avg(DashboardPRScore.score).label("avg_score"),
            # Etiqueta "pr_count", no "count" -- Row hereda `count()` de
            # tuple, y `row.count` resolvería al método heredado en vez de
            # a la columna (mypy lo pilla; en runtime habría devuelto un
            # `Callable` en vez de un `int`).
            func.count().label("pr_count"),
        )
        .where(*filters)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    trend = [
        TrendPoint(day=row.day, avg_score=_round_avg(row.avg_score), count=int(row.pr_count))
        for row in session.execute(trend_stmt)
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


def upsert_user(session: Session, login: str, password: str, display_name: str) -> None:
    table = DashboardUser.__table__
    insert_ = _dialect_insert(session)
    stmt = insert_(table).values(
        login=normalize_login(login),
        password_hash=hash_password(password),
        display_name=display_name,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.login],
        set_={
            "password_hash": stmt.excluded.password_hash,
            "display_name": stmt.excluded.display_name,
        },
    )
    session.execute(stmt)
    session.commit()


# Hash de relleno con el mismo coste (120.000 iteraciones PBKDF2) que un
# hash real, para que `authenticate_user` tarde lo mismo tanto si el login
# existe como si no -- ver el comentario dentro de la función.
_DUMMY_PASSWORD_HASH = hash_password("watchgate-dummy-timing-safe-password")


def authenticate_user(session: Session, login: str, password: str) -> bool:
    """Antes, un login inexistente devolvía `False` de inmediato, mientras
    que uno existente calculaba un PBKDF2 de 120.000 iteraciones (lento a
    propósito) antes de comparar -- la diferencia de tiempo es medible y
    permite enumerar logins válidos contra `/api/auth/login`, más aún sin
    ningún rate limiting delante. Ahora siempre se ejecuta un PBKDF2 de
    verdad, exista o no el usuario, comparando contra un hash de relleno
    fijo cuando no existe."""
    record = session.get(DashboardUser, normalize_login(login))
    if record is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return False
    return verify_password(password, record.password_hash)


def get_user(session: Session, login: str) -> DashboardUser | None:
    return session.get(DashboardUser, normalize_login(login))


def change_password(session: Session, login: str, new_password: str) -> bool:
    """Actualiza solo `password_hash` -- a diferencia de `upsert_user`
    (que también sobrescribe `display_name`, pensado para el alta desde
    Configuración), esto es para que un usuario cambie su propia
    contraseña sin arriesgarse a pisar su nombre para mostrar con un valor
    obsoleto. Devuelve `False` si el login no tiene cuenta local (usuario
    solo-OAuth/OIDC, sin fila en `dashboard_users`) -- el caller decide qué
    mensaje dar."""
    record = session.get(DashboardUser, normalize_login(login))
    if record is None:
        return False
    record.password_hash = hash_password(new_password)
    session.commit()
    return True


def list_users(session: Session) -> list[DashboardUser]:
    stmt = select(DashboardUser).order_by(DashboardUser.login)
    return list(session.execute(stmt).scalars().all())


def is_last_org_admin(session: Session, login: str) -> bool:
    """`True` si `login` tiene rol `admin_organizacion` en algún repo Y es
    el ÚNICO login con ese rol -- usado para bloquear una acción (borrar
    la cuenta, quitarle el último rol de admin) que dejaría la
    organización sin ningún admin_organizacion capaz de gestionar accesos
    después."""
    norm_login = normalize_login(login)
    admin_logins = set(
        session.execute(
            select(RepoRole.user_login).where(RepoRole.role == "admin_organizacion").distinct()
        )
        .scalars()
        .all()
    )
    return norm_login in admin_logins and len(admin_logins) <= 1


def delete_user(session: Session, login: str) -> bool:
    """Borra la cuenta local y, en cascada, TODOS sus roles asignados
    (`repo_roles`) -- sin este segundo borrado quedarían filas huérfanas
    apuntando a un login que ya no puede autenticarse nunca (ni con
    contraseña -- la cuenta desaparece -- ni heredando un rol ya asignado
    si algún día vuelve a entrar por GitHub/OIDC con el mismo login)."""
    norm_login = normalize_login(login)
    user = session.get(DashboardUser, norm_login)
    if user is None:
        return False
    stale_roles = (
        session.execute(select(RepoRole).where(RepoRole.user_login == norm_login)).scalars().all()
    )
    for role_row in stale_roles:
        session.delete(role_row)
    session.delete(user)
    session.commit()
    return True


def list_pr_numbers_for_repo(session: Session, repo: str) -> set[str]:
    """Números de PR (como texto) ya presentes en el histórico del
    Dashboard para `repo` -- usado por el barrido de polling
    (`watchgate.service.repo_polling`) para no reencolar análisis ya
    hechos. Antes esto era una query SQL inline contra una columna
    `pr_id` que NUNCA existió en esta tabla (es `pr_number`, ver
    `DashboardPRScore`) -- envuelta en un `except Exception: pass` que la
    tragaba en silencio, así que ese filtro nunca aportó nada (hallazgo
    real de esta migración)."""
    stmt = select(DashboardPRScore.pr_number).where(DashboardPRScore.repo == repo)
    return {str(n) for n in session.execute(stmt).scalars().all()}


def mark_prs_closed(session: Session, repo: str, closed_pr_numbers: set[str]) -> int:
    """Marca como `pr_state="closed"` las filas de `repo` cuyo `pr_number`
    esté en `closed_pr_numbers` y sigan en "open" -- llamado desde
    `RepoPollingService._poll_single_candidate` (watchgate/service/
    repo_polling.py) cuando una PR que sí estaba trackeada deja de aparecer
    en la lista de PRs abiertas de GitHub.

    Nunca borra ni toca el análisis en sí (score/justificación/hallazgos
    intactos) -- solo dejan de contar como "pendiente" en el dashboard. Se
    excluye a propósito `pr_number = 0` (análisis de rama principal,
    `_MAIN_BRANCH_SCAN_PR_NUMBER`): no es una PR real de GitHub, nunca debe
    poder "cerrarse" por este camino aunque su número textual coincidiera
    por accidente con el de una PR real cerrada.

    Devuelve cuántas filas se actualizaron (0 si `closed_pr_numbers` está
    vacío o ninguna coincide -- caso normal en la mayoría de barridos)."""
    if not closed_pr_numbers:
        return 0
    numeric = {int(n) for n in closed_pr_numbers if n.isdigit() and int(n) != 0}
    if not numeric:
        return 0
    stmt = (
        select(DashboardPRScore)
        .where(DashboardPRScore.repo == repo)
        .where(DashboardPRScore.pr_number.in_(numeric))
        .where(DashboardPRScore.pr_state == "open")
    )
    records = session.execute(stmt).scalars().all()
    for record in records:
        record.pr_state = "closed"
    session.commit()
    return len(records)


def _insert_sample(
    session: Session,
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
        session,
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
        set_feedback(session, score_id, feedback)


def seed_demo(session: Session) -> None:
    """Usuarios locales + histórico falso para probar el dashboard sin CI.

    Semilla de UNA sola vez -- decisión explícita (2026-08-27): antes esto
    corría entero en CADA arranque del backend, así que si alguien
    limpiaba a mano los repos `acme/*` de ejemplo (para que el dashboard
    no pareciera un demo, con datos reales de verdad), un
    `docker compose restart` los volvía a crear sin avisar
    (`upsert_role` no es condicional). Se detecta con la cuenta "admin":
    si ya existe, se asume que el seed ya corrió alguna vez y no se toca
    nada más -- ni cuentas, ni roles, ni scores -- aunque se hayan borrado
    después a mano."""
    if get_user(session, "admin") is not None:
        return

    # Cuentas locales (usuario / contraseña) — independientes de GitHub/GitLab.
    upsert_user(session, "admin", "Admin123", "Admin demo")
    upsert_user(session, "maintainer", "maint123", "Mantenedor demo")
    upsert_user(session, "reviewer", "review123", "Revisor demo")

    upsert_role(session, "admin", "acme/payments-api", "admin_organizacion")
    upsert_role(session, "admin", "acme/auth-service", "admin_organizacion")
    upsert_role(session, "admin", "acme/infra-terraform", "admin_organizacion")
    upsert_role(session, "maintainer", "acme/payments-api", "mantenedor")
    upsert_role(session, "maintainer", "acme/auth-service", "mantenedor")
    upsert_role(session, "reviewer", "acme/payments-api", "revisor")
    upsert_role(session, "reviewer", "acme/auth-service", "revisor")

    existing_count = session.execute(
        select(func.count()).select_from(DashboardPRScore)
    ).scalar_one()
    if existing_count > 0:
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
            session,
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
        session,
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
        session,
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


def compute_agent_metrics(engine_session: Session) -> AgentUsageMetrics:
    """Recibe una `Session` de la ENGINE DB (`watchgate.db.connection.get_session`/
    `get_db_session`), no del Dashboard -- antes esta función consultaba
    `agent_id`/`user_token_usage` contra la base de datos del Dashboard,
    donde NINGUNA de las dos existe: `agent_id` no es columna de
    `pr_scores` aquí, y `user_token_usage` es una tabla de la Engine DB
    (`watchgate.db.models.UserTokenUsage`). El `try/except Exception` que
    envolvía cada SELECT lo tragaba en silencio, así que esta función nunca
    devolvió datos reales (hallazgo real de esta migración). Ahora consulta
    directamente donde esos datos sí existen.

    Agregación en SQL en vez de en Python -- mismo motivo/patrón que
    `compute_org_metrics()` (perf(dashboard): agregación en SQL en vez de
    en Python): antes traía CADA fila de `pr_scores`/`user_token_usage` sin
    filtro alguno de fecha/organización y sumaba a mano, así que el
    histórico completo de la plataforma (todo agente, todo usuario, todo
    mes) se cargaba entero a memoria del proceso del dashboard-backend en
    cada carga del panel de agentes. `func.avg()`/`func.sum()` con
    `GROUP BY agent_id`/`user_id` hacen ese trabajo en el motor; el
    redondeo a 1 decimal se sigue haciendo en Python, no en SQL, por la
    misma razón que en `compute_org_metrics()`: no depender de que
    SQLite/Postgres redondeen igual entre sí ni igual que `round()`."""
    from watchgate.db.models import PRScore as EnginePRScore
    from watchgate.db.models import UserTokenUsage

    # `select(Model.columna, ...)` con columnas sueltas (en vez de
    # `select(Model)` completo) no está bien tipado por mypy contra clases
    # SQLModel -- a nivel de clase, `EnginePRScore.agent_id` resuelve al tipo
    # Pydantic del campo (`str | None`), no a un `InstrumentedAttribute` de
    # SQLAlchemy, así que ni `select(...)` ni `.is_not()`/`!=` casan con las
    # firmas esperadas. Mismo motivo por el que `record_token_usage`
    # (repository.py) ya necesita `# type: ignore[attr-defined]` en
    # `Model.__table__` -- limitación conocida de tipado SQLModel, no un
    # error real (cubierto por tests reales contra SQLite/Postgres).
    agent_stmt = select(  # type: ignore[call-overload]
        EnginePRScore.agent_id,
        func.count().label("analyses_count"),
        func.avg(EnginePRScore.score).label("avg_score"),
    ).where(
        EnginePRScore.agent_id.is_not(None),  # type: ignore[union-attr]
        EnginePRScore.agent_id != "",
    )
    agent_stmt = agent_stmt.group_by(EnginePRScore.agent_id)

    # `avg_score` puede ser NULL en teoría (columna `score` nula), aunque en
    # la práctica `PRScore.score` es NOT NULL -- se guarda como `None` en el
    # diccionario y se resuelve a 0.0 más abajo, mismo patrón que el resto
    # de la función para no asumir invariantes de esquema que no son de
    # este código. IMPORTANTE: contra Postgres, `AVG()` sobre una columna
    # entera devuelve `Decimal`, no `float` como en SQLite -- de ahí el
    # `float()` explícito antes de `round()` (mismo bug que ya atrapó
    # `compute_org_metrics()` contra Postgres real).
    agent_agg: dict[str, tuple[int, float | None]] = {
        str(row.agent_id): (
            int(row.analyses_count),
            float(row.avg_score) if row.avg_score is not None else None,
        )
        for row in engine_session.execute(agent_stmt)
    }

    # `SUM()` agrupado por `user_id` nunca es NULL para un grupo que existe
    # de verdad (el GROUP BY solo produce filas con >=1 fila real detrás) --
    # a diferencia del `SUM()` sin agrupar de `compute_org_metrics()`, aquí
    # no hay caso "cero filas" posible por grupo. El `coalesce()` es
    # defensivo (una fila con `tokens_used` NULL a mano, fuera del camino
    # normal de escritura) más que estrictamente necesario.
    token_stmt = select(  # type: ignore[call-overload]
        UserTokenUsage.user_id,
        func.coalesce(func.sum(UserTokenUsage.tokens_used), 0).label("tokens_used"),
    ).group_by(UserTokenUsage.user_id)
    token_usage: dict[str, int] = {
        str(row.user_id): int(row.tokens_used) for row in engine_session.execute(token_stmt)
    }

    total_tokens = sum(token_usage.values())

    all_agent_ids = set(agent_agg.keys()).union(token_usage.keys())
    if not all_agent_ids:
        all_agent_ids = {"default-agent"}

    agent_rows: list[AgentMetricRow] = []
    for aid in sorted(all_agent_ids):
        cnt, avg_raw = agent_agg.get(aid, (0, None))
        avg_s = round(avg_raw, 1) if avg_raw is not None else 0.0
        agent_rows.append(
            AgentMetricRow(
                agent_id=aid,
                tokens_used=token_usage.get(aid, 0),
                analyses_count=cnt,
                avg_score=avg_s,
            )
        )

    return AgentUsageMetrics(
        total_tokens_used=total_tokens,
        agents_count=len(agent_rows),
        by_agent=agent_rows,
    )
