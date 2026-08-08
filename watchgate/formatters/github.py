"""Generador de GitHub Actions Workflow Commands (Annotations)."""

from __future__ import annotations

from typing import TextIO

from watchgate.core.models import AggregatedResult, Semaforo


def _escape_property(val: str) -> str:
    """Escapa un valor de propiedad (`title=`, `file=`, ...) para un comando
    de workflow de GitHub Actions.

    A diferencia de `_escape_data` (el mensaje, que va después del último
    `::`), los VALORES DE PROPIEDAD viven dentro de una lista separada por
    `,` (`::warning key=val,key=val::mensaje`), así que además de `%`/`\\r`/
    `\\n` hay que escapar `:` y `,` -- son los delimitadores de esa sintaxis.
    Sin esto, un `file_path` con esos caracteres (contenido controlado por
    el autor del PR, p. ej. un nombre de fichero) puede inyectar
    propiedades falsas (`line=999,title=FAKE`) o incluso un `::error ...::`
    completo, corrompiendo la anotación real. Ver
    https://github.com/actions/toolkit/blob/main/docs/commands.md
    """
    return (
        val.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


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
                nat = finding.threat_nature.value.upper() if finding.threat_nature else ""
                nat_prefix = f"[{nat}] " if nat else ""
                full_msg = _escape_data(nat_prefix + finding.message)
                lines.append(f"::{level} {props_str}::{full_msg}")
        elif layer_res.risk_score >= 40:
            level = "error" if layer_res.risk_score >= 70 else "warning"
            props_str = f"title={_escape_property(f'WatchGate [{layer_name}]')}"
            lines.append(f"::{level} {props_str}::{_escape_data(layer_res.justification)}")

    output_text = "\n".join(lines)
    if stream is not None:
        stream.write(output_text + "\n")
        stream.flush()

    return output_text
