#!/usr/bin/env python3
"""Formatea el JSON crudo de `watchgate analyze --format json` a texto legible,
para auditar_prs.sh -- a propósito, sin aplicar la redacción de
`render_comment` (comment_template.py) que colapsa el resultado a un mensaje
genérico cuando threat_summary.malicioso > 0. Esa redacción tiene sentido en
un comentario PÚBLICO de PR (no darle pistas a un atacante), pero aquí es un
informe de auditoría interno: se quiere ver exactamente qué disparó cada
capa, casos maliciosos incluidos.

Uso: watchgate analyze --format json ... | format_result.py <pr_number> <pr_author> <pr_url>
"""
from __future__ import annotations

import json
import sys

_SEMAFORO_EMOJI = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
_SEMAFORO_TEXTO = {"verde": "Bajo", "amarillo": "Medio", "rojo": "Alto"}
_RECOMENDACION = {
    "verde": "No se requiere acción adicional.",
    "amarillo": "Revisión humana recomendada antes de mergear.",
    "rojo": "Bloquear el merge hasta revisión humana explícita.",
}


def main() -> int:
    pr_number, pr_author, pr_url = sys.argv[1], sys.argv[2], sys.argv[3]
    data = json.load(sys.stdin)

    semaforo = data.get("semaforo", "")
    score = data.get("score", "?")
    lines: list[str] = []

    lines.append(f"--- PR #{pr_number} ({pr_url}) -- autor: {pr_author} ---")
    lines.append(
        f"[{_SEMAFORO_EMOJI.get(semaforo, '?')}] WatchGate: "
        f"Riesgo {_SEMAFORO_TEXTO.get(semaforo, semaforo)} ({score}/100)"
    )

    threat_summary = data.get("threat_summary") or {}
    malicioso = threat_summary.get("malicioso", 0)
    vulnerabilidad = threat_summary.get("vulnerabilidad", 0)
    incertidumbre = threat_summary.get("incertidumbre", 0)
    if malicioso or vulnerabilidad or incertidumbre:
        lines.append(
            f"Amenazas: 🚨 {malicioso} Maliciosa(s) | "
            f"⚠️ {vulnerabilidad} Vulnerabilidad(es) | "
            f"❓ {incertidumbre} Incertidumbre(s)"
        )
    lines.append("")

    weights = data.get("effective_weights") or data.get("weights_used") or {}
    layer_results = data.get("layer_results") or {}
    for name, result in layer_results.items():
        weight = weights.get(name, 0)
        risk = result.get("risk_score", 0)
        line = f"{name.capitalize()}: {risk}/100  (peso {weight})"
        if result.get("skipped"):
            line += f" — omitida: {result.get('skip_reason')}"
        lines.append(line)

        justification = result.get("justification")
        if justification:
            lines.append(f'    Justificación: "{justification}"')

        for finding in result.get("findings") or []:
            severity = finding.get("severity", "info")
            rule_id = finding.get("rule_id", "?")
            path = finding.get("file_path", "?")
            line_no = finding.get("line")
            loc = f"{path}:{line_no}" if line_no else path
            nature = finding.get("threat_nature")
            nature_suffix = f" [naturaleza: {nature}]" if nature else ""
            lines.append(f"    - [{severity}] {rule_id} ({loc}): {finding.get('message', '')}{nature_suffix}")

        lines.append("")

    lines.append(f"-> {_RECOMENDACION.get(semaforo, '')}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
