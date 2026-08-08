"""Servicio de control de cuotas de tokens de LLM y Modo Degradado Inteligente."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session

from watchgate.config import WatchGateConfig
from watchgate.core.models import AggregatedResult, LayerResult, NormalizedDiff
from watchgate.core.pipeline import run_full_analysis
from watchgate.db.repository import (
    get_organization,
    get_token_usage,
    record_token_usage,
    save_pr_score,
)
from watchgate.service.policy import PolicyService

logger = logging.getLogger("watchgate.service.quota")

# Reserva conservadora de tokens que se imputa de forma ATÓMICA antes de
# llamar al LLM (ver `analyze_with_quota`) -- 1500 es el coste base que ya
# usaba la fórmula de imputación real, y 3 el máximo de "tool calls" que la
# capa semántica permite por diseño (`_semantic/layer.py`). No necesita ser
# exacta: solo tiene que ser una cota razonable para que la ventana de
# carrera entre comprobar cuota y contabilizar consumo quede cerrada por el
# propio incremento atómico, no por una comprobación previa separada.
_ESTIMATED_TOKENS_RESERVATION = 1500 + 3 * 500


class QuotaService:
    """Gestiona la auditoría de presupuestos mensuales de tokens e imponen el Modo Degradado."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_org_quota_status(self, org_id: str) -> tuple[bool, int, int]:
        """Comprueba el consumo mensual acumulado de la organización contra su cuota.

        Retorna: (is_quota_exceeded, tokens_used, monthly_quota)
        """
        org = get_organization(self.session, org_id)
        monthly_quota = org.monthly_token_quota if org else 1_000_000

        current_month = datetime.now(UTC).strftime("%Y-%m")
        tokens_used = get_token_usage(self.session, month=current_month, org_id=org_id)

        is_exceeded = tokens_used >= monthly_quota
        return is_exceeded, tokens_used, monthly_quota

    def analyze_with_quota(
        self,
        diff: NormalizedDiff,
        metadata: dict[str, Any],
        config: WatchGateConfig,
        org_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[AggregatedResult, bool]:
        """Ejecuta el análisis de riesgo respetando las cuotas de tokens de la organización.

        Si la cuota de la organización ha sido superada, conmuta automáticamente al
        **Modo Degradado Inteligente** (Opción B), omitiendo la capa semántica y
        re-normalizando las capas deterministas activas, retornando `HTTP 200 OK`.

        Retorna: (AggregatedResult, is_degraded)
        """
        org = get_organization(self.session, org_id) if org_id else None
        config = PolicyService.apply_policy_overrides(config, org)
        if org_id:
            # Propaga org_id a las capas (hoy solo lo consume SemanticLayer,
            # para filtrar por tenant el feedback humano del RAG distribuido
            # -- ver retriever.py) sin obligar a cada caller de
            # analyze_with_quota a montarlo ya dentro de `metadata` a mano.
            #
            # SIEMPRE se sobrescribe, nunca "solo si falta": `metadata` viene
            # de un dict sin validar que un cliente HTTP controla por
            # completo (`AnalyzeRequest.metadata`, `dict[str, Any]`) -- si se
            # respetase un `org_id` ya presente en el payload, cualquier
            # cliente autenticado podía pedir el `org_id` de OTRA
            # organización en su propia petición y filtrar así su feedback
            # humano del RAG distribuido (ver retriever.py), o vaciar el
            # filtro por completo con `org_id: null`/`""` para ver el
            # feedback de TODAS las organizaciones mezclado. El org_id real
            # es el que resuelve la autenticación (`org_id` de este
            # parámetro), nunca el que declare el propio cliente.
            metadata = {**metadata, "org_id": org_id}
        effective_user_id = user_id or "system"

        is_degraded = False
        reserved = False
        if org_id:
            monthly_quota = org.monthly_token_quota if org else 1_000_000
            # Reserva ATÓMICA antes de decidir si se llama al LLM. Antes,
            # `get_org_quota_status` (un SELECT) se comprobaba ANTES de la
            # llamada al LLM (que tarda segundos) y el consumo real solo se
            # contabilizaba DESPUÉS -- peticiones concurrentes de la misma
            # organización dentro de esa ventana leían todas "cuota no
            # superada" y todas acababan llamando al LLM, permitiendo
            # sobrepasar la cuota proporcionalmente a la concurrencia,
            # incluso con `record_token_usage` ya siendo atómico por sí
            # solo (eso solo evita perder incrementos, no cierra esta
            # ventana de check-then-act). Reservar aquí, de forma atómica y
            # ANTES de la llamada al LLM, hace que el propio incremento en
            # base de datos sea el "check" y el "act" en una sola operación.
            usage_after_reservation = record_token_usage(
                self.session,
                user_id=effective_user_id,
                tokens_used=_ESTIMATED_TOKENS_RESERVATION,
                org_id=org_id,
            ).tokens_used
            reserved = True
            if usage_after_reservation > monthly_quota:
                is_degraded = True
                logger.warning(
                    "Org %s ha excedido su cuota mensual (%d / %d tokens tras reservar). "
                    "Activando Modo Degradado Determinista.",
                    org_id,
                    usage_after_reservation,
                    monthly_quota,
                )

        if is_degraded:
            if reserved:
                # No se va a llamar al LLM: liberar la reserva que no se usará.
                record_token_usage(
                    self.session,
                    user_id=effective_user_id,
                    tokens_used=-_ESTIMATED_TOKENS_RESERVATION,
                    org_id=org_id,
                )

            # Modo Degradado: desactivar capa semántica y re-normalizar capas deterministas
            cfg_dict = config.model_dump()
            weights = dict(cfg_dict.get("weights", {}))
            weights["semantic"] = 0.0
            cfg_dict["weights"] = weights
            degraded_config = WatchGateConfig(**cfg_dict)

            result = run_full_analysis(diff, metadata, degraded_config)

            # Inyectar explicitamente el resultado de la capa semántica omitida por cuota
            updated_layer_results = dict(result.layer_results)
            updated_layer_results["semantic"] = LayerResult(
                layer_name="semantic",
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=(
                    "Cuota mensual de tokens alcanzada. Modo Degradado Determinista activo."
                ),
            )
            result = result.model_copy(update={"layer_results": updated_layer_results})
        else:
            # Modo Estándar
            result = run_full_analysis(diff, metadata, config)

            # Imputar el consumo REAL, ajustando contra lo ya reservado
            # arriba (delta puede ser negativo si se reservó de más, p. ej.
            # la capa semántica se saltó por otro motivo -- presupuesto
            # local del repo, fallo del cliente LLM -- o hizo menos "tool
            # calls" de los asumidos por la reserva).
            sem_res = result.layer_results.get("semantic")
            if sem_res and not sem_res.skipped:
                actual_tokens = 1500 + (sem_res.tool_calls_made * 500)
            else:
                actual_tokens = 0
            delta = actual_tokens - (_ESTIMATED_TOKENS_RESERVATION if reserved else 0)
            if delta != 0:
                record_token_usage(
                    self.session,
                    user_id=effective_user_id,
                    tokens_used=delta,
                    org_id=org_id,
                )

        # Registrar puntuación en el histórico
        save_pr_score(
            self.session,
            aggregated_result=result,
            user_id=user_id,
            org_id=org_id,
            agent_id=agent_id,
        )

        return result, is_degraded
