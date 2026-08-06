"""Entrypoint de la CLI de WatchGate (watchgate analyze / watchgate rag reindex).

Ver docs/WatchGate_spec_implementacion_IA.md §9, §12.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import watchgate.core.layers  # noqa: F401 - registrar capas en LAYER_REGISTRY
from watchgate.config import load_config
from watchgate.core.comment_template import render_comment
from watchgate.core.diffparser import parse_diff
from watchgate.core.models import Semaforo
from watchgate.core.pipeline import run_full_analysis
from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH, build_index


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

    aggregated = run_full_analysis(diff, metadata, config)

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
