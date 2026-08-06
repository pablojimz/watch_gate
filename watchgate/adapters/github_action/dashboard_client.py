"""Persistencia opcional del resultado en el dashboard (spec §12, paso 8).

El dashboard (§13) es infraestructura opcional: muchos usuarios de la Action
solo quieren el comentario en el PR, sin desplegar nada más. Por eso esta
llamada solo se hace si `WATCHGATE_DASHBOARD_URL` está configurada, y un
fallo aquí (dashboard caído, red, token incorrecto...) nunca debe tirar
abajo el job -- el análisis ya se completó y ya se publicó en el PR vía
`github_client.post_comment`/`post_check_run`, que son las llamadas que sí
deben propagar su fallo (ver docstring de ese módulo). Perder solo la
persistencia histórica es degradado, no crítico.
"""

from __future__ import annotations

import logging
import os

import httpx

from watchgate.core.models import AggregatedResult

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0


def post_score(result: AggregatedResult, author_login: str | None) -> None:
    base_url = os.environ.get("WATCHGATE_DASHBOARD_URL")
    if not base_url:
        return

    headers = {}
    token = os.environ.get("WATCHGATE_DASHBOARD_INGEST_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/api/scores",
            headers=headers,
            json={"result": result.model_dump(mode="json"), "author_login": author_login},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("No se pudo persistir el resultado en el dashboard: %s", exc)
