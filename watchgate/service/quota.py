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

        is_degraded = False
        if org_id:
            is_exceeded, used, quota = self.get_org_quota_status(org_id)
            if is_exceeded:
                is_degraded = True
                logger.warning(
                    "Org %s ha excedido su cuota mensual (%d / %d tokens). "
                    "Activando Modo Degradado Determinista.",
                    org_id,
                    used,
                    quota,
                )

        if is_degraded:
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

            # Imputar consumo de tokens si la capa semántica fue ejecutada y no omitida
            sem_res = result.layer_results.get("semantic")
            if sem_res and not sem_res.skipped:
                estimated_tokens = 1500 + (sem_res.tool_calls_made * 500)
                record_token_usage(
                    self.session,
                    user_id=user_id or "system",
                    tokens_used=estimated_tokens,
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
