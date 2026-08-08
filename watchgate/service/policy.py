"""Servicio de gobernanza y aplicación de políticas corporativas de la Organización."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from watchgate.config import WatchGateConfig
from watchgate.db.models import Organization

logger = logging.getLogger("watchgate.service.policy")

# Campos que un `config_override` enviado por un CLIENTE HTTP (agente de IA,
# potencialmente el mismo autor del PR que se está analizando) nunca puede
# tocar -- son exactamente los que deciden si un PR se marca rojo y si eso
# bloquea el merge. Ver `apply_client_config_override`: sin esto, un
# `config_override: {"thresholds": {"yellow": 999, "red": 999}}` hacía que
# el resultado fuera siempre VERDE con independencia de lo que detectaran
# las capas -- el agente autoaprobaba su propio PR malicioso. Solo la
# gobernanza de organización (`apply_policy_overrides`, controlada por un
# administrador vía `policy_json`, nunca por la petición HTTP) puede
# tocar estos campos.
CLIENT_OVERRIDE_FORBIDDEN_KEYS = frozenset(
    {"thresholds", "weights", "block_on_red", "shortcircuit_enabled"}
)

# Rango válido de un peso individual: negativo no tiene sentido (y
# `aggregator.py` excluye en silencio cualquier capa con peso <= 0 de la
# media ponderada, así que un peso negativo neutraliza esa capa sin que
# quede reflejado en `LayerResult.skipped` ni en ningún otro campo).
_MIN_WEIGHT = 0.0
_MAX_WEIGHT = 1.0
# Los thresholds son un score 0-100 (ver aggregator.py::_semaforo).
_MIN_THRESHOLD = 0
_MAX_THRESHOLD = 100


class ClientConfigOverrideError(ValueError):
    """`config_override` de un cliente HTTP intentó tocar un campo prohibido."""


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
        changes: list[str] = []

        # Sobreescritura de pesos (con validación de rango: un peso fuera de
        # [0, 1] o negativo se descarta, no se aplica a medias -- ver
        # comentario de `_MIN_WEIGHT` arriba).
        if "weights" in overrides and isinstance(overrides["weights"], dict):
            new_weights = dict(cfg_dict.get("weights", {}))
            for k, v in overrides["weights"].items():
                if isinstance(v, int | float) and _MIN_WEIGHT <= v <= _MAX_WEIGHT:
                    old = new_weights.get(str(k))
                    new_weights[str(k)] = float(v)
                    changes.append(f"weights.{k}: {old!r} -> {v!r}")
                else:
                    logger.warning(
                        "Org %s: peso '%s'=%r fuera de rango [%s, %s] en policy_json, ignorado.",
                        org.id,
                        k,
                        v,
                        _MIN_WEIGHT,
                        _MAX_WEIGHT,
                    )

            # Normalización
            total = sum(new_weights.values())
            if total > 0 and abs(total - 1.0) > 1e-4:
                new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}
            cfg_dict["weights"] = new_weights

        # Sobreescritura de umbrales (con validación de rango 0-100).
        if "thresholds" in overrides and isinstance(overrides["thresholds"], dict):
            new_thresholds = dict(cfg_dict.get("thresholds", {}))
            for k, v in overrides["thresholds"].items():
                if isinstance(v, int) and _MIN_THRESHOLD <= v <= _MAX_THRESHOLD:
                    old = new_thresholds.get(str(k))
                    new_thresholds[str(k)] = int(v)
                    changes.append(f"thresholds.{k}: {old!r} -> {v!r}")
                else:
                    logger.warning(
                        "Org %s: threshold '%s'=%r fuera de rango [%s, %s] en policy_json, "
                        "ignorado.",
                        org.id,
                        k,
                        v,
                        _MIN_THRESHOLD,
                        _MAX_THRESHOLD,
                    )
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
                old = cfg_dict.get(key)
                cfg_dict[key] = overrides[key]
                changes.append(f"{key}: {old!r} -> {overrides[key]!r}")

        try:
            effective_config = WatchGateConfig(**cfg_dict)
        except ValidationError as exc:
            # `policy_json` sintácticamente válido pero con un tipo
            # incorrecto (ej. monthly_budget_tokens: "unlimited") no debe
            # tumbar el análisis de TODA la organización con un 500 --
            # se ignora la política corrupta, se seguirá con la config
            # base hasta que se corrija, y queda registrado a voces.
            logger.error(
                "Org %s: policy_json produce una config inválida, IGNORANDO la política "
                "corporativa hasta que se corrija -- %s",
                org.id,
                exc,
            )
            return config

        logger.info(
            "Políticas corporativas de la Org %s aplicadas con éxito. Cambios: %s",
            org.id,
            "; ".join(changes) if changes else "(ninguno)",
        )
        return effective_config


def apply_client_config_override(
    base_config: WatchGateConfig, override: dict[str, Any] | None
) -> WatchGateConfig:
    """Aplica el `config_override` de una petición HTTP (agente de IA) sobre
    la config base, rechazando explícitamente los campos de seguridad
    listados en `CLIENT_OVERRIDE_FORBIDDEN_KEYS`.

    A diferencia de `PolicyService.apply_policy_overrides` (fuente de
    confianza: un administrador, vía `policy_json`), esto viene de una
    petición HTTP de un cliente potencialmente adversarial -- el mismo
    agente de IA que puede haber generado el PR que se está analizando.
    Lanza `ClientConfigOverrideError` (que el router debe convertir en un
    400) en vez de aplicar el override en silencio, para que un intento de
    tocar esos campos quede visible como error explícito, no como un
    bypass silencioso.
    """
    if not override:
        return base_config

    forbidden = sorted(CLIENT_OVERRIDE_FORBIDDEN_KEYS & override.keys())
    if forbidden:
        raise ClientConfigOverrideError(
            f"config_override no puede modificar {forbidden} -- esos campos solo los "
            "puede ajustar la gobernanza de la organización (policy_json), nunca la "
            "propia petición de análisis."
        )

    cfg_dict = base_config.model_dump()
    cfg_dict.update(override)
    try:
        return WatchGateConfig(**cfg_dict)
    except ValidationError as exc:
        raise ClientConfigOverrideError(f"config_override inválido: {exc}") from exc
