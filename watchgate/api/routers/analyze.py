"""Router REST para el endpoint de análisis de Pull Requests (POST /api/v1/analyze)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from watchgate.api.auth import get_current_user_from_api_key
from watchgate.config import WatchGateConfig, load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import AggregatedResult, CommitAuthor
from watchgate.core.pipeline import run_full_analysis
from watchgate.db.connection import default_engine
from watchgate.db.models import Organization, User, UserAPIKey
from watchgate.db.repository import record_token_usage, save_pr_score

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
    authors: list[CommitAuthor] = Field(
        default_factory=list, description="Autores de los commits"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadatos contextuales de la PR"
    )
    config_override: dict[str, Any] | None = Field(
        default=None, description="Ajustes opcionales de configuración para anular defaults"
    )


def _persist_score_and_usage(
    result: AggregatedResult, user_id: str, org_id: str | None = None
) -> None:
    """Tarea en segundo plano para guardar el resultado en pr_scores e imputar tokens."""
    with Session(default_engine) as session:
        save_pr_score(session, aggregated_result=result, user_id=user_id, org_id=org_id)

        # Si la capa semántica fue ejecutada y no omitida, estimamos e imputamos el consumo
        sem_res = result.layer_results.get("semantic")
        if sem_res and not sem_res.skipped:
            # Estimación básica de tokens de inferencia (o uso mínimo base de ~1500 tokens)
            estimated_tokens = 1500 + (sem_res.tool_calls_made * 500)
            record_token_usage(
                session, user_id=user_id, tokens_used=estimated_tokens, org_id=org_id
            )


@router.post("/analyze", response_model=AggregatedResult)
def analyze_pr(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    auth: tuple[UserAPIKey, User, Organization] = Depends(get_current_user_from_api_key),
) -> AggregatedResult:
    """Ejecuta el análisis completo de la PR enviada en texto plano.

    Persiste los resultados de forma asíncrona mediante BackgroundTasks.
    """
    _, user, org = auth

    diff = parse_diff_from_text(
        diff_text=request.diff_text,
        base_sha=request.base_sha,
        head_sha=request.head_sha,
        repo_path=request.repo_path,
        commit_messages=request.commit_messages,
        authors=request.authors,
    )

    # Carga de configuración base + overrides opcionales
    base_config = load_config()
    if request.config_override:
        cfg_dict = base_config.model_dump()
        cfg_dict.update(request.config_override)
        config = WatchGateConfig(**cfg_dict)
    else:
        config = base_config

    result = run_full_analysis(diff=diff, metadata=request.metadata, config=config)

    # Persistencia asíncrona en segundo plano para no demorar el tiempo de respuesta HTTP
    background_tasks.add_task(
        _persist_score_and_usage, result=result, user_id=user.id, org_id=org.id
    )

    return result
