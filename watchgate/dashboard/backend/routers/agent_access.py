"""agent_access.py — acceso de solo lectura al Dashboard para agentes de IA remotos.

Contraparte HTTP de las tools MCP `watchgate_repo_score_history`/
`watchgate_org_metrics` (`watchgate/mcp/tools.py`) -- mismo par de
capacidades, mismo motivo de existir (un agente de IA que quiere ver qué
dice el Dashboard sobre un repo, no solo analizar diffs nuevos), pero por
HTTP con una API Key en vez de un proceso MCP local por stdio: para un
agente que corre en otra máquina (CI, un bot, un servicio propio), no en el
IDE del propio desarrollador.

Autenticado por API Key (`watchgate.api.auth.get_current_user_from_api_key`,
el mismo mecanismo que ya usa la Engine API -- Bearer o X-API-Key, ninguna
ruta de autenticación nueva), NUNCA por la cookie de sesión del Dashboard:
son rutas para llamar por programa, no para el navegador.

El login de GitHub del Dashboard y la API Key de la Engine API siguen
siendo dos sistemas de identidad distintos (uno por `org_id`, el otro por
login), pero ya no es un bypass: cada endpoint resuelve `user.name` como
login y comprueba el rol real asignado en `repo_roles` (vía
`database.get_role`/`user_is_org_admin`, la misma fuente que usa
`require_role` en `auth.py` para las rutas autenticadas por cookie) antes
de devolver nada de un repo -- una API Key sin rol en un repo recibe 403,
igual que un usuario sin rol en el Dashboard normal.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from watchgate.api.auth import get_current_user_from_api_key
from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.schemas import OrgMetrics, ScoreOut
from watchgate.db.models import Organization, User, UserAPIKey

ApiKeyIdentity = Annotated[
    tuple[UserAPIKey, User, Organization], Depends(get_current_user_from_api_key)
]

router = APIRouter(prefix="/agent-access", tags=["agent-access"])


@router.get("/repos/{repo:path}/scores", response_model=list[ScoreOut])
def repo_score_history(
    repo: str,
    _identity: ApiKeyIdentity,
    limit: int = 20,
) -> list[ScoreOut]:
    _key, user, _org = _identity
    user_login = user.name

    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user_login)
        if not is_admin:
            role = database.get_role(conn, user_login, repo)
            if role is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permiso denegado: Sin rol asignado en '{repo}'",
                )
        scores = database.list_scores(conn, repo)
    return scores[:limit]


@router.get("/metrics", response_model=OrgMetrics)
def org_metrics(
    _identity: ApiKeyIdentity,
    repos: Annotated[list[str] | None, Query()] = None,
) -> OrgMetrics:
    _key, user, _org = _identity
    user_login = user.name

    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user_login)
        if repos:
            authorized_repos = [
                r for r in repos if is_admin or database.get_role(conn, user_login, r) is not None
            ]
            selected = authorized_repos
        else:
            selected = database.list_repos_for_user(conn, user_login, is_admin=is_admin)
        return database.compute_org_metrics(conn, selected)
