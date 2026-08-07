"""Entrypoint de la GitHub Action (spec §12, A.0.1).

Invocado como `python -m watchgate.adapters.github_action.main` desde
`.github/workflows/watchgate.yml`. A diferencia de `watchgate analyze` (CLI
genérica, sin conocimiento de ninguna plataforma concreta), este módulo sí
sabe hablar con GitHub: resuelve reputación real vía la API, publica el
comentario en el PR y marca el *check run* -- es la pieza que falta para que
un análisis calculado con `run_full_analysis` llegue de verdad a alguien.

Nunca imprime el valor de `GITHUB_TOKEN` ni `WATCHGATE_LLM_API_KEY` -- ambos
solo se leen de entorno y se pasan tal cual a las llamadas HTTP, jamás a
`print`/logging (test de seguridad obligatorio, spec §12: grep sobre los
logs de una ejecución no debe encontrar el valor literal de la API key).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import watchgate.core.layers  # noqa: F401 - registrar capas en LAYER_REGISTRY
from watchgate.adapters.github_action import dashboard_client, dashboard_settings_client
from watchgate.adapters.github_action.github_client import GitHubClient
from watchgate.config import load_config
from watchgate.core.comment_template import render_comment
from watchgate.core.diffparser import parse_diff
from watchgate.core.models import Semaforo
from watchgate.core.pipeline import run_full_analysis


def _load_pr_event(event_path: str) -> dict[str, Any]:
    with open(event_path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _extract_pr_context(pr_event: dict[str, Any]) -> tuple[str, str, int, str]:
    """`(owner, repo, pr_number, author_login)` del payload del evento."""
    owner = pr_event["repository"]["owner"]["login"]
    repo = pr_event["repository"]["name"]
    pr_number = pr_event["pull_request"]["number"]
    author_login = pr_event["pull_request"]["user"]["login"]
    return owner, repo, pr_number, author_login


def run(
    event_path: str,
    github_token: str,
    repo_path: str = ".",
    config_path: str = ".watchgate.yml",
) -> int:
    """Cuerpo real de la Action, aislado de `sys.exit`/variables de entorno
    para poder probarlo con valores inyectados en vez de un proceso real."""
    pr_event = _load_pr_event(event_path)
    owner, repo, pr_number, author_login = _extract_pr_context(pr_event)

    github_client = GitHubClient(token=github_token)
    base_sha, head_sha = github_client.get_pr_diff_shas(pr_event)

    # El repo ya está clonado por actions/checkout@v4 con fetch-depth: 0
    # (histórico completo, necesario para poder diffear base_sha..head_sha).
    diff = parse_diff(repo_path=repo_path, base_sha=base_sha, head_sha=head_sha)

    reputation_metadata = github_client.get_reputation_metadata(owner, repo, author_login)

    config = load_config(config_path)
    config = dashboard_settings_client.apply_dashboard_config(config, f"{owner}/{repo}")
    metadata: dict[str, object] = {
        "pr_id": str(pr_number),
        "repo": f"{owner}/{repo}",
        "author_login": author_login,
        "reputation": reputation_metadata,
    }

    result = run_full_analysis(diff, metadata, config)

    comment_body = render_comment(result)
    github_client.post_comment(owner, repo, pr_number, comment_body)

    is_blocking = result.semaforo == Semaforo.ROJO and config.block_on_red
    conclusion = "failure" if is_blocking else "neutral"
    github_client.post_check_run(owner, repo, head_sha, conclusion, comment_body)

    dashboard_client.post_score(result, author_login)

    print(f"WatchGate: {result.semaforo.value} ({result.score}/100) -- conclusion={conclusion}")

    return 1 if is_blocking else 0


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    github_token = os.environ.get("GITHUB_TOKEN")
    if not event_path:
        print("GITHUB_EVENT_PATH no está definida -- ¿se ejecuta fuera de GitHub Actions?")
        return 1
    if not github_token:
        print("GITHUB_TOKEN no está definida -- no se puede publicar el resultado en el PR.")
        return 1
    return run(event_path, github_token)


if __name__ == "__main__":
    sys.exit(main())
