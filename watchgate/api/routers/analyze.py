"""Router REST para el endpoint de análisis de Pull Requests (POST /api/v1/analyze)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from watchgate.api.auth import require_scope
from watchgate.api.dependencies import get_db_session
from watchgate.config import load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import AggregatedResult, CommitAuthor
from watchgate.db.models import MonitoredRepo, Organization, User, UserAPIKey
from watchgate.service.policy import ClientConfigOverrideError, apply_client_config_override
from watchgate.service.quota import QuotaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Analysis"])


class AnalyzeRequest(BaseModel):
    """Payload de solicitud para analizar un diff de PR vía HTTP."""

    diff_text: str = Field(description="Parche de texto unificado git diff")
    base_sha: str = Field(default="0000000", description="SHA de commit base")
    head_sha: str = Field(default="0000000", description="SHA de commit head")
    repo_path: str = Field(default=".", description="Ruta o identificador del repo")
    commit_messages: list[str] = Field(
        default_factory=list, description="Lista de mensajes de commit"
    )
    authors: list[CommitAuthor] = Field(default_factory=list, description="Autores de los commits")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadatos contextuales de la PR"
    )
    config_override: dict[str, Any] | None = Field(
        default=None, description="Ajustes opcionales de configuración para anular defaults"
    )


@router.post("/analyze", response_model=AggregatedResult)
def analyze_pr(
    request: AnalyzeRequest,
    auth: tuple[UserAPIKey, User, Organization] = Depends(require_scope("analysis:write")),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AggregatedResult:
    """Ejecuta el análisis completo de la PR enviada en texto plano respetando cuotas."""
    api_key, user, org = auth

    diff = parse_diff_from_text(
        diff_text=request.diff_text,
        base_sha=request.base_sha,
        head_sha=request.head_sha,
        repo_path=request.repo_path,
        commit_messages=request.commit_messages,
        authors=request.authors,
    )

    # Puerta 3: una API key solo puede analizar el repo al que pertenece.
    # `metadata["repo"]` tiene prioridad sobre `repo_path` para ser
    # consistente con cómo `run_full_analysis` rellena `result.repo` (ver
    # watchgate/core/pipeline.py, aggregate(repo=metadata.get("repo", ""))).
    requested_repo = str(request.metadata.get("repo") or request.repo_path or "")

    if api_key.monitored_repo_id is None:
        # Clave legado (creada antes de este campo): sin relación directa a
        # un repo, se aplica como red de seguridad mínima la misma
        # comprobación de antes -- el repo pedido debe estar entre los
        # monitorizados de la organización de la clave.
        legacy_stmt = select(MonitoredRepo).where(
            MonitoredRepo.org_id == org.id, MonitoredRepo.repo_path == requested_repo
        )
        if session.exec(legacy_stmt).first() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"El repo '{requested_repo}' no está monitorizado por tu organización."
                ),
            )
    else:
        key_repo = session.get(MonitoredRepo, api_key.monitored_repo_id)
        if key_repo is None or key_repo.repo_path != requested_repo:
            bound_repo_path = key_repo.repo_path if key_repo else "?"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta API key solo es válida para el repo '{bound_repo_path}'.",
            )

    # Carga de configuración base + overrides opcionales de la petición.
    # `apply_client_config_override` rechaza (400) cualquier intento de
    # tocar thresholds/weights/block_on_red/shortcircuit_enabled -- esos
    # solo los puede fijar la gobernanza de organización, nunca la propia
    # petición HTTP (ver watchgate/service/policy.py).
    base_config = load_config()
    try:
        config = apply_client_config_override(base_config, request.config_override)
    except ClientConfigOverrideError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    quota_service = QuotaService(session)
    result, _is_degraded = quota_service.analyze_with_quota(
        diff=diff,
        metadata=request.metadata,
        config=config,
        org_id=org.id,
        user_id=user.id,
        agent_id=api_key.default_agent_name,
    )

    # Espejo best-effort en la base de datos del dashboard: sin esto, el
    # análisis existe (base de datos A, vía save_pr_score dentro de
    # analyze_with_quota) pero no aparece en /repos del frontend. Un fallo
    # aquí es degradado, no crítico -- el análisis ya se hizo y ya se
    # persistió en la base de datos A, así que la petición sigue devolviendo
    # 200 pase lo que pase (mismo criterio que documentaba
    # watchgate/adapters/github_action/dashboard_client.py para este tipo de
    # fallo antes de que ese adaptador se eliminara).
    from watchgate.dashboard.backend.db import db_session as dashboard_db_session
    from watchgate.dashboard.backend.db import insert_aggregated, upsert_role

    author_login = request.metadata.get("author_login") or (
        request.authors[0].login if request.authors else None
    )
    try:
        with dashboard_db_session() as dash_conn:
            insert_aggregated(dash_conn, result, author_login=author_login)
            upsert_role(dash_conn, user.name, result.repo, "admin_organizacion")
    except Exception:
        logger.warning(
            "No se pudo persistir el resultado en el dashboard para repo=%s pr_id=%s",
            result.repo,
            result.pr_id,
            exc_info=True,
        )

    return result
