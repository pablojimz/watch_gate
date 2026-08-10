"""Implementación de herramientas MCP de seguridad de WatchGate (watchgate/mcp/tools.py)."""

from __future__ import annotations

import json
from typing import Any

from watchgate.api.schemas.agent import (
    build_agent_guidance,
    compute_finding_signature,
)
from watchgate.config import WatchGateConfig, load_config
from watchgate.core.diffparser import parse_diff, parse_diff_from_text
from watchgate.core.models import AggregatedResult, Finding, LayerResult
from watchgate.core.pipeline import run_full_analysis
from watchgate.core.rag.retriever import retrieve_relevant_context
from watchgate.mcp.auth import open_session, resolve_mcp_identity
from watchgate.mcp.schemas import (
    McpTextContent,
    McpToolCallResult,
    McpToolDefinition,
    McpToolParameterSchema,
)
from watchgate.service.quota import QuotaService

TOOLS: list[McpToolDefinition] = [
    McpToolDefinition(
        name="watchgate_analyze_diff",
        description=(
            "Realiza un análisis completo de riesgo de seguridad sobre un diff o parche Git. "
            "Combina análisis estático, dependencias, reputación del autor y evaluación "
            "semántica con LLM/RAG, retornando el semáforo y la guía para el agente."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "diff_text": {
                    "type": "string",
                    "description": "Texto del diff o parche unificado a analizar.",
                },
                "base": {
                    "type": "string",
                    "description": "Commit o rama base (si no se provee diff_text directo).",
                    "default": "main",
                },
                "head": {
                    "type": "string",
                    "description": "Commit o rama head (si no se provee diff_text directo).",
                    "default": "HEAD",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Ruta al repositorio Git local.",
                    "default": ".",
                },
                "metadata": {
                    "type": "object",
                    "description": "Metadatos adicionales del análisis (ej: pr_id, repo, autor).",
                },
            },
            required=[],
        ),
    ),
    McpToolDefinition(
        name="watchgate_precheck",
        description=(
            "Evaluación ultrarrápida (<100ms) de riesgo utilizando únicamente capas deterministas "
            "(análisis estático, dependencias, reputación). Cero consumo de tokens LLM. "
            "Ideal para verificaciones instantáneas durante la edición de código."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "diff_text": {
                    "type": "string",
                    "description": "Texto del parche unificado a evaluar rápidamente.",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Ruta al repositorio Git local.",
                    "default": ".",
                },
            },
            required=["diff_text"],
        ),
    ),
    McpToolDefinition(
        name="watchgate_explain_risk",
        description=(
            "Genera un desglose explicativo detallado del nivel de riesgo, desglosando "
            "puntuaciones por capa, hallazgos concretos, justificaciones del LLM y factores "
            "determinantes para que el agente entienda exactamente el origen del riesgo."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "diff_text": {
                    "type": "string",
                    "description": "Texto del diff o parche a analizar y explicar.",
                },
                "analysis_json": {
                    "type": "string",
                    "description": "JSON de AggregatedResult previo para explicar el riesgo.",
                },
            },
            required=[],
        ),
    ),
    McpToolDefinition(
        name="watchgate_verify_fix",
        description=(
            "Compara un diff original (con alertas de seguridad) contra un nuevo diff candidato "
            "corregido por el agente. Utiliza firmas sintácticas estables para determinar si "
            "los hallazgos fueron resueltos con éxito."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "original_diff": {
                    "type": "string",
                    "description": "Texto del diff original que produjo hallazgos de seguridad.",
                },
                "candidate_diff": {
                    "type": "string",
                    "description": "Texto del nuevo diff candidato corregido por el agente.",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Ruta al repositorio local.",
                    "default": ".",
                },
            },
            required=["original_diff", "candidate_diff"],
        ),
    ),
    McpToolDefinition(
        name="watchgate_query_threat_kb",
        description=(
            "Consulta la base de conocimientos vectorial RAG de WatchGate sobre patrones "
            "de ataque conocidos, vulnerabilidades históricas y técnicas de MITRE ATT&CK."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "query": {
                    "type": "string",
                    "description": "Consulta de seguridad (ej: 'trojan source', 'dependency').",
                },
                "k": {
                    "type": "integer",
                    "description": "Número máximo de fragmentos relevantes a retornar.",
                    "default": 3,
                },
            },
            required=["query"],
        ),
    ),
    McpToolDefinition(
        name="watchgate_submit_feedback",
        description=(
            "Envía la confirmación o corrección sobre la evaluación de un "
            "análisis previo ('correcto' o 'falso_positivo') para realimentar "
            "las métricas y la base de conocimiento RAG de la organización."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "score_id": {
                    "type": "integer",
                    "description": "Identificador entero del análisis en el historial.",
                },
                "feedback": {
                    "type": "string",
                    "enum": ["correcto", "falso_positivo"],
                    "description": "'correcto' para confirmar, 'falso_positivo' para desestimar.",
                },
            },
            required=["score_id", "feedback"],
        ),
    ),
    McpToolDefinition(
        name="watchgate_repo_score_history",
        description=(
            "Consulta el historial de análisis de riesgo de un repositorio tal como lo ve el "
            "Dashboard (score, semáforo, desglose por capa y feedback humano de cada PR "
            "analizado). Requiere WATCHGATE_MCP_API_KEY configurada -- sin identidad de "
            "organización, no hay datos de dashboard que devolver. Respeta el rol del usuario "
            "por repositorio del Dashboard (mantenedor/revisor/admin): sin rol asignado en el "
            "repo solicitado, devuelve error de permiso denegado."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "repo": {
                    "type": "string",
                    "description": "Repositorio en formato 'owner/nombre'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de análisis a devolver (los más recientes).",
                    "default": 20,
                },
            },
            required=["repo"],
        ),
    ),
    McpToolDefinition(
        name="watchgate_org_metrics",
        description=(
            "Métricas agregadas de postura de seguridad tal como las ve el Dashboard: PRs "
            "analizados, score medio, distribución de semáforos, feedback humano acumulado y "
            "desglose por repositorio. Requiere WATCHGATE_MCP_API_KEY configurada. Sin "
            "'repos', agrega los repositorios del Dashboard visibles para el usuario según su "
            "rol (todos si es admin_organizacion); con 'repos', filtra a los que tenga rol "
            "asignado."
        ),
        inputSchema=McpToolParameterSchema(
            type="object",
            properties={
                "repos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Repositorios a agregar ('owner/nombre'). Si se omite, todos.",
                },
            },
            required=[],
        ),
    ),
]


def get_mcp_tools_list() -> list[McpToolDefinition]:
    """Retorna el catálogo de herramientas MCP expuestas por WatchGate."""
    return TOOLS


def execute_mcp_tool(name: str, arguments: dict[str, Any] | None) -> McpToolCallResult:
    """Ejecuta una herramienta MCP por nombre pasando sus argumentos."""
    args = arguments or {}

    try:
        if name == "watchgate_analyze_diff":
            return _handle_analyze_diff(args)
        elif name == "watchgate_precheck":
            return _handle_precheck(args)
        elif name == "watchgate_explain_risk":
            return _handle_explain_risk(args)
        elif name == "watchgate_verify_fix":
            return _handle_verify_fix(args)
        elif name == "watchgate_query_threat_kb":
            return _handle_query_threat_kb(args)
        elif name == "watchgate_repo_score_history":
            return _handle_repo_score_history(args)
        elif name == "watchgate_org_metrics":
            return _handle_org_metrics(args)
        elif name == "watchgate_submit_feedback":
            return _handle_submit_feedback(args)
        else:
            return McpToolCallResult(
                content=[McpTextContent(text=f"Herramienta no encontrada: '{name}'")],
                isError=True,
            )
    except Exception as exc:
        return McpToolCallResult(
            content=[McpTextContent(text=f"Error ejecutando la herramienta '{name}': {exc}")],
            isError=True,
        )


def _run_analysis_with_optional_quota(
    diff: Any, metadata: dict[str, Any], config: WatchGateConfig
) -> AggregatedResult:
    """Ejecuta el análisis real -- por `QuotaService` si `WATCHGATE_MCP_API_KEY`
    resuelve una identidad válida (cuota mensual respetada, coste registrado,
    `org_id` propagado al RAG distribuido, igual que la API REST de agentes),
    o directo si no hay identidad configurada (uso local sin organización,
    sin límites -- el comportamiento de siempre).

    Hallazgo real de revisión: antes esta tool llamaba a `run_full_analysis`
    siempre directo, sin pasar nunca por `QuotaService` -- ningún límite de
    presupuesto mensual ni `org_id` que aislara el feedback humano del RAG
    distribuido entre organizaciones, a diferencia de la API REST de agentes
    (`/api/v1/agent/*`), que sí lo hacía."""
    with open_session() as session:
        identity = resolve_mcp_identity(session)
        if identity is None:
            return run_full_analysis(diff=diff, metadata=metadata, config=config)

        api_key, user, org = identity
        quota_service = QuotaService(session)
        result, _is_degraded = quota_service.analyze_with_quota(
            diff=diff,
            metadata=metadata,
            config=config,
            org_id=org.id,
            user_id=user.id,
            agent_id=api_key.default_agent_name,
        )
        return result


def _handle_analyze_diff(args: dict[str, Any]) -> McpToolCallResult:
    diff_text = args.get("diff_text")
    repo_path = args.get("repo_path", ".")
    metadata = args.get("metadata") or {}

    config = load_config()

    if diff_text:
        diff = parse_diff_from_text(diff_text=diff_text, repo_path=repo_path)
    else:
        base = args.get("base", "main")
        head = args.get("head", "HEAD")
        diff = parse_diff(repo_path=repo_path, base_sha=base, head_sha=head)

    analysis_res = _run_analysis_with_optional_quota(diff, metadata, config)
    guidance = build_agent_guidance(analysis_res)

    output = {
        "analysis": analysis_res.model_dump(),
        "guidance": guidance.model_dump(),
    }
    return McpToolCallResult(content=[McpTextContent(text=json.dumps(output, indent=2))])


def _handle_precheck(args: dict[str, Any]) -> McpToolCallResult:
    diff_text = args.get("diff_text", "")
    repo_path = args.get("repo_path", ".")

    diff = parse_diff_from_text(diff_text=diff_text, repo_path=repo_path)

    base_config = load_config()
    cfg_dict = base_config.model_dump()
    weights = dict(cfg_dict.get("weights", {}))
    weights["semantic"] = 0.0
    cfg_dict["weights"] = weights
    fast_config = WatchGateConfig(**cfg_dict)

    analysis_res = run_full_analysis(diff=diff, metadata={"precheck": True}, config=fast_config)

    # Indicar explícitamente que la capa semántica fue omitida por precheck
    updated_layer_results = dict(analysis_res.layer_results)
    updated_layer_results["semantic"] = LayerResult(
        layer_name="semantic",
        risk_score=0,
        justification="",
        skipped=True,
        skip_reason="Deshabilitada para precheck ultrarrápido",
    )
    analysis_res = analysis_res.model_copy(update={"layer_results": updated_layer_results})

    guidance = build_agent_guidance(analysis_res)
    output = {
        "analysis": analysis_res.model_dump(),
        "guidance": guidance.model_dump(),
    }
    return McpToolCallResult(content=[McpTextContent(text=json.dumps(output, indent=2))])


def _handle_explain_risk(args: dict[str, Any]) -> McpToolCallResult:
    analysis_json = args.get("analysis_json")
    diff_text = args.get("diff_text")

    if analysis_json:
        data = json.loads(analysis_json)
        res = AggregatedResult.model_validate(data)
    elif diff_text:
        diff = parse_diff_from_text(diff_text=diff_text)
        config = load_config()
        res = run_full_analysis(diff=diff, metadata={}, config=config)
    else:
        msg = "Debe proporcionar 'diff_text' o 'analysis_json' para explicar el riesgo."
        return McpToolCallResult(
            content=[McpTextContent(text=msg)],
            isError=True,
        )

    explanation_lines = [
        "=== Explicación de Riesgo WatchGate ===",
        f"Puntuación Global de Riesgo: {res.score}/100",
        f"Semáforo: {res.semaforo.value.upper()}",
        f"Resumen de Amenazas: {res.threat_summary}",
        "",
        "--- Desglose por Capas ---",
    ]

    for layer_name, layer_res in res.layer_results.items():
        if layer_res.skipped:
            explanation_lines.append(
                f"• [{layer_name.upper()}] OMITIDA (Razón: {layer_res.skip_reason})"
            )
            continue

        explanation_lines.append(f"• [{layer_name.upper()}] Nota: {layer_res.risk_score}/100")
        if layer_res.justification:
            explanation_lines.append(f"  Justificación: {layer_res.justification}")
        if layer_res.findings:
            explanation_lines.append(f"  Hallazgos ({len(layer_res.findings)}):")
            for f in layer_res.findings:
                msg_line = f"    - [{f.severity.upper()}] {f.rule_id} en {f.file_path}"
                if f.line:
                    msg_line += f":{f.line}"
                msg_line += f": {f.message}"
                explanation_lines.append(msg_line)

    guidance = build_agent_guidance(res)
    explanation_lines.extend(
        [
            "",
            "--- Guía para el Agente ---",
            f"Acción recomendada: {guidance.recommended_action}",
            f"Resumen: {guidance.summary_for_agent}",
        ]
    )

    if guidance.actionable_steps:
        explanation_lines.append("Pasos concretos de corrección:")
        for idx, step in enumerate(guidance.actionable_steps, start=1):
            line_str = f":{step.line}" if step.line else ""
            step_str = (
                f"  {idx}. [{step.file_path}{line_str}] {step.problem} -> {step.suggested_action}"
            )
            explanation_lines.append(step_str)

    return McpToolCallResult(content=[McpTextContent(text="\n".join(explanation_lines))])


def _handle_verify_fix(args: dict[str, Any]) -> McpToolCallResult:
    original_diff = args.get("original_diff", "")
    candidate_diff = args.get("candidate_diff", "")
    repo_path = args.get("repo_path", ".")

    config = load_config()

    orig_diff_obj = parse_diff_from_text(diff_text=original_diff, repo_path=repo_path)
    orig_res = _run_analysis_with_optional_quota(orig_diff_obj, {}, config)

    cand_diff_obj = parse_diff_from_text(diff_text=candidate_diff, repo_path=repo_path)
    cand_res = _run_analysis_with_optional_quota(cand_diff_obj, {}, config)

    orig_findings: dict[str, Finding] = {}
    for layer in orig_res.layer_results.values():
        if layer.skipped:
            continue
        for f in layer.findings:
            sig = compute_finding_signature(f)
            orig_findings[sig] = f

    cand_signatures: set[str] = set()
    remaining_findings: list[Finding] = []
    for layer in cand_res.layer_results.values():
        if layer.skipped:
            continue
        for f in layer.findings:
            sig = compute_finding_signature(f)
            cand_signatures.add(sig)
            remaining_findings.append(f)

    resolved_findings = [f for sig, f in orig_findings.items() if sig not in cand_signatures]
    risk_reduced = cand_res.score < orig_res.score or len(resolved_findings) > 0

    output = {
        "risk_reduced": risk_reduced,
        "previous_score": orig_res.score,
        "new_score": cand_res.score,
        "resolved_findings_count": len(resolved_findings),
        "resolved_findings": [f.model_dump() for f in resolved_findings],
        "remaining_findings_count": len(remaining_findings),
        "remaining_findings": [f.model_dump() for f in remaining_findings],
    }

    return McpToolCallResult(content=[McpTextContent(text=json.dumps(output, indent=2))])


def _handle_query_threat_kb(args: dict[str, Any]) -> McpToolCallResult:
    query = args.get("query", "")
    k = int(args.get("k", 3))

    # Hallazgo real de revisión: sin `org_id`, `retrieve_relevant_context`
    # consulta la colección de feedback humano SIN filtrar -- en RAG
    # distribuido (`WATCHGATE_CHROMA_URL` compartido entre organizaciones),
    # esta tool devolvía el feedback de TODAS las organizaciones mezclado,
    # sin el aislamiento que ya tiene la API REST (`quota.py`). El corpus
    # público (`attack_patterns`) sigue sin filtrar nunca -- es
    # intencionalmente compartido, esto solo afecta al feedback propio.
    with open_session() as session:
        identity = resolve_mcp_identity(session)
        # `.id` leído DENTRO del `with`: fuera, con la sesión ya cerrada,
        # acceder a un atributo de un objeto ORM expirado/detached lanza
        # `DetachedInstanceError` -- bug real que se coló aquí mismo en la
        # primera versión de este fix, atrapado por el test de este caso.
        org_id = identity[2].id if identity is not None else None

    fragments = retrieve_relevant_context(diff_summary=query, k=k, org_id=org_id)

    if not fragments:
        no_frag_msg = (
            f"No se encontraron fragmentos relevantes en la base "
            f"de conocimientos para la consulta '{query}'."
        )
        return McpToolCallResult(content=[McpTextContent(text=no_frag_msg)])

    results = []
    for frag in fragments:
        results.append(
            {
                "case_name": frag.case_name,
                "origin": frag.origin,
                "verdict": frag.verdict,
                "text": frag.text,
            }
        )

    return McpToolCallResult(content=[McpTextContent(text=json.dumps(results, indent=2))])


_NO_MCP_IDENTITY_ERROR = (
    "Esta herramienta necesita una organización -- configura WATCHGATE_MCP_API_KEY "
    "con una API Key de WatchGate válida (la misma que usarías contra la Engine API) "
    "antes de usarla."
)


def _handle_repo_score_history(args: dict[str, Any]) -> McpToolCallResult:
    repo = args.get("repo")
    limit = int(args.get("limit", 20))
    if not repo:
        return McpToolCallResult(
            content=[McpTextContent(text="Falta el parámetro requerido 'repo'.")],
            isError=True,
        )

    with open_session() as session:
        identity = resolve_mcp_identity(session)
        if identity is None:
            return McpToolCallResult(
                content=[McpTextContent(text=_NO_MCP_IDENTITY_ERROR)],
                isError=True,
            )
        _key, user, _org = identity
        user_login = user.name

    from watchgate.dashboard.backend import db as dashboard_db

    with dashboard_db.db_session() as conn:
        is_admin = dashboard_db.user_is_org_admin(conn, user_login)
        if not is_admin and dashboard_db.get_role(conn, user_login, repo) is None:
            return McpToolCallResult(
                content=[McpTextContent(text=f"Permiso denegado: Sin rol asignado en '{repo}'.")],
                isError=True,
            )
        scores = dashboard_db.list_scores(conn, repo)

    output = [s.model_dump(mode="json") for s in scores[:limit]]
    return McpToolCallResult(content=[McpTextContent(text=json.dumps(output, indent=2))])


def _handle_org_metrics(args: dict[str, Any]) -> McpToolCallResult:
    requested_repos = args.get("repos")

    with open_session() as session:
        identity = resolve_mcp_identity(session)
        if identity is None:
            return McpToolCallResult(
                content=[McpTextContent(text=_NO_MCP_IDENTITY_ERROR)],
                isError=True,
            )
        _key, user, _org = identity
        user_login = user.name

    from watchgate.dashboard.backend import db as dashboard_db

    with dashboard_db.db_session() as conn:
        is_admin = dashboard_db.user_is_org_admin(conn, user_login)
        if requested_repos:
            repos = [
                r
                for r in requested_repos
                if is_admin or dashboard_db.get_role(conn, user_login, r) is not None
            ]
        else:
            repos = dashboard_db.list_repos_for_user(conn, user_login, is_admin=is_admin)
        metrics = dashboard_db.compute_org_metrics(conn, repos)

    return McpToolCallResult(content=[McpTextContent(text=metrics.model_dump_json(indent=2))])


def _handle_submit_feedback(args: dict[str, Any]) -> McpToolCallResult:
    score_id = args.get("score_id")
    feedback = args.get("feedback")
    if score_id is None or not feedback:
        return McpToolCallResult(
            content=[McpTextContent(text="Se requieren los parámetros 'score_id' y 'feedback'.")],
            isError=True,
        )

    with open_session() as session:
        identity = resolve_mcp_identity(session)
        if identity is None:
            return McpToolCallResult(
                content=[McpTextContent(text=_NO_MCP_IDENTITY_ERROR)],
                isError=True,
            )
        _user_api_key, user, _org = identity
        user_name = str(user.name)

    from watchgate.dashboard.backend import db as dashboard_db
    from watchgate.db.repository import check_user_repo_permission

    with dashboard_db.db_session() as conn:
        existing = dashboard_db.get_score(conn, int(score_id))
        if existing is None:
            return McpToolCallResult(
                content=[McpTextContent(text=f"Análisis con ID '{score_id}' no encontrado.")],
                isError=True,
            )

        with open_session() as session:
            has_perm = check_user_repo_permission(
                session, user_name, existing.repo, required_role="mantenedor"
            )
        if not has_perm:
            msg = (
                f"Permiso denegado: Se requiere rol 'mantenedor' sobre el "
                f"repositorio '{existing.repo}'."
            )
            return McpToolCallResult(
                content=[McpTextContent(text=msg)],
                isError=True,
            )

        if feedback not in ("correcto", "falso_positivo"):
            msg_err = "El feedback debe ser 'correcto' o 'falso_positivo'."
            return McpToolCallResult(
                content=[McpTextContent(text=msg_err)],
                isError=True,
            )
        updated = dashboard_db.set_feedback(conn, int(score_id), feedback)
        if updated is None:
            return McpToolCallResult(
                content=[McpTextContent(text=f"Error actualizando feedback para ID '{score_id}'.")],
                isError=True,
            )

    res = {
        "status": "success",
        "score_id": score_id,
        "repo": existing.repo,
        "feedback": feedback,
    }
    return McpToolCallResult(content=[McpTextContent(text=json.dumps(res, indent=2))])
