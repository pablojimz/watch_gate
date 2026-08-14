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
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from watchgate.core.models import ReputationMetadata

_API_BASE = "https://api.github.com"
_TIMEOUT = 15.0
_MAX_DIFF_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

# Cuántos commits recientes del repo se muestrean para decidir si el repo
# "tiene historial de commits firmados" -- no es viable (ni necesario) mirar
# el historial entero, un repo que firma commits lo hace de forma consistente
# reciente, no de forma esporádica.
_SIGNED_HISTORY_SAMPLE_SIZE = 20

_LINK_LAST_PAGE_RE = re.compile(r'[?&]page=(\d+)>;\s*rel="last"')


class DiffTooLargeError(Exception):
    """El diff descargado supera el límite de tamaño permitido."""


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Wrapper interno para peticiones con manejo de rate limits."""
        kwargs.setdefault("timeout", _TIMEOUT)
        kwargs.setdefault("headers", self._headers)

        max_retries = 3
        for attempt in range(max_retries):
            response = httpx.request(method, f"{_API_BASE}{path}", **kwargs)

            # Manejo de Rate Limit
            if response.status_code in (403, 429) and "x-ratelimit-remaining" in response.headers:
                if int(response.headers["x-ratelimit-remaining"]) == 0:
                    reset_time = int(response.headers.get("x-ratelimit-reset", time.time() + 60))
                    sleep_time = max(0, reset_time - int(time.time())) + 1
                    # No esperar más de 60 segundos por defecto para evitar asfixiar workers
                    if sleep_time <= 60 and attempt < max_retries - 1:
                        time.sleep(sleep_time)
                        continue

            # Manejo de 304 Not Modified para peticiones condicionales (ETag)
            if response.status_code == 304:
                return response

            response.raise_for_status()
            return response
        raise httpx.HTTPStatusError(
            "Max retries exceeded for rate limit", request=response.request, response=response
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        return self._request("GET", path, params=params)

    def get_pr_diff_shas(self, pr_event: dict[str, Any]) -> tuple[str, str]:
        """Extrae `(base_sha, head_sha)` del payload del evento `pull_request`
        (el JSON que GitHub Actions deja en `GITHUB_EVENT_PATH`)."""
        pr = pr_event["pull_request"]
        return pr["base"]["sha"], pr["head"]["sha"]

    def list_recent_pull_requests(
        self, owner: str, repo: str, per_page: int = 10
    ) -> list[dict[str, Any]]:
        """Devuelve las PRs abiertas más recientes de un repositorio."""
        params = {"state": "open", "sort": "created", "direction": "desc", "per_page": per_page}
        return list(self._get(f"/repos/{owner}/{repo}/pulls", params=params).json())

    def list_all_open_pull_requests(
        self, owner: str, repo: str, max_prs: int = 50
    ) -> list[dict[str, Any]]:
        """Devuelve todas las PRs abiertas de un repositorio paginando hasta `max_prs`."""
        all_prs: list[dict[str, Any]] = []
        page = 1
        per_page = min(50, max_prs)

        while len(all_prs) < max_prs:
            params = {
                "state": "open",
                "sort": "created",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            }
            try:
                response = self._get(f"/repos/{owner}/{repo}/pulls", params=params)
                prs = response.json()
                if not prs or not isinstance(prs, list):
                    break
                all_prs.extend(prs)
                if len(prs) < per_page:
                    break
                page += 1
            except httpx.HTTPError:
                break

        return all_prs[:max_prs]

    def list_recent_pull_requests_with_etag(
        self, owner: str, repo: str, per_page: int = 10, etag: str | None = None
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Consulta PRs abiertas enviando `If-None-Match: <etag>`.

        Retorna:
        - (None, etag_actual) si responde HTTP 304 Not Modified.
        - (lista_prs, nuevo_etag) si responde HTTP 200 OK.
        """
        headers = dict(self._headers)
        if etag:
            headers["If-None-Match"] = etag

        params = {"state": "open", "sort": "created", "direction": "desc", "per_page": per_page}
        response = self._request(
            "GET", f"/repos/{owner}/{repo}/pulls", params=params, headers=headers
        )

        if response.status_code == 304:
            return None, etag

        new_etag = response.headers.get("ETag")
        return list(response.json()), new_etag

    def _stream_diff(self, url: str, size_error_context: str) -> str:
        """Descarga un diff unificado en streaming desde `url`, aplicando
        el límite de _MAX_DIFF_SIZE_BYTES -- lógica compartida por
        `get_pull_request_diff` (diff de una PR) y `get_compare_diff`
        (diff entre dos refs cualesquiera, usado para el escaneo de rama
        completa, ver `get_default_branch_scan_data`). `size_error_context`
        es solo para el mensaje de `DiffTooLargeError` (p. ej. "la PR #42"
        o "la comparación <sha>...main")."""
        headers = {**self._headers, "Accept": "application/vnd.github.v3.diff"}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                diff_text = ""
                with httpx.stream("GET", url, headers=headers, timeout=_TIMEOUT) as response:
                    # Manejo de Rate Limit
                    if (
                        response.status_code in (403, 429)
                        and "x-ratelimit-remaining" in response.headers
                    ):
                        if int(response.headers["x-ratelimit-remaining"]) == 0:
                            reset_time = int(
                                response.headers.get("x-ratelimit-reset", time.time() + 60)
                            )
                            sleep_time = max(0, reset_time - int(time.time())) + 1
                            if sleep_time <= 60 and attempt < max_retries - 1:
                                time.sleep(sleep_time)
                                continue
                    response.raise_for_status()

                    downloaded = 0
                    for chunk in response.iter_text():
                        downloaded += len(chunk.encode("utf-8"))
                        if downloaded > _MAX_DIFF_SIZE_BYTES:
                            raise DiffTooLargeError(
                                f"El diff de {size_error_context} supera el límite de 2MB."
                            )
                        diff_text += chunk

                return diff_text
            except httpx.HTTPStatusError as exc:
                if attempt == max_retries - 1:
                    raise exc
        raise httpx.HTTPStatusError(
            "Max retries exceeded for rate limit",
            request=httpx.Request("GET", url),
            response=httpx.Response(429, request=httpx.Request("GET", url)),
        )

    def get_pull_request_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Descarga el diff unificado de una PR. Lanza DiffTooLargeError si > 2MB."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        return self._stream_diff(url, f"la PR #{pr_number}")

    def get_compare_diff(self, owner: str, repo: str, base: str, head: str) -> str:
        """Descarga el diff unificado entre `base` y `head` (dos refs/SHAs
        cualesquiera, no necesariamente relacionados por una PR) vía la
        Compare API de GitHub. Lanza DiffTooLargeError si > 2MB -- MISMO
        límite que un diff de PR, y en un repo grande es bastante más
        probable alcanzarlo aquí (ver `get_default_branch_scan_data`)."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/compare/{base}...{head}"
        return self._stream_diff(url, f"la comparación {base}...{head}")

    def get_pull_request_metadata(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Descarga los metadatos JSON (author, head, base, etc.) de una PR."""
        return dict(self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}").json())

    def get_pull_request_data(
        self, owner: str, repo: str, pr_number: int
    ) -> tuple[str, dict[str, Any]]:
        """Descarga el diff y los metadatos JSON de una PR."""
        metadata = self.get_pull_request_metadata(owner, repo, pr_number)
        diff_text = self.get_pull_request_diff(owner, repo, pr_number)
        return diff_text, metadata

    def get_repo_metadata(self, owner: str, repo: str) -> dict[str, Any]:
        """Metadatos del repositorio (incluye `default_branch`)."""
        return dict(self._get(f"/repos/{owner}/{repo}").json())

    def get_branch_head_commit(self, owner: str, repo: str, branch: str) -> dict[str, Any]:
        """Metadatos JSON del commit HEAD de `branch` (sha, autor, etc.)."""
        return dict(self._get(f"/repos/{owner}/{repo}/commits/{branch}").json())

    def get_root_commit_sha(self, owner: str, repo: str, branch: str) -> str | None:
        """SHA del primer commit (root, sin padre) del historial de
        `branch` -- usado como "base" real para diffear TODO el contenido
        actual del repo (ver `get_default_branch_scan_data`).

        Probado en vivo: la Compare API de GitHub NO admite el SHA mágico
        del árbol vacío de git (`4b825dc6...`, el truco que sí funciona con
        `git diff` en un checkout local) como base -- responde 404, porque
        ese objeto no existe de verdad en el almacén de GitHub para un repo
        concreto. El primer commit real sí es siempre un objeto válido.

        Misma técnica que `_commit_history_by_author`: pedir `per_page=1`
        trae en la propia cabecera `Link` el número de la última página, que
        equivale al total de commits -- pedir esa última página da el commit
        MÁS ANTIGUO sin tener que paginar el historial completo (coste fijo:
        2 peticiones, con independencia de cuántos commits tenga el repo)."""
        response = self._get(
            f"/repos/{owner}/{repo}/commits", params={"sha": branch, "per_page": 1}
        )
        commits = response.json()
        if not commits:
            return None

        link_header = response.headers.get("Link", "")
        match = _LINK_LAST_PAGE_RE.search(link_header)
        if not match:
            # Sin cabecera "last" -- un único commit en toda la rama, que
            # ya es el root.
            return commits[0].get("sha")

        last_page = int(match.group(1))
        last_response = self._get(
            f"/repos/{owner}/{repo}/commits",
            params={"sha": branch, "per_page": 1, "page": last_page},
        )
        last_commits = last_response.json()
        return last_commits[0].get("sha") if last_commits else commits[0].get("sha")

    def get_default_branch_scan_data(self, owner: str, repo: str) -> tuple[str, dict[str, Any]]:
        """Diff completo de la rama por defecto del repo (TODO su
        contenido actual, no solo una PR) + metadatos con la MISMA forma
        que `get_pull_request_data` (`{"user": {"login": ...}}`) para que
        encaje en el mismo pipeline de análisis sin cambios -- usado para
        el escaneo de línea base al dar de alta un repo en auditoría
        externa (ver `tasks.py:run_main_branch_scan`).

        El diff se obtiene comparando contra el PRIMER commit real del
        historial (`get_root_commit_sha`), no contra el árbol vacío de git
        -- ver esa docstring para el porqué. Si por lo que sea no se puede
        resolver el root (repo sin commits, fallo de red puntual), se cae a
        comparar la rama contra sí misma (`default_branch...default_branch`,
        diff vacío) -- una respuesta vacía es mejor que reventar el job de
        auditoría completo por esto.
        """
        repo_meta = self.get_repo_metadata(owner, repo)
        default_branch = repo_meta.get("default_branch") or "main"

        head_commit = self.get_branch_head_commit(owner, repo, default_branch)
        root_sha = self.get_root_commit_sha(owner, repo, default_branch) or default_branch
        diff_text = self.get_compare_diff(owner, repo, root_sha, default_branch)

        author = head_commit.get("author")
        author_login = author.get("login") if isinstance(author, dict) else None

        metadata = {
            "user": {"login": author_login or "unknown"},
            "head": {"sha": head_commit.get("sha", default_branch)},
            "default_branch": default_branch,
        }
        return diff_text, metadata

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
        self,
        owner: str,
        repo: str,
        author_login: str,
        pr_number: int | None = None,
        head_sha: str | None = None,
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
        """
        author_account_age_days: int | None = None
        author_public_repos: int | None = None
        author_followers: int | None = None
        try:
            user = self._get(f"/users/{author_login}").json()
            created_at = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
            author_account_age_days = (datetime.now(UTC) - created_at).days
            author_public_repos = user.get("public_repos")
            author_followers = user.get("followers")
        except (httpx.HTTPError, KeyError, ValueError):
            pass

        author_prior_contributions_to_repo = 0
        latest: dict[str, Any] | None = None
        try:
            count, latest = self._commit_history_by_author(owner, repo, author_login)
            author_prior_contributions_to_repo = count
        except httpx.HTTPError:
            pass

        pr_commit: dict[str, Any] | None = None
        if pr_number is not None:
            try:
                pr_commits = self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits").json()
                if pr_commits and isinstance(pr_commits, list):
                    pr_commit = pr_commits[-1]
            except httpx.HTTPError:
                pass
        elif head_sha:
            try:
                head_commit = self._get(f"/repos/{owner}/{repo}/commits/{head_sha}").json()
                if isinstance(head_commit, dict):
                    pr_commit = head_commit
            except httpx.HTTPError:
                pass

        if pr_commit is not None and isinstance(pr_commit, dict):
            commit_email_matches_verified_email = pr_commit.get("author") is not None
            commit_is_signed = bool(
                pr_commit.get("commit", {}).get("verification", {}).get("verified")
            )
        elif latest is not None:
            commit_email_matches_verified_email = latest.get("author") is not None
            commit_is_signed = bool(
                latest.get("commit", {}).get("verification", {}).get("verified")
            )
        else:
            commit_email_matches_verified_email = (
                True if author_account_age_days is not None else False
            )
            commit_is_signed = False

        repo_has_history_of_signed_commits = False
        try:
            repo_has_history_of_signed_commits = self._repo_has_signed_commit_history(owner, repo)
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
            author_public_repos=author_public_repos,
            author_followers=author_followers,
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
