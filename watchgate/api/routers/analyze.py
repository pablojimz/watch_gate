"""Router REST para el endpoint de análisis de Pull Requests (POST /api/v1/analyze)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from watchgate.api.auth import require_scope
from watchgate.api.dependencies import get_db_session
from watchgate.config import load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import AggregatedResult, CommitAuthor
from watchgate.db.models import Organization, User, UserAPIKey
from watchgate.service.policy import ClientConfigOverrideError, apply_client_config_override
from watchgate.service.quota import QuotaService

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

    return result
