"""metrics.py — métricas agregadas de postura de seguridad."""

from __future__ import annotations

from fastapi import APIRouter

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser
from watchgate.dashboard.backend.schemas import OrgMetrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=OrgMetrics)
def get_org_metrics(user: CurrentUser) -> OrgMetrics:
    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user.login)
        repos = database.list_repos_for_user(conn, user.login, is_admin=is_admin)
        return database.compute_org_metrics(conn, repos)
