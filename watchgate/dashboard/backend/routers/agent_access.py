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

LIMITACIÓN CONOCIDA, la misma que en las tools MCP -- documentada aquí y en
el propio `docs/manual_mcp.md`, no oculta: el Dashboard controla el acceso
por login de GitHub y un rol por repositorio (`repo_roles`, resuelto por
`require_role` en `auth.py`), mientras que una API Key de la Engine API se
resuelve por organización, no por login de GitHub -- son dos sistemas de
identidad que nunca se unificaron. Estos endpoints, a diferencia de sus
equivalentes autenticados por cookie en `scores.py`/`metrics.py`, NO
aplican `require_role`: cualquier API Key válida (de cualquier
organización) ve el historial/métricas de CUALQUIER repositorio del
Dashboard. Aceptable para el caso de uso de hoy (una única organización
usando su propio Dashboard), pero antes de exponer esto en un despliegue
multi-organización de verdad hace falta resolver un login real a partir de
la API Key (o, más simple, exigir un scope dedicado y aceptar que sigue
siendo "toda la organización", nunca por repo).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

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
    with database.db_session() as conn:
        scores = database.list_scores(conn, repo)
    return scores[:limit]


@router.get("/metrics", response_model=OrgMetrics)
def org_metrics(
    _identity: ApiKeyIdentity,
    repos: Annotated[list[str] | None, Query()] = None,
) -> OrgMetrics:
    with database.db_session() as conn:
        if repos:
            selected = repos
        else:
            # `is_admin=True` ignora el login y devuelve TODOS los repos del
            # Dashboard -- ver la limitación documentada en el docstring del
            # módulo (sin un login de GitHub real resuelto de la API Key, no
            # hay forma de acotar "solo los repos de esta organización").
            selected = database.list_repos_for_user(conn, "_agent_access", is_admin=True)
        return database.compute_org_metrics(conn, selected)
