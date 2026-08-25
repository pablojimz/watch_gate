"""Autenticación como GitHub App: JWT de App -> token de instalación.

Es la credencial correcta del modo "managed": cuando alguien instala la
GitHub App de WatchGate en su repositorio, la App puede pedir tokens de
acceso EFÍMEROS (1 hora) limitados a esa instalación concreta -- sin PATs
personales de por medio, sin que el dueño del repo comparta ninguna
credencial con WatchGate.

Flujo (documentado por GitHub):
1. Con el App ID y la clave privada PEM de la App (se descargan al
   registrar la App), se firma un JWT RS256 de vida corta (<= 10 min).
2. Ese JWT autentica `POST /app/installations/{id}/access_tokens`, que
   devuelve un token de instalación válido ~1 hora.
3. Ese token se usa como un token normal de la API de GitHub (leer diffs,
   comentar PRs) sobre los repos de ESA instalación, nada más.

Configuración (ver .env.example):
- `WATCHGATE_GITHUB_APP_ID`: el App ID numérico.
- `WATCHGATE_GITHUB_APP_PRIVATE_KEY`: el PEM completo (se aceptan `\\n`
  literales, habituales al meter un PEM en una variable de entorno), o
- `WATCHGATE_GITHUB_APP_PRIVATE_KEY_PATH`: ruta a un fichero .pem.

Sin estas variables, `github_app_configured()` es False y todo lo demás
degrada a la cascada de credenciales existente (PATs de usuario/org, ver
`resolve_github_credentials`) -- la App es el camino preferente, nunca un
requisito.

RS256 se firma con python-jose sobre el backend de `cryptography` -- ambas
ya son dependencias del proyecto (jose para las sesiones del dashboard,
cryptography para Fernet); cero dependencias nuevas.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
from jose import jwt

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_REQUEST_TIMEOUT_SECONDS = 15.0

# El JWT de App puede durar hasta 10 min; 9 deja margen de reloj. `iat` se
# atrasa 60s como recomienda GitHub (clock drift entre emisor y validador).
_APP_JWT_TTL_SECONDS = 540
_APP_JWT_IAT_DRIFT_SECONDS = 60

# Los tokens de instalación duran ~1h; se renuevan 5 min antes de expirar.
_TOKEN_REFRESH_MARGIN_SECONDS = 300.0

# Caché de PROCESO: installation_id -> (monotonic de expiración, token).
_installation_token_cache: dict[str, tuple[float, str]] = {}


def _app_id() -> str | None:
    return os.environ.get("WATCHGATE_GITHUB_APP_ID")


def _private_key() -> str | None:
    key = os.environ.get("WATCHGATE_GITHUB_APP_PRIVATE_KEY")
    if key:
        # Un PEM pegado en una variable de entorno suele llegar con los
        # saltos de línea escapados como '\n' literales.
        return key.replace("\\n", "\n")
    key_path = os.environ.get("WATCHGATE_GITHUB_APP_PRIVATE_KEY_PATH")
    if key_path:
        path = Path(key_path).expanduser()
        if path.is_file():
            return path.read_text(encoding="utf-8")
        logger.warning("WATCHGATE_GITHUB_APP_PRIVATE_KEY_PATH=%r no existe.", key_path)
    return None


def github_app_configured() -> bool:
    """True si hay App ID y clave privada configurados en el entorno."""
    return bool(_app_id() and _private_key())


def generate_app_jwt() -> str | None:
    """JWT RS256 de vida corta que identifica a la App (no a una
    instalación). `None` si la App no está configurada o la clave no firma."""
    app_id = _app_id()
    private_key = _private_key()
    if not app_id or not private_key:
        return None
    now = int(time.time())
    claims = {
        "iat": now - _APP_JWT_IAT_DRIFT_SECONDS,
        "exp": now + _APP_JWT_TTL_SECONDS,
        "iss": app_id,
    }
    try:
        # python-jose no tipa `jwt.encode` (devuelve `Any`) -- el `str()`
        # es solo para satisfacer a mypy, la librería ya devuelve un str.
        return str(jwt.encode(claims, private_key, algorithm="RS256"))
    except Exception as exc:  # noqa: BLE001 -- clave PEM malformada, etc.
        logger.error("No se pudo firmar el JWT de la GitHub App: %r", exc)
        return None


def get_installation_token(installation_id: str) -> str | None:
    """Token de acceso efímero para una instalación concreta, cacheado por
    proceso hasta ~5 min antes de su expiración. `None` (con log) ante
    cualquier fallo -- el llamador degrada a la cascada de PATs existente."""
    cached = _installation_token_cache.get(installation_id)
    if cached is not None and time.monotonic() < cached[0]:
        return cached[1]

    app_jwt = generate_app_jwt()
    if app_jwt is None:
        return None
    try:
        response = httpx.post(
            f"{_API_BASE}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "No se pudo obtener token de instalación de GitHub App para installation_id=%s: %r",
            installation_id,
            exc,
        )
        return None

    token = data.get("token")
    if not isinstance(token, str) or not token:
        logger.warning(
            "Respuesta sin 'token' al pedir el token de instalación %s.", installation_id
        )
        return None
    # GitHub devuelve `expires_at` ISO; usar el TTL nominal (1h) desde ahora
    # con margen es más simple y siempre igual o más conservador.
    _installation_token_cache[installation_id] = (
        time.monotonic() + 3600.0 - _TOKEN_REFRESH_MARGIN_SECONDS,
        token,
    )
    return token


def list_installation_repositories(installation_id: str) -> list[str]:
    """`full_name` (owner/repo) de todos los repos accesibles para la
    instalación, paginando. Lista vacía (con log) ante cualquier fallo --
    quien reclama la instalación puede añadir los repos a mano después."""
    token = get_installation_token(installation_id)
    if token is None:
        return []
    names: list[str] = []
    page = 1
    while True:
        try:
            response = httpx.get(
                f"{_API_BASE}/installation/repositories",
                params={"per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Fallo listando repos de la instalación %s (página %d): %r. "
                "Se devuelven los %d ya listados.",
                installation_id,
                page,
                exc,
                len(names),
            )
            break
        repositories = data.get("repositories") or []
        for repo in repositories:
            full_name = repo.get("full_name") if isinstance(repo, dict) else None
            if full_name:
                names.append(full_name)
        if len(repositories) < 100:
            break
        page += 1
    return names
