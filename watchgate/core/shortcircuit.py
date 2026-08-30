"""Cortocircuito de extremo antes de la capa semántica (spec §11, A.3.4).

Opcional / objetivo ampliado. Se invoca *antes* de instanciar la capa
semántica en el orquestador, solo si `config.shortcircuit_enabled` es True.

Nota de invocación (responsabilidad de quien integre esto en el
orquestador, no de este módulo): si `evaluate_shortcircuit` devuelve un
`Semaforo`, hay que registrar igualmente un
`LayerResult(skipped=True, skip_reason="Cortocircuito de extremo aplicado")`
para la capa semántica, para que el dashboard sepa que no se ejecutó.

Decisiones de diseño que tomé y que no vienen fijadas por la spec (a
confirmar con el equipo):
- `_has_new_network_calls` usa una heurística textual propia (regex sobre el
  diff), no reinvoca Semgrep: el resultado de static_layer ya corrió y su
  risk_score es un agregado, no expone "hubo llamada de red sí/no" como
  señal independiente. Un falso positivo aquí solo implica NO cortocircuitar
  (se ejecuta la capa semántica de más), nunca sube el score.
- `_has_new_dependencies` reutiliza `DEPENDENCY_MANIFEST_FILENAMES` de
  `layers/_shared.py`, la misma lista que usa `deps_layer.py` (§5) para
  decidir si hay manifiestos tocados.
- El muestreo de auditoría (`audit_sampling table` en la spec) no se
  persiste desde aquí: se expone `on_audit_sample` como callback opcional
  para que quien invoque este módulo decida dónde registrarlo (podría ser
  una tabla nueva en la misma DB de `cost_control.py`).
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from pathlib import Path

from watchgate.core.aggregator import weighted_average
from watchgate.core.layers._shared import (
    DEPENDENCY_MANIFEST_FILENAMES,
    parse_manifest_file_change,
)
from watchgate.core.models import Confidence, LayerResult, NormalizedDiff, Semaforo, ThreatNature

FORCING_PATTERNS: list[str] = [r"PKGBUILD$", r"^\.github/workflows/", r"Makefile$", r"Dockerfile$"]

# Heurística ligera para detectar llamadas de red nuevas en el diff. No
# pretende ser exhaustiva (para eso está la regla Semgrep
# "network-call-in-build-script" de static_layer.py) — aquí basta con ser
# sensible, porque un falso positivo solo implica ejecutar la capa semántica
# de más, nunca subir el score.
_NETWORK_CALL_PATTERNS: list[str] = [
    r"requests\.(get|post|put|delete|patch)\(",
    r"fetch\(",
    r"\bcurl\s",
    r"Invoke-WebRequest",
    r"urllib\.request",
    r"httpx\.(get|post|put|delete)\(",
]

_FORCING_RE = [re.compile(p) for p in FORCING_PATTERNS]
_NETWORK_RE = [re.compile(p) for p in _NETWORK_CALL_PATTERNS]

_PARTIAL_LAYER_NAMES = ("static", "dependencies", "deps", "vulnerabilities", "reputation")


def _matches_forcing_pattern(diff: NormalizedDiff) -> bool:
    return any(any(p.search(fc.path) for p in _FORCING_RE) for fc in diff.files)


def _has_new_network_calls(diff: NormalizedDiff) -> bool:
    return any(
        any(p.search(fc.diff_hunk) for p in _NETWORK_RE) for fc in diff.files if not fc.is_binary
    )


def _has_new_dependencies(diff: NormalizedDiff) -> bool:
    manifest_files = [
        fc for fc in diff.files if Path(fc.path).name in DEPENDENCY_MANIFEST_FILENAMES
    ]
    if not manifest_files:
        return False

    for file_change in manifest_files:
        parsed = parse_manifest_file_change(file_change)
        if any(ch.is_new or ch.install_script or ch.is_direct_url for ch in parsed):
            return True

    return False


def evaluate_shortcircuit(
    partial_results: dict[str, LayerResult],
    weights: dict[str, float],
    diff: NormalizedDiff,
    thresholds: dict[str, int],
    rng: Callable[[], float] = random.random,
    on_audit_sample: Callable[[], None] | None = None,
) -> Semaforo | None:
    """Devuelve un Semaforo si se puede cortocircuitar sin llamar a la capa
    semántica, o None si hay que ejecutarla igualmente.

    `rng` se inyecta explícitamente (en vez de usar `random.random()` a
    pelo) para que el muestreo de auditoría 1/20 sea determinista en tests.
    """
    partial_score = weighted_average(partial_results, weights, layer_names=_PARTIAL_LAYER_NAMES)

    # Si alguna capa determinista encontró un hallazgo MALICIOUS de
    # confianza ALTA de verdad, cortocircuitar directamente a ROJO sin
    # gastar tokens en el LLM. Antes bastaba con `risk_score >= red
    # threshold` (sin mirar confidence en absoluto) -- mismo problema que
    # ya se corrigió hoy en `aggregator.py::_apply_malicious_and_uncertain_
    # policy`: `deps_layer.py` nunca rellena `confidence` y puntúa 75-80
    # para patrones habituales y a menudo legítimos (dependencia pinneada a
    # una URL de git, script postinstall con chmod +x), así que esto podía
    # cortocircuitar a ROJO -- sin darle nunca la oportunidad a la capa
    # semántica de matizarlo -- un PR benigno con `shortcircuit_enabled`
    # activo (opt-in, no es el default).
    for layer_res in partial_results.values():
        if (
            not layer_res.skipped
            and layer_res.threat_nature == ThreatNature.MALICIOUS
            and layer_res.confidence == Confidence.ALTA
        ):
            return Semaforo.ROJO

    # El cortocircuito a ROJO solo es seguro si incluso con un score semántico de 0
    # (el mejor caso para el autor), la media ponderada global resultante sigue siendo
    # mayor o igual al umbral de ROJO. De lo contrario, añadir la capa semántica con score 0
    # reduciría la media ponderada y podría bajar el veredicto a AMARILLO o VERDE.
    active_partial = {
        k: v
        for k, v in partial_results.items()
        if k in _PARTIAL_LAYER_NAMES and not v.skipped and weights.get(k, 0) > 0
    }
    partial_weighted_sum = sum(weights[k] * active_partial[k].risk_score for k in active_partial)
    partial_weight_sum = sum(weights[k] for k in active_partial)
    semantic_weight = weights.get("semantic", 0.0) if weights.get("semantic", 0.0) > 0 else 0.0
    total_weight = partial_weight_sum + semantic_weight

    if total_weight > 0:
        min_possible_score = partial_weighted_sum / total_weight
        if round(min_possible_score) >= thresholds["red"]:
            return Semaforo.ROJO

    forces_semantic = (
        _matches_forcing_pattern(diff)
        or _has_new_network_calls(diff)
        or _has_new_dependencies(diff)
    )

    # Auditoría: `skipped=True` no distinguía "esta capa decidió que no
    # había nada que comprobar" de "esta capa REVENTÓ" (safe_analyze /
    # _build_and_analyze en orchestrator.py también ponen skipped=True al
    # atrapar una excepción). Antes, si `static` se caía (timeout de
    # Semgrep, fallo de proceso) y el resto de capas deterministas no veía
    # nada sospechoso, este cortocircuito marcaba el diff VERDE sin que el
    # análisis estático hubiese llegado a ejecutarse de verdad -- confirmado
    # en vivo. `crashed=True` (ver models.py) marca ese caso de forma
    # explícita; con cobertura reducida por un fallo real, nunca es seguro
    # cortocircuitar a VERDE -- se deja caer a la capa semántica, la única
    # capa que sigue pudiendo aportar señal real pese al fallo de otra.
    any_partial_layer_crashed = any(
        res.crashed for name, res in partial_results.items() if name in _PARTIAL_LAYER_NAMES
    )

    if (
        partial_score < thresholds["yellow"] * 0.5
        and not forces_semantic
        and not any_partial_layer_crashed
    ):
        if rng() < 1 / 20:
            if on_audit_sample is not None:
                on_audit_sample()
            return None  # forzar semántica igualmente, pese a la baja señal parcial
        return Semaforo.VERDE

    return None
