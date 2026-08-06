"""Wrapper fino sobre la API REST de GitHub (spec §12, A.0.1).

Cada método falla de forma controlada: un problema de red o una respuesta
inesperada de la API de GitHub nunca debe tirar abajo todo el análisis ni
inflar el `risk_score` por indisponibilidad del propio GitHub (mismo
criterio ya usado en `_semantic/tools.py` para OSV/VirusTotal). `post_comment`
y `post_check_run` son la excepción: si esas dos fallan, el resultado del
análisis nunca llega a nadie, así que si fallan, se propaga la excepción --
mejor un fallo ruidoso en el job de CI que un análisis silenciosamente
perdido.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from watchgate.core.models import ReputationMetadata

_API_BASE = "https://api.github.com"
_TIMEOUT = 15.0

# Cuántos commits recientes del repo se muestrean para decidir si el repo
# "tiene historial de commits firmados" -- no es viable (ni necesario) mirar
# el historial entero, un repo que firma commits lo hace de forma consistente
# reciente, no de forma esporádica.
_SIGNED_HISTORY_SAMPLE_SIZE = 20

_LINK_LAST_PAGE_RE = re.compile(r'[?&]page=(\d+)>;\s*rel="last"')


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        response = httpx.get(
            f"{_API_BASE}{path}", headers=self._headers, params=params, timeout=_TIMEOUT
        )
        response.raise_for_status()
        return response

    def get_pr_diff_shas(self, pr_event: dict[str, Any]) -> tuple[str, str]:
        """Extrae `(base_sha, head_sha)` del payload del evento `pull_request`
        (el JSON que GitHub Actions deja en `GITHUB_EVENT_PATH`)."""
        pr = pr_event["pull_request"]
        return pr["base"]["sha"], pr["head"]["sha"]

    def _commit_history_by_author(
        self, owner: str, repo: str, author_login: str
    ) -> tuple[int, dict[str, Any] | None]:
        """`(conteo_aproximado, commit_mas_reciente)` de `author_login` en la
        rama por defecto, en una sola llamada: con `per_page=1`, la propia
        respuesta ya trae el commit más reciente, y el número de la última
        página en la cabecera `Link` aproxima el conteo total (la API de
        GitHub no expone un conteo directo)."""
        response = self._get(
            f"/repos/{owner}/{repo}/commits", params={"author": author_login, "per_page": 1}
        )
        commits = response.json()
        latest = commits[0] if commits else None

        link_header = response.headers.get("Link", "")
        match = _LINK_LAST_PAGE_RE.search(link_header)
        count = int(match.group(1)) if match else len(commits)
        return count, latest

    def _repo_has_signed_commit_history(self, owner: str, repo: str) -> bool:
        response = self._get(
            f"/repos/{owner}/{repo}/commits", params={"per_page": _SIGNED_HISTORY_SAMPLE_SIZE}
        )
        commits = response.json()
        return any(
            c.get("commit", {}).get("verification", {}).get("verified") is True for c in commits
        )

    def get_reputation_metadata(
        self, owner: str, repo: str, author_login: str
    ) -> ReputationMetadata:
        """Construye `ReputationMetadata` (spec §6) a partir de señales
        reales de la API de GitHub. Cada sub-consulta se degrada a un valor
        neutral/conservador por su cuenta si falla -- una API caída no debe
        tirar abajo el resto del análisis, pero tampoco debe traducirse en
        "reputación intachable" por defecto (eso sería justo el fallo de
        seguridad contrario al que se quiere evitar).

        `signing_key_seen_before_for_login` siempre es `None`: sin el
        dashboard (§13, todavía no implementado) no hay dónde persistir qué
        claves se han visto antes para un usuario -- `None` es el valor que
        `ReputationMetadata` define explícitamente para "no aplica todavía".

        Las señales de firma/email verificado se leen del commit más
        reciente del autor en este repo (no hay un SHA de commit concreto en
        la firma de este método, fijada por la spec) -- una aproximación
        razonable de sus hábitos, no una verificación del commit exacto del
        PR (eso ya lo cubre `diffparser.py` con los autores reales del diff).
        """
        author_account_age_days: int | None = None
        try:
            user = self._get(f"/users/{author_login}").json()
            created_at = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
            author_account_age_days = (datetime.now(UTC) - created_at).days
        except (httpx.HTTPError, KeyError, ValueError):
            pass

        author_prior_contributions_to_repo = 0
        commit_email_matches_verified_email = False
        commit_is_signed = False
        try:
            count, latest = self._commit_history_by_author(owner, repo, author_login)
            author_prior_contributions_to_repo = count
            if latest is not None:
                commit_email_matches_verified_email = latest.get("author") is not None
                commit_is_signed = bool(
                    latest.get("commit", {}).get("verification", {}).get("verified")
                )
        except httpx.HTTPError:
            pass

        repo_has_history_of_signed_commits = False
        try:
            repo_has_history_of_signed_commits = self._repo_has_signed_commit_history(
                owner, repo
            )
        except httpx.HTTPError:
            pass

        return ReputationMetadata(
            author_login=author_login,
            author_account_age_days=author_account_age_days,
            author_prior_contributions_to_repo=author_prior_contributions_to_repo,
            commit_email_matches_verified_email=commit_email_matches_verified_email,
            commit_is_signed=commit_is_signed,
            signing_key_seen_before_for_login=None,
            repo_has_history_of_signed_commits=repo_has_history_of_signed_commits,
        )

    def post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        response = httpx.post(
            f"{_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=self._headers,
            json={"body": body},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()

    def post_check_run(
        self, owner: str, repo: str, sha: str, conclusion: str, summary: str
    ) -> None:
        response = httpx.post(
            f"{_API_BASE}/repos/{owner}/{repo}/check-runs",
            headers=self._headers,
            json={
                "name": "WatchGate",
                "head_sha": sha,
                "status": "completed",
                "conclusion": conclusion,
                "output": {"title": "WatchGate", "summary": summary},
            },
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
