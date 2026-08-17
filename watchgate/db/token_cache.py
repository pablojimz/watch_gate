"""Caché semántica y consumo de tokens -- funciones CRUD de bajo nivel sobre
`Session`, sin más dependencias que `watchgate.db.models`.

Extraído de `watchgate.db.repository` a propósito: ese módulo tiene un
import diferido (dentro de `check_user_repo_permission`) hacia
`watchgate.dashboard.backend.db`, y `watchgate/core/cost_control.py`
(modo CLI/engine local) necesita `get_semantic_cache`/`set_semantic_cache`/
`record_repo_token_usage`/`get_repo_token_usage` sin arrastrar esa
dependencia -- el contrato de arquitectura (`[tool.importlinter]`, ver
`tests/unit/test_architecture.py`) prohíbe que `watchgate.core` alcance
`watchgate.dashboard` ni siquiera transitivamente, y `grimp` (el analizador
que usa import-linter) cuenta cualquier `import`, esté o no dentro de una
función. Este módulo es una hoja sin dependencias hacia `watchgate.dashboard`,
así que `cost_control.py` puede importar de aquí directamente sin romper
ese contrato. `watchgate.db.repository` re-exporta estas mismas funciones
para no romper a sus propios callers (`service/quota.py`, tests).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from watchgate.db.models import RepoTokenUsage, SemanticCache


def get_semantic_cache(
    session: Session, diff_hash_value: str, org_id: str = "default-org"
) -> str | None:
    """Recupera la respuesta JSON en caché de la capa semántica aislada por organización."""
    stmt = select(SemanticCache).where(
        SemanticCache.diff_hash == diff_hash_value, SemanticCache.org_id == org_id
    )
    cached = session.exec(stmt).first()
    return cached.output_json if cached else None


def set_semantic_cache(
    session: Session, diff_hash_value: str, output_json: str, org_id: str = "default-org"
) -> SemanticCache:
    """Guarda una respuesta JSON en la caché semántica aislada por organización."""
    stmt = select(SemanticCache).where(
        SemanticCache.diff_hash == diff_hash_value, SemanticCache.org_id == org_id
    )
    existing = session.exec(stmt).first()

    if existing:
        existing.output_json = output_json
        existing.created_at = datetime.now(UTC)
        cache_record = existing
    else:
        cache_record = SemanticCache(
            org_id=org_id, diff_hash=diff_hash_value, output_json=output_json
        )

    session.add(cache_record)
    session.commit()
    session.refresh(cache_record)
    return cache_record


def record_repo_token_usage(
    session: Session,
    repo: str,
    tokens_used: int,
    month: str | None = None,
) -> RepoTokenUsage:
    """Registra o incrementa, de forma ATÓMICA, el consumo de tokens
    mensual de un REPOSITORIO -- contraparte de
    `watchgate.db.repository.record_token_usage` para `CostController`
    (`watchgate/core/cost_control.py`, modo CLI/engine local sin
    organización/tenant: la cuota se lleva por repo, no por usuario). Mismo
    patrón `INSERT ... ON CONFLICT DO UPDATE` atómico, por el mismo motivo
    (evitar el *lost update* de un SELECT->incrementar en Python->UPDATE/
    INSERT bajo llamadas concurrentes del mismo repo/mes)."""
    month_key = month or datetime.now(UTC).strftime("%Y-%m")
    dialect = session.get_bind().dialect.name

    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert
    else:
        from sqlalchemy.dialects.sqlite import insert as _insert  # type: ignore[assignment]

    table = RepoTokenUsage.__table__  # type: ignore[attr-defined]
    stmt = _insert(table).values(repo=repo, month=month_key, tokens_used=tokens_used)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.repo, table.c.month],
        set_={"tokens_used": table.c.tokens_used + stmt.excluded.tokens_used},
    )
    session.exec(stmt)
    session.commit()

    usage = session.exec(
        select(RepoTokenUsage).where(RepoTokenUsage.repo == repo, RepoTokenUsage.month == month_key)
    ).first()
    assert usage is not None  # noqa: S101 -- se acaba de upsertar en esta misma transacción
    return usage


def get_repo_token_usage(session: Session, repo: str, month: str | None = None) -> int:
    """Tokens consumidos por `repo` en el mes especificado (0 si no hay fila)."""
    month_key = month or datetime.now(UTC).strftime("%Y-%m")
    usage = session.exec(
        select(RepoTokenUsage).where(RepoTokenUsage.repo == repo, RepoTokenUsage.month == month_key)
    ).first()
    return usage.tokens_used if usage else 0
