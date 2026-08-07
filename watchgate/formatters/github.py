"""Generador de GitHub Actions Workflow Commands (Annotations)."""

from __future__ import annotations

from typing import TextIO

from watchgate.core.models import AggregatedResult, Semaforo


def _escape_property(val: str) -> str:
    return val.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_data(val: str) -> str:
    return val.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def render_github_annotations(
    aggregated: AggregatedResult, stream: TextIO | None = None
) -> str:
    """Genera comandos de flujo de trabajo de GitHub Actions (`::error::`, `::warning::`).

    Rule 1: Si se especifica un stream (ej. `sys.stderr`), emite las anotaciones
    directamente sobre ese stream para aislar `sys.stdout`.
    """
    lines: list[str] = []

    # Anotación global de resumen
    if aggregated.semaforo == Semaforo.ROJO:
        cmd_type = "error"
    elif aggregated.semaforo == Semaforo.AMARILLO:
        cmd_type = "warning"
    else:
        cmd_type = "notice"

    msg = f"WatchGate: Riesgo global {aggregated.score}/100 ({aggregated.semaforo.value.upper()})"
    lines.append(f"::{cmd_type} title={_escape_property('WatchGate Score')}::{_escape_data(msg)}")

    # Anotaciones por hallazgo estructurado
    for layer_name, layer_res in aggregated.layer_results.items():
        if layer_res.skipped:
            continue

        if layer_res.findings:
            for finding in layer_res.findings:
                level = "error" if finding.severity.lower() == "error" else "warning"
                props: list[str] = [f"title={_escape_property(f'WatchGate [{layer_name}]')}"]
                if finding.file_path:
                    props.append(f"file={_escape_property(finding.file_path)}")
                if finding.line is not None and finding.line > 0:
                    props.append(f"line={finding.line}")
                if (
                    finding.line is not None
                    and finding.end_line is not None
                    and finding.end_line >= finding.line
                ):
                    props.append(f"endLine={finding.end_line}")

                props_str = ",".join(props)
                lines.append(f"::{level} {props_str}::{_escape_data(finding.message)}")
        elif layer_res.risk_score >= 40:
            level = "error" if layer_res.risk_score >= 70 else "warning"
            props_str = f"title={_escape_property(f'WatchGate [{layer_name}]')}"
            lines.append(f"::{level} {props_str}::{_escape_data(layer_res.justification)}")

    output_text = "\n".join(lines)
    if stream is not None:
        stream.write(output_text + "\n")
        stream.flush()

    return output_text
