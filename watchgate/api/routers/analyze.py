"""Router REST para el endpoint de análisis de Pull Requests (POST /api/v1/analyze)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from watchgate.adapters.github_client import GitHubClient
from watchgate.api.auth import require_scope
from watchgate.api.dependencies import get_db_session
from watchgate.config import load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import AggregatedResult, CommitAuthor, ProposedYaraRule
from watchgate.db.models import (
    MonitoredRepo,
    Organization,
    PendingYaraRule,
    User,
    UserAPIKey,
    VCSConnection,
)
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


def requested_repo_for(request: AnalyzeRequest) -> str:
    """Repo efectivo de la petición. `metadata["repo"]` tiene prioridad
    sobre `repo_path` para ser consistente con cómo `run_full_analysis`
    rellena `result.repo` (ver watchgate/core/pipeline.py,
    aggregate(repo=metadata.get("repo", "")))."""
    return str(request.metadata.get("repo") or request.repo_path or "")


def ensure_api_key_repo_binding(
    session: Session, api_key: UserAPIKey, org: Organization, requested_repo: str
) -> None:
    """Puerta 3: una API key solo puede analizar el repo al que pertenece.

    Extraída de `analyze_pr` para que los endpoints de agente
    (`/agent/precheck`, `/agent/analyze`, `/agent/verify-fix`) apliquen
    EXACTAMENTE la misma puerta -- antes solo `/analyze` la comprobaba, y
    una clave atada a un repo podía analizar cualquier otro pasando por los
    endpoints de agente (mismo scope `analysis:write`, misma cuota), un
    bypass directo de la decisión de keys.py de que "toda clave nueva debe
    crearse atada a un repo concreto".
    """
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
                detail=(f"El repo '{requested_repo}' no está monitorizado por tu organización."),
            )
    else:
        key_repo = session.get(MonitoredRepo, api_key.monitored_repo_id)
        if key_repo is None or key_repo.repo_path != requested_repo:
            bound_repo_path = key_repo.repo_path if key_repo else "?"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta API key solo es válida para el repo '{bound_repo_path}'.",
            )


def _persist_proposed_yara_rules(
    session: Session,
    proposed_rules: list[ProposedYaraRule],
    *,
    org_id: str,
    repo: str,
    pr_id: str,
) -> None:
    """Bucle de retroalimentación (tools.py::propose_yara_rule): una fila
    `PendingYaraRule` (status="pending") por propuesta aceptada de este
    análisis -- nunca se activa sola, queda pendiente de revisión humana
    (ver `dashboard/backend/routers/yara_rules.py`, `is_site_superadmin`).

    Deduplicado por `rule_name`: si el mismo PR se re-analiza (nuevo push,
    reintento), no debe generar una fila nueva por cada re-análisis
    mientras la propuesta anterior siga pendiente o ya se haya decidido
    sobre ella -- una regla RECHAZADA tampoco se vuelve a proponer sola."""
    for proposal in proposed_rules:
        existing = session.exec(
            select(PendingYaraRule).where(PendingYaraRule.rule_name == proposal.rule_name)
        ).first()
        if existing is not None:
            continue
        session.add(
            PendingYaraRule(
                id=str(uuid.uuid4()),
                org_id=org_id,
                repo=repo,
                pr_id=pr_id,
                rule_name=proposal.rule_name,
                category=proposal.category,
                yara_source=proposal.yara_source,
                rationale=proposal.rationale,
                status="pending",
            )
        )
    session.commit()


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

    requested_repo = requested_repo_for(request)
    ensure_api_key_repo_binding(session, api_key, org, requested_repo)

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

    if "reputation" not in request.metadata and "/" in requested_repo:
        author_login = request.metadata.get("author_login") or (
            (request.authors[0].login or request.authors[0].name) if request.authors else None
        )
        if author_login:
            token = os.environ.get("WATCHGATE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
            if not token and api_key.monitored_repo_id:
                key_repo = session.get(MonitoredRepo, api_key.monitored_repo_id)
                if key_repo and key_repo.vcs_connection_id:
                    vcs = session.get(VCSConnection, key_repo.vcs_connection_id)
                    if vcs and vcs.access_token:
                        token = vcs.access_token

            owner, repo_name = requested_repo.split("/", 1)
            pr_num = None
            if request.metadata.get("pr_id"):
                try:
                    pr_num = int(str(request.metadata.get("pr_id")))
                except (ValueError, TypeError):
                    pass

            try:
                client = GitHubClient(token)
                rep_metadata = client.get_reputation_metadata(
                    owner, repo_name, author_login, pr_number=pr_num, head_sha=request.head_sha
                )
                from watchgate.dashboard.backend.db import resolve_author_has_prior_high_risk_pr

                rep_metadata.author_has_prior_high_risk_pr = (
                    resolve_author_has_prior_high_risk_pr(
                        author_login, exclude_repo=requested_repo, exclude_pr_number=pr_num
                    )
                )
                request.metadata["reputation"] = rep_metadata
            except Exception:
                logger.debug("No se pudieron enriquecer metadatos de reputación", exc_info=True)

    quota_service = QuotaService(session)
    result, _is_degraded = quota_service.analyze_with_quota(
        diff=diff,
        metadata=request.metadata,
        config=config,
        org_id=org.id,
        user_id=user.id,
        agent_id=api_key.default_agent_name,
    )

    # Bucle de retroalimentación: propuestas de reglas YARA de la capa
    # semántica, si las hubo, quedan pendientes de revisión humana. Misma
    # sesión/BD que el resto de esta petición (Engine DB) -- a diferencia
    # del espejo al dashboard de más abajo, no hace falta abrir otra
    # conexión. Best-effort: un fallo aquí no debe tumbar una respuesta
    # 200 por un análisis que ya se hizo bien.
    semantic_result = result.layer_results.get("semantic")
    if semantic_result is not None and semantic_result.proposed_rules:
        try:
            _persist_proposed_yara_rules(
                session,
                semantic_result.proposed_rules,
                org_id=org.id,
                repo=result.repo,
                pr_id=result.pr_id,
            )
        except Exception:
            logger.warning(
                "No se pudieron persistir las reglas YARA propuestas para repo=%s pr_id=%s",
                result.repo,
                result.pr_id,
                exc_info=True,
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
            # AUDITORÍA (hallazgo crítico, corregido -- mismo patrón que
            # tasks.py, ver ese fichero): esto daba "admin_organizacion",
            # que `user_is_org_admin()` trata como admin GLOBAL sobre
            # TODOS los repos de TODAS las organizaciones (repo_roles no
            # tiene columna org_id). Como este endpoint corre en CADA
            # análisis real vía API Key (git-hook/CI/Action), cualquier
            # usuario con una API Key válida se autoconcedía superadmin
            # cross-tenant con solo analizar un PR. "mantenedor" preserva
            # la intención real (ver el propio repo en el dashboard) sin
            # ceder poder sobre organizaciones ajenas.
            upsert_role(dash_conn, user.name, result.repo, "mantenedor")
    except Exception:
        logger.warning(
            "No se pudo persistir el resultado en el dashboard para repo=%s pr_id=%s",
            result.repo,
            result.pr_id,
            exc_info=True,
        )

    return result
