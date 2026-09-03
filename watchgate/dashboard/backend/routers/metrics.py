"""metrics.py — métricas agregadas de postura de seguridad y consumo de agentes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.org_scope import (
    is_site_superadmin,
    resolve_caller_org_id,
    resolve_org_repo_paths,
)
from watchgate.dashboard.backend.schemas import AgentUsageMetrics, OrgMetrics
from watchgate.db.connection import get_db_session

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=OrgMetrics)
def get_org_metrics(
    user: CurrentUser,
    engine_session: Session = Depends(get_db_session),  # noqa: B008
) -> OrgMetrics:
    # Auditoría: acotado a la organización real del llamador -- antes
    # `is_admin=True` (global) hacía que `list_repos_for_user` devolviera
    # los repos de TODAS las organizaciones, no solo la propia.
    #
    # AUDITORÍA (bugfix): `user_is_org_admin` está hardcodeado a `False`
    # siempre -- se quitó el rol "admin_organizacion" del RBAC (ver su
    # docstring), así que este endpoint nunca dejaba ver métricas a nadie
    # sin un `RepoRole` explícito, ni siquiera al superadmin de sitio
    # (reproducido en vivo: el login "admin", superadmin de sitio por
    # defecto, veía 0 en todo). `routers/scores.py::list_visible_repos` ya
    # resuelve esto bien -- mismo patrón aquí: `is_site_superadmin` decide
    # `is_admin`/`unscoped`, no la función muerta.
    caller_is_site_superadmin = is_site_superadmin(user.login)
    org_id = resolve_caller_org_id(engine_session, user.login)
    org_repo_paths = resolve_org_repo_paths(engine_session, org_id)
    with database.db_session() as conn:
        repos = database.list_repos_for_user(
            conn,
            user.login,
            is_admin=caller_is_site_superadmin,
            org_id=org_id,
            org_repo_paths=org_repo_paths,
            unscoped=caller_is_site_superadmin,
        )
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
    # docstring) -- es dato de INSTANCIA completa, no por-organización, así
    # que exige superadmin de sitio (mismo nivel que llm_settings.py/
    # ui_settings.py), no un mero admin_organizacion (que tras acotarlo por
    # organización ya no tendría sentido aquí).
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )
    return database.compute_agent_metrics(engine_session)
