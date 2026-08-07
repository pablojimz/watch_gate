"""Esquemas de datos Pydantic v2 para la API de Agentes de IA (watchgate/api/schemas/agent.py)."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from watchgate.core.models import AggregatedResult, Finding, Semaforo


class ActionableStep(BaseModel):
    """Paso concreto de corrección sugerido para un agente de código."""

    file_path: str = Field(description="Ruta del archivo afectado")
    line: int | None = Field(default=None, description="Número de línea aproximado")
    problem: str = Field(description="Descripción del problema o regla violada")
    suggested_action: str = Field(description="Instrucciones concretas para corregir el código")


class AgentGuidance(BaseModel):
    """Estructuración accionable para guiar el bucle de autocorrección del agente."""

    is_mergeable: bool = Field(
        description="True si la propuesta cumple las políticas y puede fusionarse"
    )
    recommended_action: str = Field(
        description="Acción recomendada: 'PROCEED', 'RETRY_WITH_FIX', 'BLOCK_HUMAN_REVIEW'"
    )
    summary_for_agent: str = Field(description="Resumen conciso del estado de seguridad")
    actionable_steps: list[ActionableStep] = Field(
        default_factory=list,
        description="Lista de pasos concretos a seguir para corregir hallazgos",
    )


class AgentAnalyzeResponse(BaseModel):
    """Respuesta completa del análisis REST para un agente de IA."""

    analysis: AggregatedResult
    guidance: AgentGuidance


class VerifyFixRequest(BaseModel):
    """Solicitud para verificar si un nuevo parche candidato soluciona las alertas previas."""

    original_diff: str = Field(description="Diff original que generó alertas")
    candidate_diff: str = Field(description="Nuevo diff corregido generado por el agente")
    base_sha: str = Field(default="0000000")
    head_sha: str = Field(default="0000000")
    repo_path: str = Field(default=".")
    config_override: dict[str, Any] | None = Field(
        default=None, description="Ajustes opcionales de configuración para anular defaults"
    )


class VerifyFixResponse(BaseModel):
    """Resultado comparativo tras evaluar la corrección del agente."""

    risk_reduced: bool = Field(
        description="True si el nivel de riesgo o número de alertas disminuyó"
    )
    previous_score: int = Field(description="Puntuación de riesgo del diff original (0-100)")
    new_score: int = Field(description="Puntuación de riesgo del diff candidato (0-100)")
    resolved_findings: list[Finding] = Field(
        default_factory=list, description="Lista de hallazgos resueltos con éxito"
    )
    remaining_findings: list[Finding] = Field(
        default_factory=list, description="Lista de hallazgos aún presentes en el nuevo diff"
    )


class AgentPolicyResponse(BaseModel):
    """Información de políticas corporativas y cuotas vigentes para la organización."""

    org_id: str
    monthly_token_quota: int
    tokens_used: int
    quota_remaining: int
    thresholds: dict[str, int]
    weights: dict[str, float]
    block_on_red: bool


def compute_finding_signature(finding: Finding) -> str:
    """Calcula un hash sintáctico estable para un hallazgo ignorando números de línea volátiles.

    Utilizado por `verify-fix` para comparar hallazgos entre versiones de parches.
    """
    raw_key = f"{finding.rule_id}:{finding.file_path}:{finding.severity}:{finding.message}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def build_agent_guidance(aggregated_result: AggregatedResult) -> AgentGuidance:
    """Construye las instrucciones accionables (`AgentGuidance`) desde `AggregatedResult`."""
    is_mergeable = aggregated_result.semaforo != Semaforo.ROJO

    if aggregated_result.semaforo == Semaforo.VERDE:
        recommended_action = "PROCEED"
        summary = (
            "El análisis no ha detectado amenazas críticas ni vulnerabilidades de alto riesgo. "
            "Código listo para merge."
        )
    elif aggregated_result.semaforo == Semaforo.AMARILLO:
        recommended_action = "RETRY_WITH_FIX"
        summary = (
            f"Riesgo medio ({aggregated_result.score}/100). "
            "Se recomienda corregir las advertencias antes de solicitar el merge."
        )
    else:
        recommended_action = "BLOCK_HUMAN_REVIEW"
        summary = (
            f"Riesgo alto/bloqueante ({aggregated_result.score}/100). "
            "Fusión rechazada por políticas de seguridad."
        )

    steps: list[ActionableStep] = []
    for layer_name, layer_res in aggregated_result.layer_results.items():
        if layer_res.skipped:
            continue
        for f in layer_res.findings:
            if f.severity in ("error", "warning"):
                steps.append(
                    ActionableStep(
                        file_path=f.file_path,
                        line=f.line,
                        problem=f"[{layer_name.upper()}] {f.rule_id}: {f.message}",
                        suggested_action=(
                            f"Revisar {f.file_path} y eliminar o refactorizar el patrón "
                            f"detectado por {f.rule_id}."
                        ),
                    )
                )

    return AgentGuidance(
        is_mergeable=is_mergeable,
        recommended_action=recommended_action,
        summary_for_agent=summary,
        actionable_steps=steps,
    )
