"""Formateador de consola interactiva TTY usando Rich."""

from __future__ import annotations

import io

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from watchgate.core.comment_template import render_comment
from watchgate.core.models import AggregatedResult, Semaforo


def render_console(aggregated: AggregatedResult) -> str:
    """Renderiza el resultado del análisis con paneles y tablas enriquecidas de Rich.

    Si ocurre cualquier error durante el renderizado con Rich, se utiliza
    `render_comment` como fallback transparente.
    """
    try:
        string_io = io.StringIO()
        console = Console(file=string_io, width=120)

        # 1. Determinar estilo y badge según el semáforo
        if aggregated.semaforo == Semaforo.ROJO:
            color = "red"
            badge = "[BLOCK] RIESGO ALTO"
        elif aggregated.semaforo == Semaforo.AMARILLO:
            color = "yellow"
            badge = "[WARN] RIESGO MEDIO"
        else:
            color = "green"
            badge = "[PASS] RIESGO BAJO"

        header_text = Text()
        header_text.append(f"{badge}\n", style=f"bold {color}")
        header_text.append(
            f"Puntuación Global de Riesgo: {aggregated.score}/100\n", style="bold"
        )
        header_text.append(f"PR ID: {aggregated.pr_id or 'N/A'} | Repo: {aggregated.repo or 'N/A'}")

        console.print(
            Panel(
                header_text,
                title="[bold]WatchGate Security Gate Analysis[/bold]",
                border_style=color,
                expand=True,
            )
        )

        # 2. Tabla de capas
        table = Table(title="Desglose por Capa de Análisis", border_style="dim", expand=True)
        table.add_column("Capa", style="bold cyan")
        table.add_column("Puntuación", justify="right")
        table.add_column("Peso", justify="right")
        table.add_column("Contribución", justify="right")
        table.add_column("Estado", justify="center")
        table.add_column("Justificación / Hallazgo Principal", style="italic")

        layer_labels: dict[str, str] = {
            "static": "Estática (Semgrep/YARA)",
            "dependencies": "Dependencias (OSV/Typosquat)",
            "reputation": "Reputación Autor",
            "semantic": "Semántica (LLM)",
        }

        for layer_name, layer_res in aggregated.layer_results.items():
            weight = aggregated.weights_used.get(layer_name, 0.0)
            contrib = round(layer_res.risk_score * weight, 1)
            display_name = layer_labels.get(layer_name, layer_name.capitalize())

            if layer_res.skipped:
                status_str = f"[dim]Omitida ({layer_res.skip_reason or 'Disabled'})[/dim]"
                score_str = "[dim]0[/dim]"
            else:
                status_str = "[bold green]Activa[/bold green]"
                if layer_res.risk_score >= 70:
                    score_str = f"[bold red]{layer_res.risk_score}[/bold red]"
                elif layer_res.risk_score >= 40:
                    score_str = f"[bold yellow]{layer_res.risk_score}[/bold yellow]"
                else:
                    score_str = f"[green]{layer_res.risk_score}[/green]"

            just_text = (
                layer_res.justification[:120] + "..."
                if len(layer_res.justification) > 120
                else layer_res.justification
            )
            table.add_row(
                display_name,
                score_str,
                f"{weight:.2f}",
                f"{contrib:.1f}",
                status_str,
                just_text,
            )

        console.print(table)

        # 3. Detalle semántico si existe
        semantic_res = aggregated.layer_results.get("semantic")
        if semantic_res and not semantic_res.skipped and semantic_res.justification:
            console.print(
                Panel(
                    semantic_res.justification,
                    title="[bold blue]Análisis de Intención Semántica (LLM)[/bold blue]",
                    border_style="blue",
                    expand=True,
                )
            )

        return string_io.getvalue()
    except Exception:  # noqa: BLE001
        return render_comment(aggregated)
