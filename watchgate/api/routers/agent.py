"""Router REST con endpoints optimizados para Agentes de IA (watchgate/api/routers/agent.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from watchgate.api.auth import get_current_user_from_api_key
from watchgate.api.dependencies import get_db_session
from watchgate.api.routers.analyze import AnalyzeRequest
from watchgate.api.schemas.agent import (
    AgentAnalyzeResponse,
    AgentPolicyResponse,
    VerifyFixRequest,
    VerifyFixResponse,
    build_agent_guidance,
    compute_finding_signature,
)
from watchgate.config import WatchGateConfig, load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import AggregatedResult, Finding, LayerResult
from watchgate.db.models import Organization, User, UserAPIKey
from watchgate.service.policy import PolicyService
from watchgate.service.quota import QuotaService

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


@router.post("/precheck", response_model=AggregatedResult)
def agent_precheck(
    request: AnalyzeRequest,
    auth: tuple[UserAPIKey, User, Organization] = Depends(
        get_current_user_from_api_key
    ),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AggregatedResult:
    """Evaluación ultrarrápida (<100ms) utilizando únicamente capas deterministas.

    No consume tokens de LLM y proporciona feedback instantáneo para iteraciones rápidas.
    """
    api_key, user, org = auth

    diff = parse_diff_from_text(
        diff_text=request.diff_text,
        base_sha=request.base_sha,
        head_sha=request.head_sha,
        repo_path=request.repo_path,
        commit_messages=request.commit_messages,
        authors=request.authors,
    )

    base_config = load_config()
    cfg_dict = base_config.model_dump()
    if request.config_override:
        cfg_dict.update(request.config_override)

    # Forzar desactivación de la capa semántica para precheck ultrarrápido
    weights = dict(cfg_dict.get("weights", {}))
    weights["semantic"] = 0.0
    cfg_dict["weights"] = weights
    fast_config = WatchGateConfig(**cfg_dict)

    quota_service = QuotaService(session)
    result, _ = quota_service.analyze_with_quota(
        diff=diff,
        metadata=request.metadata,
        config=fast_config,
        org_id=org.id,
        user_id=user.id,
        agent_id=api_key.default_agent_name,
    )

    # Inyectar explicitamente el estado omitido de la capa semántica
    updated_layer_results = dict(result.layer_results)
    updated_layer_results["semantic"] = LayerResult(
        layer_name="semantic",
        risk_score=0,
        justification="",
        skipped=True,
        skip_reason="Deshabilitada para precheck ultrarrápido",
    )
    result = result.model_copy(update={"layer_results": updated_layer_results})

    return result


@router.post("/analyze", response_model=AgentAnalyzeResponse)
def agent_analyze(
    request: AnalyzeRequest,
    auth: tuple[UserAPIKey, User, Organization] = Depends(
        get_current_user_from_api_key
    ),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AgentAnalyzeResponse:
    """Análisis completo para agentes de IA con guía estructurada `AgentGuidance`."""
    api_key, user, org = auth

    diff = parse_diff_from_text(
        diff_text=request.diff_text,
        base_sha=request.base_sha,
        head_sha=request.head_sha,
        repo_path=request.repo_path,
        commit_messages=request.commit_messages,
        authors=request.authors,
    )

    base_config = load_config()
    if request.config_override:
        cfg_dict = base_config.model_dump()
        cfg_dict.update(request.config_override)
        config = WatchGateConfig(**cfg_dict)
    else:
        config = base_config

    quota_service = QuotaService(session)
    result, _ = quota_service.analyze_with_quota(
        diff=diff,
        metadata=request.metadata,
        config=config,
        org_id=org.id,
        user_id=user.id,
        agent_id=api_key.default_agent_name,
    )

    guidance = build_agent_guidance(result)
    return AgentAnalyzeResponse(analysis=result, guidance=guidance)


@router.post("/verify-fix", response_model=VerifyFixResponse)
def agent_verify_fix(
    request: VerifyFixRequest,
    auth: tuple[UserAPIKey, User, Organization] = Depends(
        get_current_user_from_api_key
    ),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> VerifyFixResponse:
    """Compara un diff original vs un diff candidato corregido por el agente.

    Identifica qué hallazgos fueron resueltos mediante firmas sintácticas estables.
    """
    api_key, user, org = auth
    base_config = load_config()
    if request.config_override:
        cfg_dict = base_config.model_dump()
        cfg_dict.update(request.config_override)
        config = WatchGateConfig(**cfg_dict)
    else:
        config = base_config

    quota_service = QuotaService(session)

    orig_diff = parse_diff_from_text(
        diff_text=request.original_diff,
        base_sha=request.base_sha,
        head_sha=request.head_sha,
        repo_path=request.repo_path,
    )
    orig_res, _ = quota_service.analyze_with_quota(
        diff=orig_diff,
        metadata={"repo": request.repo_path, "pr_id": "verify-orig"},
        config=config,
        org_id=org.id,
        user_id=user.id,
        agent_id=api_key.default_agent_name,
    )

    cand_diff = parse_diff_from_text(
        diff_text=request.candidate_diff,
        base_sha=request.base_sha,
        head_sha=request.head_sha,
        repo_path=request.repo_path,
    )
    cand_res, _ = quota_service.analyze_with_quota(
        diff=cand_diff,
        metadata={"repo": request.repo_path, "pr_id": "verify-cand"},
        config=config,
        org_id=org.id,
        user_id=user.id,
        agent_id=api_key.default_agent_name,
    )

    # Mapeo de hallazgos originales por firma
    orig_findings: dict[str, Finding] = {}
    for layer in orig_res.layer_results.values():
        if layer.skipped:
            continue
        for f in layer.findings:
            sig = compute_finding_signature(f)
            orig_findings[sig] = f

    # Mapeo de hallazgos candidatos por firma
    cand_signatures: set[str] = set()
    remaining_findings: list[Finding] = []
    for layer in cand_res.layer_results.values():
        if layer.skipped:
            continue
        for f in layer.findings:
            sig = compute_finding_signature(f)
            cand_signatures.add(sig)
            remaining_findings.append(f)

    resolved_findings = [
        f for sig, f in orig_findings.items() if sig not in cand_signatures
    ]

    risk_reduced = (
        cand_res.score < orig_res.score or len(resolved_findings) > 0
    )

    return VerifyFixResponse(
        risk_reduced=risk_reduced,
        previous_score=orig_res.score,
        new_score=cand_res.score,
        resolved_findings=resolved_findings,
        remaining_findings=remaining_findings,
    )


@router.get("/policy", response_model=AgentPolicyResponse)
def get_agent_policy(
    auth: tuple[UserAPIKey, User, Organization] = Depends(
        get_current_user_from_api_key
    ),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AgentPolicyResponse:
    """Devuelve las políticas corporativas y el estado de cuota restante de la organización."""
    _, _, org = auth

    quota_service = QuotaService(session)
    _is_exceeded, used, quota = quota_service.get_org_quota_status(org.id)
    remaining = max(0, quota - used)

    base_config = load_config()
    effective_config = PolicyService.apply_policy_overrides(base_config, org)

    return AgentPolicyResponse(
        org_id=org.id,
        monthly_token_quota=quota,
        tokens_used=used,
        quota_remaining=remaining,
        thresholds=effective_config.thresholds,
        weights=effective_config.weights,
        block_on_red=effective_config.block_on_red,
    )
