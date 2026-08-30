"""metrics.py — métricas agregadas de postura de seguridad y consumo de agentes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import AgentUsageMetrics, OrgMetrics
from watchgate.db.connection import get_db_session

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=OrgMetrics)
def get_org_metrics(user: CurrentUser) -> OrgMetrics:
    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user.login)
        repos = database.list_repos_for_user(conn, user.login, is_admin=is_admin)
        return database.compute_org_metrics(conn, repos)


@router.get("/metrics/agent-usage", response_model=AgentUsageMetrics)
def get_agent_usage_metrics(
    user: CurrentUser,
    engine_session: Session = Depends(get_db_session),  # noqa: B008
) -> AgentUsageMetrics:
    # `compute_agent_metrics` lee de la Engine DB (agent_id/tokens_used
    # viven ahí, no en la base de datos del Dashboard) -- ver el docstring
    # de la función para el bug real que esto corrige.
    #
    # AUDITORÍA (hallazgo crítico, corregido): este endpoint no comprobaba
    # ningún rol -- cualquier usuario autenticado, sin rol en ningún repo,
    # veía el consumo de tokens/coste de TODA la plataforma y emails reales
    # de otras cuentas (confirmado en vivo). `compute_agent_metrics` no
    # filtra por organización (agrega toda la Engine DB, ver su propio
    # docstring), así que el único gate correcto disponible hoy es exigir
    # admin -- mismo patrón que llm_settings.py/ui_settings.py para esta
    # misma clase de dato "de instancia", no por-repo.
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere admin")
    return database.compute_agent_metrics(engine_session)
