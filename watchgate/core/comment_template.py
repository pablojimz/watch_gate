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
    "{% if redacted %}"
    "Este cambio ha sido bloqueado por la política de seguridad del repositorio.\n"
    "No se publican detalles del análisis en este comentario. Si crees que es un "
    "error, contacta con un administrador del repositorio a través del dashboard.\n"
    "{% else %}"
    "{% if threat_summary and (threat_summary.get('malicioso', 0) > 0 or "
    "threat_summary.get('vulnerabilidad', 0) > 0 or threat_summary.get('incertidumbre', 0) > 0) %}"
    "Amenazas: 🚨 {{ threat_summary.get('malicioso', 0) }} Maliciosa(s) | "
    "⚠️ {{ threat_summary.get('vulnerabilidad', 0) }} Vulnerabilidad(es) | "
    "❓ {{ threat_summary.get('incertidumbre', 0) }} Incertidumbre(s)\n"
    # Rule 2: el "+" tras cada tag de cierre de abajo desactiva trim_blocks
    # SOLO para ese tag -- sin él, Jinja se come el "\n" literal que viene
    # justo después de un "%}" (es lo que hace trim_blocks=True), y todas
    # las líneas de capas/justificación/recomendación de más abajo colapsan
    # en una única línea ilegible. Nunca se había visto en producción porque
    # hasta ahora esta rama solo se ejercitaba con `redacted=False`, y en la
    # práctica casi cualquier análisis real caía por la rama `redacted=True`
    # de arriba (ver docstring de render_comment) -- que no pasa por aquí.
    "{% endif +%}\n"
    "{% for name, result in layer_results.items() -%}\n"
    "{{ name | capitalize }}: {{ result.risk_score }}/100  "
    "(peso {{ effective_weights.get(name, weights_used.get(name, 0)) }})"
    "{% if result.skipped %} — omitida: {{ result.skip_reason }}{% endif +%}\n"
    "{% endfor +%}\n"
    "{%- if 'semantic' in layer_results and not layer_results['semantic'].skipped %}\n"
    "Justificación (capa semántica):\n"
    "\"{{ layer_results['semantic'].justification }}\"\n"
    "{% endif +%}\n"
    "{% endif +%}\n"
    "-> {{ recomendacion }}\n"
)

_env = Environment(trim_blocks=True, lstrip_blocks=True)
_template = _env.from_string(_TEMPLATE_SOURCE)


def render_comment(result: AggregatedResult) -> str:
    """Renderiza el comentario de PR a partir de un AggregatedResult.

    Si el análisis encontró código malicioso (`threat_summary.malicioso > 0`,
    no una simple vulnerabilidad/CVE), el comentario se redacta a un mensaje
    genérico -- sin desglose por capa ni la justificación de la capa
    semántica. El autor del PR es, en este caso, un adversario potencial: un
    comentario público explicándole EXACTAMENTE qué patrón disparó la
    detección (p. ej. "detectamos la exfiltración vía curl a dominio X") le
    da la información que necesita para evadirla en el siguiente intento.
    Una vulnerabilidad no maliciosa (dependencia con CVE, config insegura)
    no tiene ese problema -- ahí sigue interesando explicarle al autor qué
    arreglar. El detalle completo del análisis, en ambos casos, sigue
    disponible para quien tenga acceso al dashboard (ver
    `ScoresTable`/`ReportModal` en el frontend)."""
    redacted = result.threat_summary.get("malicioso", 0) > 0
    return _template.render(
        semaforo_emoji=_SEMAFORO_EMOJI[result.semaforo],
        semaforo_texto=_SEMAFORO_TEXTO[result.semaforo],
        score=result.score,
        layer_results=result.layer_results,
        weights_used=result.weights_used,
        effective_weights=result.effective_weights or result.weights_used,
        recomendacion=_RECOMENDACION[result.semaforo],
        threat_summary=result.threat_summary,
        redacted=redacted,
    )
