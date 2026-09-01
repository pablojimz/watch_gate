"""yara_rules.py — cola de revisión de reglas YARA propuestas por la capa
semántica (bucle de retroalimentación, ver
`core/layers/_semantic/tools.py::propose_yara_rule`).

Lee/escribe `PendingYaraRule` directamente en la Engine DB, sin tabla
espejo en la BD del Dashboard -- mismo patrón que
`scores.py::list_blocked_authors`/`block_author` contra `BlockedAuthor`
(ver el docstring de `PendingYaraRule` para por qué vive ahí y no en la
BD del Dashboard: hay un lector real durante el propio análisis,
`static_layer.py`).

Se quitó el rol "admin_organizacion" del RBAC -- ya no hay ninguna
distinción entre "ver la cola" y "aprobar/rechazar": las dos exigen
`is_site_superadmin`, porque la activación es de INSTANCIA completa,
nunca por organización (`_run_yara_on_text` compila un único ruleset por
proceso, sin concepto de org) -- mismo criterio que `llm_settings.py`/
`ui_settings.py`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import yara
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.org_scope import is_site_superadmin
from watchgate.db.connection import get_db_session
from watchgate.db.models import PendingYaraRule

router = APIRouter(tags=["yara-rules"])

EngineDBSession = Annotated[Session, Depends(get_db_session)]

# Fragmentos claramente benignos para la comprobación de falsos positivos
# al aprobar -- ver _run_benign_fixture_check.
_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "yara_review_fixtures"


class PendingYaraRuleOut(BaseModel):
    id: str
    org_id: str | None
    repo: str
    pr_id: str
    rule_name: str
    category: str
    yara_source: str
    rationale: str
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ApprovedYaraRuleOut(PendingYaraRuleOut):
    # Nombres de fixture que la regla, ya aprobada, coincidió contra
    # código benigno -- aviso, no bloqueo: la decisión sigue siendo
    # humana (ver _run_benign_fixture_check).
    benign_matches: list[str]


def _to_out(row: PendingYaraRule) -> PendingYaraRuleOut:
    return PendingYaraRuleOut(
        id=row.id,
        org_id=row.org_id,
        repo=row.repo,
        pr_id=row.pr_id,
        rule_name=row.rule_name,
        category=row.category,
        yara_source=row.yara_source,
        rationale=row.rationale,
        status=row.status,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
    )


@router.get("/admin/yara-rules", response_model=list[PendingYaraRuleOut])
def list_pending_yara_rules(
    user: CurrentUser,
    engine_session: EngineDBSession,
    status_filter: str | None = Query(default="pending", alias="status"),
) -> list[PendingYaraRuleOut]:
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )

    stmt = select(PendingYaraRule)
    if status_filter:
        stmt = stmt.where(PendingYaraRule.status == status_filter)
    stmt = stmt.order_by(PendingYaraRule.created_at.desc())  # type: ignore[attr-defined]

    rows = engine_session.exec(stmt).all()
    return [_to_out(r) for r in rows]


def _run_benign_fixture_check(yara_source: str) -> list[str]:
    """Compila la regla propuesta y la ejecuta contra un pequeño corpus de
    fragmentos claramente benignos (`yara_review_fixtures/`) -- NO bloquea
    la aprobación si hay coincidencias (la decisión sigue siendo humana),
    pero avisa: una regla que dispara contra código normal es
    probablemente demasiado amplia. Nunca lanza -- un fallo aquí degrada a
    "sin avisos", no debe impedir aprobar una regla por lo demás válida."""
    try:
        compiled = yara.compile(source=yara_source)
    except yara.Error:
        return []
    if not _FIXTURES_DIR.is_dir():
        return []
    matches: list[str] = []
    for fixture_path in sorted(_FIXTURES_DIR.iterdir()):
        if not fixture_path.is_file():
            continue
        try:
            data = fixture_path.read_bytes()
        except OSError:
            continue
        try:
            if compiled.match(data=data, timeout=5):
                matches.append(fixture_path.name)
        except yara.Error:
            continue
    return matches


def _get_pending_rule_or_404(engine_session: Session, rule_id: str) -> PendingYaraRule:
    row = engine_session.get(PendingYaraRule, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla no encontrada")
    if row.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La regla ya está en estado '{row.status}', no 'pending'.",
        )
    return row


@router.post("/admin/yara-rules/{rule_id}/approve", response_model=ApprovedYaraRuleOut)
def approve_yara_rule(
    rule_id: str, user: CurrentUser, engine_session: EngineDBSession
) -> ApprovedYaraRuleOut:
    """Activa la regla para TODA la instancia (ver el docstring del
    módulo) -- por eso exige superadmin de sitio. No escribe ningún
    fichero: `static_layer.py`
    recompila directamente desde esta fila (`status="approved"`) con un
    TTL corto, ver `_get_compiled_generated_yara_rules`."""
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )

    row = _get_pending_rule_or_404(engine_session, rule_id)

    # Re-validar aquí, no solo confiar en la validación de tools.py -- por
    # si el contenido en BD se corrompió entre la propuesta y la revisión.
    try:
        yara.compile(source=row.yara_source)
    except yara.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"La regla ya no compila: {exc}"
        ) from exc

    benign_matches = _run_benign_fixture_check(row.yara_source)

    row.status = "approved"
    row.reviewed_by = user.login
    row.reviewed_at = datetime.now(UTC)
    engine_session.add(row)
    engine_session.commit()
    engine_session.refresh(row)

    return ApprovedYaraRuleOut(**_to_out(row).model_dump(), benign_matches=benign_matches)


@router.post("/admin/yara-rules/{rule_id}/reject", response_model=PendingYaraRuleOut)
def reject_yara_rule(
    rule_id: str, user: CurrentUser, engine_session: EngineDBSession
) -> PendingYaraRuleOut:
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )

    row = _get_pending_rule_or_404(engine_session, rule_id)
    row.status = "rejected"
    row.reviewed_by = user.login
    row.reviewed_at = datetime.now(UTC)
    engine_session.add(row)
    engine_session.commit()
    engine_session.refresh(row)
    return _to_out(row)
