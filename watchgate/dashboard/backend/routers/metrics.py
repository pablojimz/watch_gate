"""metrics.py — métricas agregadas de postura de seguridad y consumo de agentes."""

from __future__ import annotations

from fastapi import APIRouter

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import AgentUsageMetrics, OrgMetrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=OrgMetrics)
def get_org_metrics(user: CurrentUser) -> OrgMetrics:
    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user.login)
        repos = database.list_repos_for_user(conn, user.login, is_admin=is_admin)
        return database.compute_org_metrics(conn, repos)


@router.get("/metrics/agent-usage", response_model=AgentUsageMetrics)
def get_agent_usage_metrics(_user: CurrentUser) -> AgentUsageMetrics:
    with database.db_session() as conn:
        return database.compute_agent_metrics(conn)
