"""Entrypoint de la CLI de WatchGate (watchgate analyze / watchgate rag reindex).

Ver docs/WatchGate_spec_implementacion_IA.md §9, §12.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from watchgate.config import WatchGateConfig, load_config
from watchgate.core.aggregator import aggregate
from watchgate.core.comment_template import render_comment
from watchgate.core.cost_control import CostController
from watchgate.core.diffparser import parse_diff
from watchgate.core.layers._semantic.layer import SemanticLayer
from watchgate.core.layers._semantic.llm_factory import build_llm_client
from watchgate.core.models import LayerResult, Semaforo
from watchgate.core.orchestrator import LayerFactory, run_analysis
from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH, build_index
from watchgate.core.shortcircuit import evaluate_shortcircuit


class _ConfigWithoutSemantic:
    """Wrapper helper para calcular el score parcial sin la capa semántica."""

    def __init__(self, full_config: WatchGateConfig) -> None:
        self.weights = {k: v for k, v in full_config.weights.items() if k != "semantic"}
        self.thresholds = full_config.thresholds


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watchgate",
        description="WatchGate: Sistema de scoring de riesgo para pull requests en CI/CD.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcomandos disponibles")

    # Command: analyze
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analiza un diff de PR entre dos commits"
    )
    analyze_parser.add_argument("--base", required=True, help="SHA o ref del commit base")
    analyze_parser.add_argument("--head", required=True, help="SHA o ref del commit head")
    analyze_parser.add_argument(
        "--repo-path", default=".", help="Ruta al repositorio Git local (default: .)"
    )
    analyze_parser.add_argument(
        "--config",
        default=".watchgate.yml",
        help="Ruta al archivo .watchgate.yml (default: .watchgate.yml)",
    )
    analyze_parser.add_argument("--pr-id", default="", help="ID de la Pull Request")
    analyze_parser.add_argument("--repo", default="", help="Nombre del repositorio (ej: org/repo)")
    analyze_parser.add_argument(
        "--format",
        choices=["comment", "json"],
        default="comment",
        help="Formato de salida: 'comment' (markdown) o 'json' (default: comment)",
    )
    analyze_parser.add_argument(
        "--author-login", default="", help="Login del autor del PR en GitHub/GitLab"
    )
    analyze_parser.add_argument(
        "--output", default="", help="Archivo opcional para guardar el resultado"
    )

    # Command: rag
    rag_parser = subparsers.add_parser("rag", help="Gestión del sistema RAG")
    rag_subparsers = rag_parser.add_subparsers(dest="rag_subcommand", help="Subcomandos RAG")
    reindex_parser = rag_subparsers.add_parser(
        "reindex", help="Reindexa el corpus local de patrones de ataque en ChromaDB"
    )
    reindex_parser.add_argument(
        "--index-path",
        default=DEFAULT_INDEX_PATH,
        help=f"Ruta al índice ChromaDB (default: {DEFAULT_INDEX_PATH})",
    )

    return parser


def _cmd_analyze(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    diff = parse_diff(args.repo_path, args.base, args.head)

    metadata: dict[str, object] = {
        "pr_id": args.pr_id,
        "repo": args.repo,
        "author_login": args.author_login,
    }

    cost_control = None
    layer_factories: dict[str, LayerFactory] = {}

    if config.weights.get("semantic", 0) > 0:
        cost_control = CostController(
            db_path=".watchgate/cost.db",
            max_diff_tokens=config.max_diff_tokens,
            monthly_budget_tokens=config.monthly_budget_tokens,
        )
        try:
            llm_client = build_llm_client()
            layer_factories["semantic"] = lambda: SemanticLayer(llm_client, cost_control)
        except Exception:
            # Si falla el cliente LLM (ej. sin API key), safe_analyze lo aislará
            pass

    try:
        if config.shortcircuit_enabled:
            partial_cfg = _ConfigWithoutSemantic(config)
            partial_res = run_analysis(diff, metadata, partial_cfg)
            shortcircuit_verdict = evaluate_shortcircuit(
                partial_results=partial_res.layer_results,
                weights=config.weights,
                diff=diff,
                thresholds=config.thresholds,
            )
            if shortcircuit_verdict is not None:
                final_results = dict(partial_res.layer_results)
                final_results["semantic"] = LayerResult(
                    layer_name="semantic",
                    risk_score=0,
                    justification="",
                    skipped=True,
                    skip_reason="Cortocircuito de extremo aplicado",
                )
                aggregated = aggregate(
                    results=final_results,
                    weights=config.weights,
                    diff=diff,
                    pr_id=str(metadata["pr_id"]),
                    repo=str(metadata["repo"]),
                    thresholds=config.thresholds,
                )
            else:
                aggregated = run_analysis(diff, metadata, config, layer_factories=layer_factories)
        else:
            aggregated = run_analysis(diff, metadata, config, layer_factories=layer_factories)
    finally:
        if cost_control is not None:
            cost_control.close()

    if args.format == "json":
        output_text = aggregated.model_dump_json(indent=2)
    else:
        output_text = render_comment(aggregated)

    print(output_text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")

    if config.block_on_red and aggregated.semaforo == Semaforo.ROJO:
        return 1
    return 0


def _cmd_rag_reindex(args: argparse.Namespace) -> int:
    index_path = args.index_path
    count = build_index(index_path=index_path)
    print(f"[WatchGate] Indexados {count} fragmentos en {index_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "analyze":
        return _cmd_analyze(args)
    if args.subcommand == "rag":
        if args.rag_subcommand == "reindex":
            return _cmd_rag_reindex(args)
        parser.parse_args(["rag", "--help"])
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
