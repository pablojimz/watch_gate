"""Renderizado del comentario de PR (spec §10)."""

from __future__ import annotations

from jinja2 import Environment

from watchgate.core.models import AggregatedResult, Semaforo

_SEMAFORO_EMOJI: dict[Semaforo, str] = {
    Semaforo.VERDE: "🟢",
    Semaforo.AMARILLO: "🟡",
    Semaforo.ROJO: "🔴",
}

_SEMAFORO_TEXTO: dict[Semaforo, str] = {
    Semaforo.VERDE: "Bajo",
    Semaforo.AMARILLO: "Medio",
    Semaforo.ROJO: "Alto",
}

_RECOMENDACION: dict[Semaforo, str] = {
    Semaforo.VERDE: "No se requiere acción adicional.",
    Semaforo.AMARILLO: "Revisión humana recomendada antes de mergear.",
    Semaforo.ROJO: "Bloquear el merge hasta revisión humana explícita.",
}

_TEMPLATE_SOURCE = (
    "[{{ semaforo_emoji }}] WatchGate: Riesgo {{ semaforo_texto }} ({{ score }}/100)\n"
    "{% if threat_summary and (threat_summary.get('malicioso', 0) > 0 or "
    "threat_summary.get('vulnerabilidad', 0) > 0 or threat_summary.get('incertidumbre', 0) > 0) %}"
    "Amenazas: 🚨 {{ threat_summary.get('malicioso', 0) }} Maliciosa(s) | "
    "⚠️ {{ threat_summary.get('vulnerabilidad', 0) }} Vulnerabilidad(es) | "
    "❓ {{ threat_summary.get('incertidumbre', 0) }} Incertidumbre(s)\n"
    "{% endif %}\n"
    "{% for name, result in layer_results.items() -%}\n"
    "{{ name | capitalize }}: {{ result.risk_score }}/100  "
    "(peso {{ weights_used.get(name, 0) }})"
    "{% if result.skipped %} — omitida: {{ result.skip_reason }}{% endif %}\n"
    "{% endfor %}\n"
    "{%- if 'semantic' in layer_results and not layer_results['semantic'].skipped %}\n"
    "Justificación (capa semántica):\n"
    '"{{ layer_results[\'semantic\'].justification }}"\n'
    "{% endif %}\n"
    "-> {{ recomendacion }}\n"
)

_env = Environment(trim_blocks=True, lstrip_blocks=True)
_template = _env.from_string(_TEMPLATE_SOURCE)


def render_comment(result: AggregatedResult) -> str:
    """Renderiza el comentario de PR a partir de un AggregatedResult."""
    return _template.render(
        semaforo_emoji=_SEMAFORO_EMOJI[result.semaforo],
        semaforo_texto=_SEMAFORO_TEXTO[result.semaforo],
        score=result.score,
        layer_results=result.layer_results,
        weights_used=result.weights_used,
        recomendacion=_RECOMENDACION[result.semaforo],
        threat_summary=result.threat_summary,
    )
