"""Capa de reputación del autor (3c).

Ver docs/WatchGate_spec_implementacion_IA.md §6. Nunca hace llamadas HTTP:
toda la metadata llega ya resuelta desde el adaptador (A.0.1) en
metadata["reputation"], como un ReputationMetadata.
"""

from __future__ import annotations

from typing import Any

from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import LayerResult, NormalizedDiff, ReputationMetadata

_NO_METADATA_SKIP_REASON = "Sin metadatos de plataforma disponibles"


@register_layer
class ReputationLayer(AnalysisLayer):
    name = "reputation"

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        reputation = metadata.get("reputation")
        if isinstance(reputation, dict):
            try:
                reputation = ReputationMetadata.model_validate(reputation)
            except Exception:
                reputation = None

        if not isinstance(reputation, ReputationMetadata):
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="",
                skipped=True,
                skip_reason=_NO_METADATA_SKIP_REASON,
            )

        score = 0
        signals: list[str] = []

        if (
            reputation.author_account_age_days is not None
            and reputation.author_account_age_days < 30
        ):
            score += 10
            signals.append(
                f"La cuenta autora tiene {reputation.author_account_age_days} días de "
                "antigüedad (menos de 30)."
            )

        # 20 de los 30 puntos originales de "cuenta nueva" se han movido
        # aquí: una cuenta nueva es sospechosa por sí sola, pero un autor
        # con un PR anterior ya detectado como altamente malicioso (score
        # > 70, en cualquier repo que audite este Dashboard) es una señal
        # de reputación bastante más fuerte y concreta que la mera edad de
        # la cuenta -- se le da más peso a propósito. Lo resuelve
        # dashboard/backend/tasks.py antes de llamar a esta capa (ver
        # comentario de `author_has_prior_high_risk_pr` en
        # ReputationMetadata); si nunca se resolvió, el default es False y
        # esta señal simplemente no dispara.
        if reputation.author_has_prior_high_risk_pr:
            score += 20
            signals.append(
                "El autor tiene un PR anterior detectado con puntuación de riesgo alta "
                "(>70), posible indicio de actividad maliciosa recurrente."
            )

        if (
            reputation.author_public_repos == 0
            and reputation.author_followers == 0
            and reputation.author_account_age_days is not None
            and reputation.author_account_age_days < 90
        ):
            score += 15
            signals.append(
                "El perfil de GitHub del autor carece de actividad pública previa "
                "(0 repositorios públicos y 0 seguidores)."
            )

        if reputation.author_prior_contributions_to_repo == 0:
            score += 20
            signals.append("El autor no tiene contribuciones previas a este repositorio.")

        if not reputation.commit_email_matches_verified_email:
            score += 25
            signals.append(
                "El email del commit no coincide con un email verificado de la plataforma."
            )

        if reputation.repo_has_history_of_signed_commits and not reputation.commit_is_signed:
            score += 30
            signals.append(
                "El repositorio tiene historial de commits firmados, pero este commit no "
                "está firmado."
            )

        if reputation.commit_is_signed and reputation.signing_key_seen_before_for_login is False:
            score += 40
            signals.append(
                "El commit está firmado, pero con una clave que nunca se había visto antes "
                "para este usuario."
            )

        justification = (
            " ".join(signals)
            if signals
            else "No se han detectado señales de reputación sospechosas para este autor."
        )

        return LayerResult(
            layer_name=self.name,
            risk_score=min(100, score),
            justification=justification,
        )
