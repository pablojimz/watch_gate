"""Smoke test manual de Línea 2 (reputación + semántica), sin Línea 1.

No es el orquestador real ni sustituye a cost_control.py -- eso es trabajo de
Pablo Ayllón (núcleo). Esto es solo lo mínimo para poder lanzar
`ReputationLayer` + `SemanticLayer` de verdad contra un repo git local y ver
un resultado, mientras el resto del sistema no existe todavía:

- `_ToyCostController`: presupuesto infinito, caché en memoria, sin persistir
  nada a disco. Cumple `CostControllerLike` (Protocol estructural de
  `layer.py`), pero NO es una implementación real de §8 -- se descarta al
  terminar el proceso.
- `_parse_git_diff_to_normalized_diff`: parseo crudo de `git diff` en
  `NormalizedDiff`, no un adaptador de plataforma de verdad (eso vive en
  `watchgate/adapters/`, tampoco construido aún). No resuelve renames con
  similitud de contenido, ni metadata de reputación real (para eso hace
  falta la API de la plataforma, no solo git local) -- la reputación se pasa
  aparte, con valores de ejemplo si no se indica un JSON real.

Cada ejecución (salvo con --no-log) añade una línea a un fichero JSONL
(.watchgate/semantic_layer_log.jsonl por defecto, gitignored) con el diff
probado y la respuesta completa del LLM -- un registro persistente de qué se
probó y qué contestó, para poder revisarlo sin repetir la llamada.

Uso:
    poetry run python scripts/smoke_test_linea2.py --repo /ruta/al/repo \\
        [--base HEAD~1] [--head HEAD] [--reputation reputation.json] \\
        [--label "nombre-del-caso"] [--log-path ruta.jsonl] [--no-log]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# El repo vive en ~/Desktop (iCloud), que a veces marca los .pth del venv
# como "hidden" (flag de BSD) tras el editable install; Python 3.11+ los
# ignora sin avisar y `watchgate` deja de ser importable fuera de pytest
# (que sí tiene pythonpath=["."] en pyproject.toml). Este script se ejecuta
# suelto con `python scripts/...`, así que se asegura su propio sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchgate.core.layers._semantic.client import SemanticOutput  # noqa: E402
from watchgate.core.layers._semantic.layer import SemanticLayer  # noqa: E402
from watchgate.core.layers._semantic.llm_factory import build_llm_client  # noqa: E402
from watchgate.core.layers.reputation_layer import ReputationLayer  # noqa: E402
from watchgate.core.models import (  # noqa: E402
    FileChange,
    FileStatus,
    LayerResult,
    NormalizedDiff,
    ReputationMetadata,
)
from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH  # noqa: E402

_DIFF_GIT_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")

_DEFAULT_REPUTATION = ReputationMetadata(
    author_login="ejemplo-autor",
    author_account_age_days=400,
    author_prior_contributions_to_repo=12,
    commit_email_matches_verified_email=True,
    commit_is_signed=False,
    signing_key_seen_before_for_login=None,
    repo_has_history_of_signed_commits=False,
)


class _ToyCostController:
    """Cumple CostControllerLike; presupuesto infinito, sin persistencia.
    Solo para este script -- NO es cost_control.py (Línea 1, §8)."""

    def __init__(self) -> None:
        self._cache: dict[str, SemanticOutput] = {}

    def budget_remaining(self, repo: str) -> int:
        return 10_000_000

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())

    def get_cached(self, diff_hash: str) -> SemanticOutput | None:
        return self._cache.get(diff_hash)

    def store_cached(self, diff_hash: str, output: SemanticOutput) -> None:
        self._cache[diff_hash] = output

    def record_usage(self, repo: str, tokens_used: int) -> None:
        pass


def _status_from_block(header_lines: list[str]) -> tuple[FileStatus, str | None]:
    joined = "\n".join(header_lines)
    if "new file mode" in joined:
        return FileStatus.ADDED, None
    if "deleted file mode" in joined:
        return FileStatus.DELETED, None
    rename_from = re.search(r"^rename from (.+)$", joined, re.MULTILINE)
    if rename_from:
        return FileStatus.RENAMED, rename_from.group(1)
    return FileStatus.MODIFIED, None


def _is_binary_block(header_lines: list[str]) -> bool:
    return "Binary files" in "\n".join(header_lines)


def _parse_git_diff_to_normalized_diff(
    repo_path: str, base: str, head: str, commit_messages: list[str]
) -> NormalizedDiff:
    raw = subprocess.run(  # noqa: S603, S607
        ["git", "diff", "--unified=3", base, head],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    files: list[FileChange] = []
    blocks = re.split(r"(?=^diff --git )", raw, flags=re.MULTILINE)
    for block in blocks:
        if not block.strip():
            continue
        lines = block.splitlines()
        match = _DIFF_GIT_HEADER.match(lines[0])
        if not match:
            continue
        path = match.group(2)

        hunk_start = next((i for i, line in enumerate(lines) if line.startswith("@@")), None)
        header_lines = lines[1:hunk_start] if hunk_start is not None else lines[1:]
        hunk_lines = lines[hunk_start:] if hunk_start is not None else []
        status, old_path = _status_from_block(header_lines)
        is_binary = _is_binary_block(header_lines)

        additions = sum(
            1 for line in hunk_lines if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1 for line in hunk_lines if line.startswith("-") and not line.startswith("---")
        )

        files.append(
            FileChange(
                path=path,
                old_path=old_path,
                status=status,
                diff_hunk="\n".join(hunk_lines),
                additions=additions,
                deletions=deletions,
                is_binary=is_binary,
            )
        )

    return NormalizedDiff(
        base_sha=base,
        head_sha=head,
        repo_path=repo_path,
        files=files,
        commit_messages=commit_messages,
        authors=[],
    )


def _commit_messages(repo_path: str, base: str, head: str) -> list[str]:
    raw = subprocess.run(  # noqa: S603, S607
        ["git", "log", "--format=%s", f"{base}..{head}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in raw.splitlines() if line]


def _print_result(result: LayerResult) -> None:
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


_DEFAULT_LOG_PATH = ".watchgate/semantic_layer_log.jsonl"


def _client_info(llm_client: object) -> dict[str, str]:
    return {
        "client_class": type(llm_client).__name__,
        "model": str(getattr(llm_client, "_model", "?")),
    }


def _append_log_entry(
    log_path: Path,
    label: str | None,
    diff: NormalizedDiff,
    reputation_result: LayerResult,
    semantic_result: LayerResult,
    llm_client: object,
    rag_enabled: bool,
) -> None:
    """Registro persistente de qué dijo el LLM en cada prueba manual -- no es
    un log de producción (eso es Cloud Logging/§8, Línea 1), solo un rastro
    en disco para poder revisar después qué se probó y qué contestó."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "label": label,
        "repo": diff.repo_path,
        "base_sha": diff.base_sha,
        "head_sha": diff.head_sha,
        "files": [{"path": fc.path, "status": fc.status.value} for fc in diff.files],
        "llm": _client_info(llm_client),
        "rag_enabled": rag_enabled,
        "reputation_result": reputation_result.model_dump(mode="json"),
        "semantic_result": semantic_result.model_dump(mode="json"),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\n(registrado en {log_path})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Ruta a un repo git local")
    parser.add_argument("--base", default="HEAD~1")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--reputation",
        default=None,
        help="JSON con un ReputationMetadata; si se omite, usa valores de ejemplo",
    )
    parser.add_argument("--label", default=None, help="Etiqueta legible para el registro")
    parser.add_argument(
        "--log-path",
        default=_DEFAULT_LOG_PATH,
        help=f"Fichero JSONL donde registrar el resultado (por defecto {_DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--no-log", action="store_true", help="No registrar este resultado en el fichero JSONL"
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help=(
            "Desactiva el contexto RAG (apunta a un índice inexistente bajo un "
            "directorio temporal, retrieve_relevant_context devuelve []) -- para "
            "comparar qué aporta de verdad"
        ),
    )
    args = parser.parse_args()

    commit_messages = _commit_messages(args.repo, args.base, args.head)
    diff = _parse_git_diff_to_normalized_diff(args.repo, args.base, args.head, commit_messages)
    print(f"--- diff parseado: {len(diff.files)} fichero(s) ---")
    for fc in diff.files:
        print(f"  {fc.status.value:9s} {fc.path} (+{fc.additions}/-{fc.deletions})")

    reputation = _DEFAULT_REPUTATION
    if args.reputation:
        reputation = ReputationMetadata.model_validate(
            json.loads(Path(args.reputation).read_text())
        )

    metadata: dict[str, Any] = {"repo": "local/smoke-test", "reputation": reputation}

    print("\n--- ReputationLayer ---")
    reputation_result = ReputationLayer().analyze(diff, metadata)
    _print_result(reputation_result)

    print("\n--- SemanticLayer ---" + (" (sin RAG)" if args.no_rag else ""))
    llm_client = build_llm_client()
    if args.no_rag:
        rag_index_path = tempfile.mkdtemp(prefix="watchgate_no_rag_") + "/indice_inexistente"
    else:
        rag_index_path = DEFAULT_INDEX_PATH
    semantic = SemanticLayer(llm_client, _ToyCostController(), rag_index_path=rag_index_path)
    semantic_result = semantic.analyze(diff, metadata)
    _print_result(semantic_result)

    if not args.no_log:
        _append_log_entry(
            Path(args.log_path),
            args.label,
            diff,
            reputation_result,
            semantic_result,
            llm_client,
            rag_enabled=not args.no_rag,
        )


if __name__ == "__main__":
    main()
