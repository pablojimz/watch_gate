"""Servicio de gobernanza y aplicación de políticas corporativas de la Organización."""

from __future__ import annotations

import json
import logging
from typing import Any

from watchgate.config import WatchGateConfig
from watchgate.db.models import Organization

logger = logging.getLogger("watchgate.service.policy")


class PolicyService:
    """Aplica las políticas corporativas centralizadas registradas en SaaS/Organization."""

    @staticmethod
    def apply_policy_overrides(
        config: WatchGateConfig, org: Organization | None
    ) -> WatchGateConfig:
        """Aplica la gobernanza de la Organización sobre la configuración local `.watchgate.yml`.

        Las reglas y umbrales definidos en `org.policy_json` invalidan obligatoriamente
        las preferencias locales del repositorio o cliente.
        """
        if not org or not org.policy_json:
            return config

        try:
            overrides: dict[str, Any] = json.loads(org.policy_json)
        except Exception as err:
            logger.warning("Error al deserializar policy_json para la Org %s: %s", org.id, err)
            return config

        if not isinstance(overrides, dict):
            return config

        cfg_dict = config.model_dump()

        # Sobreescritura de pesos
        if "weights" in overrides and isinstance(overrides["weights"], dict):
            new_weights = dict(cfg_dict.get("weights", {}))
            for k, v in overrides["weights"].items():
                if isinstance(v, (int, float)):
                    new_weights[str(k)] = float(v)

            # Normalización
            total = sum(new_weights.values())
            if total > 0 and abs(total - 1.0) > 1e-4:
                new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}
            cfg_dict["weights"] = new_weights

        # Sobreescritura de umbrales
        if "thresholds" in overrides and isinstance(overrides["thresholds"], dict):
            new_thresholds = dict(cfg_dict.get("thresholds", {}))
            for k, v in overrides["thresholds"].items():
                if isinstance(v, int):
                    new_thresholds[str(k)] = int(v)
            cfg_dict["thresholds"] = new_thresholds

        # Sobreescrituras booleanas o numéricas directas
        for key in (
            "block_on_red",
            "shortcircuit_enabled",
            "max_diff_tokens",
            "monthly_budget_tokens",
            "max_dependency_checks",
        ):
            if key in overrides:
                cfg_dict[key] = overrides[key]

        logger.info("Políticas corporativas de la Org %s aplicadas con éxito.", org.id)
        return WatchGateConfig(**cfg_dict)
