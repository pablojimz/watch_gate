# PYTHON_ARGCOMPLETE_OK
"""Entrypoint de la CLI de WatchGate (watchgate analyze / watchgate rag reindex).

Ver docs/planificacion/mejoras_cli.md y docs/WatchGate_spec_implementacion_IA.md §9, §12.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import argcomplete

import watchgate.core.layers  # noqa: F401 - registrar capas en LAYER_REGISTRY
from watchgate.config import apply_cli_overrides, load_config
from watchgate.core.comment_template import render_comment
from watchgate.core.diffparser import parse_diff, parse_diff_from_text
from watchgate.core.models import CommitAuthor, Semaforo
from watchgate.core.pipeline import run_full_analysis
from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH, build_index
from watchgate.formatters.console import render_console
from watchgate.formatters.github import render_github_annotations
from watchgate.formatters.sarif import render_sarif

logger = logging.getLogger("watchgate.cli")

MAX_STDIN_BYTES = 10 * 1024 * 1024  # Rule 2: Límite máximo de 10 MB para stdin


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watchgate",
        description="WatchGate: Sistema de scoring de riesgo para pull requests en CI/CD.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcomandos disponibles")

    # Command: analyze
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analiza un diff de PR entre dos commits o por stdin"
    )
    analyze_parser.add_argument(
        "--base",
        default="main",
        help="SHA o ref del commit base (o '-' para stdin)",
    )
    analyze_parser.add_argument(
        "--head",
        default="HEAD",
        help="SHA o ref del commit head (default: HEAD)",
    )
    analyze_parser.add_argument(
        "--diff-stdin",
        action="store_true",
        help="Lee el parche unificado directamente desde sys.stdin (pipeline Unix)",
    )
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
        choices=["comment", "json", "sarif"],
        default="comment",
        help="Formato de salida: 'comment' (markdown/rich), 'json' o 'sarif' (default: comment)",
    )
    analyze_parser.add_argument(
        "--github-annotations",
        action="store_true",
        help="Emite comandos de flujo de trabajo de GitHub Actions (::error:: / ::warning::)",
    )
    analyze_parser.add_argument(
        "--author-login", default="", help="Login del autor del PR en GitHub/GitLab"
    )
    analyze_parser.add_argument(
        "--author-email", default="", help="Email del autor del commit"
    )
    analyze_parser.add_argument(
        "--weight",
        action="append",
        help="Override dinámico de peso de capa (ej: --weight static=0.35)",
    )
    analyze_parser.add_argument(
        "--threshold",
        action="append",
        help="Override dinámico de umbral (ej: --threshold red=80)",
    )
    analyze_parser.add_argument(
        "--output", default="", help="Archivo opcional para guardar el resultado"
    )

    # Diagnóstico / Logs
    analyze_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Activa logs detallados (INFO)"
    )
    analyze_parser.add_argument(
        "--debug", action="store_true", help="Activa logs de diagnóstico completos (DEBUG)"
    )
    analyze_parser.add_argument(
        "-q", "--quiet", action="store_true", help="Silencia todo stderr excepto el informe final"
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

    argcomplete.autocomplete(parser)
    return parser


def _setup_logging(args: argparse.Namespace) -> None:
    if args.quiet:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr, force=True)
    elif args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
            force=True,
        )
    elif args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="[WatchGate] %(message)s",
            stream=sys.stderr,
            force=True,
        )
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr, force=True)


def _cmd_analyze(args: argparse.Namespace) -> int:
    _setup_logging(args)

    # 1. Cargar configuración con overrides
    try:
        config = load_config(args.config)
        config = apply_cli_overrides(
            config, weight_overrides=args.weight, threshold_overrides=args.threshold
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Fallo cargando/aplicando configuración", exc_info=True)
        if not args.quiet:
            msg = f"[Error de Configuración] No se pudo cargar/aplicar config: {exc}"
            print(msg, file=sys.stderr)
        return 2

    # 2. Ingesta del Diff (stdin vs. Git local)
    use_stdin = args.diff_stdin or args.base == "-"
    if use_stdin:
        # Rule 2: Verificación de TTY e ingesta segura de stdin
        if sys.stdin.isatty():
            if not args.quiet:
                msg = (
                    "[Error Ingesta] Se activó --diff-stdin pero no hay datos "
                    "canalizados en stdin."
                )
                print(msg, file=sys.stderr)
            return 2

        try:
            diff_text = sys.stdin.read(MAX_STDIN_BYTES + 1)
            if len(diff_text) > MAX_STDIN_BYTES:
                if not args.quiet:
                    msg = (
                        f"[Error Ingesta] El parche por stdin excede el límite de 10 MB "
                        f"({MAX_STDIN_BYTES} bytes)."
                    )
                    print(msg, file=sys.stderr)
                return 2
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fallo leyendo stdin", exc_info=True)
            if not args.quiet:
                msg = f"[Error Ingesta] No se pudo leer la entrada estándar: {exc}"
                print(msg, file=sys.stderr)
            return 2

        author = CommitAuthor(
            name=args.author_login or "stdin-user",
            email=args.author_email or "stdin@watchgate.local",
            login=args.author_login or "stdin-user",
        )
        try:
            diff = parse_diff_from_text(diff_text, authors=[author])
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fallo parseando el diff de stdin", exc_info=True)
            if not args.quiet:
                msg = f"[Error de Parseo] Sintaxis de diff no válida en stdin: {exc}"
                print(msg, file=sys.stderr)
            return 2
    else:
        try:
            diff = parse_diff(args.repo_path, args.base, args.head)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fallo extrayendo el diff con git", exc_info=True)
            if not args.quiet:
                msg = f"[Error de Git] No se pudo extraer el diff de '{args.repo_path}': {exc}"
                print(msg, file=sys.stderr)
            return 2

    metadata: dict[str, object] = {
        "pr_id": args.pr_id,
        "repo": args.repo or (args.repo_path if not use_stdin else "local/stdin"),
        "author_login": args.author_login,
    }

    # 3. Ejecución del pipeline
    try:
        aggregated = run_full_analysis(diff, metadata, config)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Fallo en el pipeline de análisis", exc_info=True)
        if not args.quiet:
            print(f"[Error de Ejecución] Fallo en el pipeline de análisis: {exc}", file=sys.stderr)
        return 3

    # 4. Formateo de salida principal
    if args.format == "json":
        output_text = aggregated.model_dump_json(indent=2)
    elif args.format == "sarif":
        output_text = render_sarif(aggregated)
    else:
        # Formato 'comment'
        if sys.stdout.isatty() and not args.output:
            output_text = render_console(aggregated)
        else:
            output_text = render_comment(aggregated)

    print(output_text)

    # 5. Anotaciones de GitHub Actions (Rule 1: Aislamiento a stderr si format == json/sarif)
    if args.github_annotations:
        target_stream = sys.stderr if args.format in ("json", "sarif") else sys.stdout
        render_github_annotations(aggregated, stream=target_stream)

    # 6. Guardado en archivo opcional
    if args.output:
        try:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fallo escribiendo el archivo de salida", exc_info=True)
            if not args.quiet:
                msg = f"[Error de Escritura] No se pudo guardar en '{args.output}': {exc}"
                print(msg, file=sys.stderr)

    # 7. Exit Codes estandarizados
    if config.block_on_red and aggregated.semaforo == Semaforo.ROJO:
        return 1
    return 0


def _cmd_rag_reindex(args: argparse.Namespace) -> int:
    try:
        index_path = args.index_path
        count = build_index(index_path=index_path)
        print(f"[WatchGate] Indexados {count} fragmentos en {index_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[Error RAG] No se pudo reindexar el corpus: {exc}", file=sys.stderr)
        return 3


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "analyze":
        return _cmd_analyze(args)
    if args.subcommand == "rag":
        if args.rag_subcommand == "reindex":
            return _cmd_rag_reindex(args)
        parser.parse_args(["rag", "--help"])
        return 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
