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

from sqlalchemy import Engine, func, select
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
    OrgMetrics,
    RepoMetricRow,
    RepoSettings,
    RoleName,
    ScoreOut,
    TrendPoint,
    UiSettings,
    normalize_login,
)
from watchgate.db.connection import build_engine
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

# Columnas que compute_org_metrics() lee de verdad -- a diferencia de
# _record_to_score_out() (que sí necesita la fila completa, incluidos
# findings_json/semantic_justification, para reconstruir un AggregatedResult
# real), esta función solo agrega números/etiquetas. Seleccionar la entidad
# completa traería esos blobs (hallazgos con fichero/línea/mensaje de cada
# capa, texto del LLM) para cada fila de TODO el histórico visible de la
# organización -- payload real que ni se deserializaba aquí, solo se
# descartaba.
_METRICS_COLUMNS = (
    DashboardPRScore.repo,
    DashboardPRScore.timestamp,
    DashboardPRScore.score,
    DashboardPRScore.semaforo,
    DashboardPRScore.human_feedback,
    *(
        getattr(DashboardPRScore, col)
        for _, score_col, skip_col in _LAYER_COLS
        for col in (score_col, skip_col)
    ),
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
        justification = ""
        if name == "semantic":
            justification = record.semantic_justification or ""

        extra = findings_by_layer.get(name, {})
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
    return LlmSettingsOut(
        provider=record.provider,  # type: ignore[arg-type]
        model=record.model,
        base_url=record.base_url,
        api_key_set=bool(api_key),
        api_key_masked=_mask_api_key(api_key),
        monthly_budget_tokens=record.monthly_budget_tokens,
        max_diff_tokens=record.max_diff_tokens,
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
    record.provider = body.provider
    record.model = body.model
    record.base_url = body.base_url
    record.api_key = new_key
    record.monthly_budget_tokens = body.monthly_budget_tokens
    record.max_diff_tokens = body.max_diff_tokens
    session.commit()
    return get_llm_settings(session)


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

    stmt = (
        select(*_METRICS_COLUMNS)
        .where(DashboardPRScore.repo.in_(repos))
        .order_by(DashboardPRScore.timestamp.asc())
    )
    rows = session.execute(stmt).all()

    total = len(rows)
    avg_score = round(sum(int(r.score) for r in rows) / total, 1) if total else 0.0
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
        sem = r.semaforo
        if sem in by_semaforo:
            by_semaforo[sem] += 1
        fb = r.human_feedback
        if fb == "correcto":
            feedback_correct += 1
        elif fb == "falso_positivo":
            feedback_fp += 1
        else:
            feedback_pending += 1

        # Misma tripleta (nombre, columna score, columna skipped) que
        # _LAYER_COLS -- reutilizada en vez de duplicada, para no tener que
        # acordarse de actualizar dos sitios el día que cambien las capas.
        for layer, score_col, skip_col in _LAYER_COLS:
            skip_val = getattr(r, skip_col)
            score_val = getattr(r, score_col)
            if not skip_val and score_val is not None:
                layer_sums[layer].append(int(score_val))

        repo = r.repo
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
        bucket["score_sum"] = float(bucket["score_sum"]) + int(r.score)
        if sem in ("verde", "amarillo", "rojo"):
            bucket[sem] = int(bucket[sem]) + 1
        if fb is None:
            bucket["feedback_pending"] = int(bucket["feedback_pending"]) + 1

        day = str(r.timestamp)[:10]
        by_day.setdefault(day, []).append(int(r.score))

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
    """Usuarios locales + histórico falso para probar el dashboard sin CI."""
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
    directamente donde esos datos sí existen."""
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
    rows = engine_session.execute(
        select(  # type: ignore[call-overload]
            EnginePRScore.agent_id, EnginePRScore.score
        ).where(
            EnginePRScore.agent_id.is_not(None),  # type: ignore[union-attr]
            EnginePRScore.agent_id != "",
        )
    ).all()

    agent_data: dict[str, dict[str, Any]] = {}
    for agent_id_raw, score_raw in rows:
        agent_id = str(agent_id_raw)
        bucket = agent_data.setdefault(agent_id, {"count": 0, "score_sum": 0.0})
        bucket["count"] += 1
        bucket["score_sum"] += float(score_raw)

    token_usage: dict[str, int] = {}
    tu_rows = engine_session.execute(
        select(  # type: ignore[call-overload]
            UserTokenUsage.user_id, UserTokenUsage.tokens_used
        )
    ).all()
    for user_id_raw, tokens_raw in tu_rows:
        u_id = str(user_id_raw)
        token_usage[u_id] = token_usage.get(u_id, 0) + int(tokens_raw)

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
