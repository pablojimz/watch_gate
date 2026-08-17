"""auth.py — OAuth GitHub + cookie de sesión firmada + resolución de rol."""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError, jwe, jwt
from jose.exceptions import JOSEError

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.schemas import (
    DevLoginIn,
    PasswordLoginIn,
    RoleName,
    User,
    normalize_login,
)

SESSION_COOKIE = "watchgate_session"
ROLE_RANK: dict[RoleName, int] = {
    "revisor": 1,
    "mantenedor": 2,
    "admin_organizacion": 3,
}

# Único hardcodeado en todo el proyecto -- cualquiera que lea este fichero
# (o el repo público) conoce este valor, así que firmar tokens de sesión con
# él fuera de desarrollo local equivale a no tener autenticación. Ver
# `ensure_safe_startup_config`.
INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"

router = APIRouter(prefix="/auth", tags=["auth"])


def _secret() -> str:
    return os.environ.get("WATCHGATE_DASHBOARD_SECRET", INSECURE_DEFAULT_SECRET)


def _frontend_origin() -> str:
    return os.environ.get("WATCHGATE_DASHBOARD_FRONTEND_ORIGIN", "http://localhost:5173")


def _github_client_id() -> str | None:
    return os.environ.get("WATCHGATE_GITHUB_CLIENT_ID")


def _github_client_secret() -> str | None:
    return os.environ.get("WATCHGATE_GITHUB_CLIENT_SECRET")


def _dev_mode() -> bool:
    return os.environ.get("WATCHGATE_DASHBOARD_DEV_MODE", "1") == "1"


def _dev_login_enabled() -> bool:
    """Gate específico de `POST /api/auth/dev-login` (crear sesión con solo un
    usuario, sin contraseña), independiente de `_dev_mode()`.

    `_dev_mode()` también controla `ensure_safe_startup_config` (exige
    secreto largo + token de ingesta + cookie Secure en cuanto se apaga), que
    son cosas de "esto es un despliegue real detrás de TLS" -- no aplican
    necesariamente a un host sin reverse proxy HTTPS delante, donde forzar
    cookie Secure rompería todas las sesiones. Este flag deja cerrar solo el
    login sin contraseña sin arrastrar esas otras exigencias.
    """
    if os.environ.get("WATCHGATE_DASHBOARD_DISABLE_DEV_LOGIN", "0") == "1":
        return False
    return _dev_mode()


def _ingest_token() -> str | None:
    return os.environ.get("WATCHGATE_DASHBOARD_INGEST_TOKEN")


# Rate limiting de /api/auth/login -- en memoria de proceso por defecto
# (_LOGIN_ATTEMPTS), sin dependencias nuevas obligatorias. No había ningún
# límite de intentos: fuerza bruta sin bloqueo de cuenta, sin backoff.
#
# Limitación que tenía esto en memoria: no compartido entre
# workers/réplicas -- con un solo proceso protege de verdad, con varias
# réplicas detrás de un balanceador cada una lleva su propio contador. Si
# WATCHGATE_REDIS_URL está configurada, el conteo se mueve a Redis (un
# sorted set por login, score = timestamp, para la misma ventana
# deslizante que la versión en memoria -- ZREMRANGEBYSCORE poda lo que ya
# venció, ZCARD cuenta lo que queda, EXPIRE limpia claves de logins que ya
# no reintentan) y sí queda compartido entre réplicas. Sin esa variable,
# el comportamiento es exactamente el de antes -- no es un cambio rupturista.
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 300.0
_LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5


def _get_redis_client() -> Any | None:
    """`None` si `WATCHGATE_REDIS_URL` no está configurada (caso por
    defecto) -- sin caché a nivel de módulo a propósito: construir un
    `redis.Redis` es barato (conexión perezosa, no conecta aquí), y así
    los tests pueden monkeypatchear esta función directamente sin pelear
    con un singleton ya inicializado de una ejecución anterior."""
    redis_url = os.environ.get("WATCHGATE_REDIS_URL")
    if not redis_url:
        return None
    import redis as redis_module

    return redis_module.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)


def _redis_rate_limit_key(login: str) -> str:
    return f"watchgate:login-rate-limit:{normalize_login(login)}"


def _memory_count_recent_attempts(login: str) -> int:
    key = normalize_login(login)
    now = time.monotonic()
    recent = [t for t in _LOGIN_ATTEMPTS.get(key, []) if now - t < _LOGIN_RATE_LIMIT_WINDOW_SECONDS]
    if recent:
        _LOGIN_ATTEMPTS[key] = recent
    else:
        _LOGIN_ATTEMPTS.pop(key, None)
    return len(recent)


def _redis_count_recent_attempts(client: Any, login: str) -> int:
    key = _redis_rate_limit_key(login)
    now = time.time()
    client.zremrangebyscore(key, 0, now - _LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    count: int = client.zcard(key)
    return count


def _check_login_rate_limit(login: str) -> None:
    client = _get_redis_client()
    count = (
        _redis_count_recent_attempts(client, login)
        if client
        else _memory_count_recent_attempts(login)
    )
    if count >= _LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
        )


def _record_failed_login_attempt(login: str) -> None:
    client = _get_redis_client()
    if client:
        key = _redis_rate_limit_key(login)
        now = time.time()
        client.zadd(key, {str(now): now})
        client.expire(key, int(_LOGIN_RATE_LIMIT_WINDOW_SECONDS))
    else:
        _LOGIN_ATTEMPTS.setdefault(normalize_login(login), []).append(time.monotonic())


def _clear_login_attempts(login: str) -> None:
    client = _get_redis_client()
    if client:
        client.delete(_redis_rate_limit_key(login))
    else:
        _LOGIN_ATTEMPTS.pop(normalize_login(login), None)


def ensure_safe_startup_config() -> None:
    """Se niega a arrancar con una configuración insegura para producción.

    `WATCHGATE_DASHBOARD_DEV_MODE` vale "1" por defecto (comodidad en local:
    no hace falta configurar nada para levantar el dashboard). Pero eso
    significa que un despliegue real que se olvide de fijar las variables de
    entorno arrancaría en silencio con el login de desarrollo abierto,
    firmando cookies de sesión con `INSECURE_DEFAULT_SECRET` (público en este
    repo -- cualquiera podría forjar una sesión de admin_organizacion), y con
    `POST /api/scores` (la ingesta desde la Action, sin cookie de usuario)
    aceptando cualquier llamada sin autenticar. En cuanto alguien apaga dev
    mode explícitamente (la señal de "esto es un despliegue real"), exigimos
    que también se haya resuelto cada uno de esos puntos; si no, mejor que el
    proceso no arranque a que arranque con un agujero de autenticación.
    """
    if _dev_mode():
        return
    problems = []
    if _secret() == INSECURE_DEFAULT_SECRET:
        problems.append(
            "WATCHGATE_DASHBOARD_SECRET no está configurado (sigue en el valor "
            "por defecto inseguro)"
        )
    elif len(_secret()) < 32:
        # Solo se comprobaba el valor exacto por defecto -- un secreto
        # propio pero corto/débil (p. ej. "x") pasaba el check libremente.
        # 32 caracteres es un mínimo razonable para una clave HMAC-SHA256.
        problems.append(
            f"WATCHGATE_DASHBOARD_SECRET es demasiado corto ({len(_secret())} caracteres, "
            "mínimo 32) para firmar sesiones de forma segura"
        )
    if _ingest_token() is None:
        problems.append(
            "WATCHGATE_DASHBOARD_INGEST_TOKEN no está configurado "
            "(POST /api/scores quedaría sin autenticar)"
        )
    if os.environ.get("WATCHGATE_DASHBOARD_SECURE_COOKIE", "0") != "1":
        problems.append(
            "WATCHGATE_DASHBOARD_SECURE_COOKIE no está activado (la cookie de sesión, que "
            "puede llevar embebido un token de acceso de GitHub, viajaría sin el flag "
            "Secure)"
        )
    if problems:
        raise RuntimeError(
            "Configuración insegura para producción con "
            "WATCHGATE_DASHBOARD_DEV_MODE=0: " + "; ".join(problems) + "."
        )


def require_ingest_token(request: Request) -> None:
    """Autenticación de `POST /api/scores` (ingesta desde la Action).

    Ese endpoint lo llama un proceso de CI, no un usuario con cookie de
    sesión -- usa un bearer token compartido en vez del flujo de login
    humano. Si `WATCHGATE_DASHBOARD_INGEST_TOKEN` no está configurado el
    endpoint queda abierto (mismo criterio que dev mode: comodidad en local),
    pero `ensure_safe_startup_config` ya exige que esté fijado en cuanto se
    apaga dev mode, así que en producción esta rama siempre exige el token.
    """
    expected = _ingest_token()
    if expected is None:
        return
    provided = request.headers.get("Authorization", "")
    scheme, _, token = provided.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de ingesta inválido"
        )


def _encryption_key() -> bytes:
    """Deriva una clave AES-256 (32 bytes exactos) del secreto de sesión
    vía SHA-256 -- `_secret()` es una passphrase elegida por un humano, de
    longitud arbitraria (aunque ahora con un mínimo de 32 caracteres, ver
    `ensure_safe_startup_config`), no directamente material de clave
    criptográfico apto para AES-256-GCM. Reutiliza el mismo secreto que ya
    se configura para firmar (una sola variable de entorno que gestionar),
    con un hash aparte para no reusar literalmente los mismos bytes como
    clave de firma y de cifrado."""
    return hashlib.sha256(f"watchgate-session-encryption:{_secret()}".encode()).digest()


def create_session_token(login: str, github_token: str | None = None) -> str:
    # Único punto por el que pasan las cuatro vías de login (dev, local,
    # GitHub, OIDC) -- normalizar aquí garantiza que el `sub` de la cookie
    # de sesión (y por tanto CurrentUser.login en el resto del backend)
    # siempre sea la forma canónica, sin depender de que cada caller la
    # haya normalizado ya. Ver normalize_login() en schemas.py.
    payload: dict[str, object] = {
        "sub": normalize_login(login),
        "exp": datetime.now(UTC) + timedelta(days=7),
    }
    if github_token:
        payload["gh"] = github_token
    signed = jwt.encode(payload, _secret(), algorithm="HS256")
    # JWT anidado: firmar (integridad/expiración, como antes) y ENCIMA
    # cifrar (AES-256-GCM) el JWS resultante. Un JWT firmado pero no
    # cifrado es *legible* por cualquiera que tenga el valor de la cookie
    # -- no hace falta el secreto, solo decodificar base64 -- y este
    # payload puede llevar embebido un token de acceso de GitHub real
    # (scope `repo,read:org`) en `gh`. Cifrar cierra esa lectura sin tener
    # que mover la sesión a un almacén en servidor (cambio de arquitectura
    # mayor, fuera de alcance de este fix).
    encrypted = jwe.encrypt(signed, _encryption_key(), algorithm="dir", encryption="A256GCM")
    return str(encrypted.decode("ascii"))


def decode_session_token(token: str) -> dict[str, object]:
    decrypted = jwe.decrypt(token, _encryption_key())
    if decrypted is None:
        raise JWTError("No se pudo descifrar el token de sesión")
    res: dict[str, object] = jwt.decode(decrypted, _secret(), algorithms=["HS256"])
    return res


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("WATCHGATE_DASHBOARD_SECURE_COOKIE", "0") == "1",
        max_age=7 * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def get_current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    try:
        payload = decode_session_token(token)
    except JOSEError as exc:
        # `JOSEError` cubre tanto un JWS mal firmado/expirado (`JWTError`)
        # como un JWE que no descifra (`JWEError`) -- ambos son "sesión
        # inválida" desde el punto de vista de este endpoint.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida"
        ) from exc
    login = payload.get("sub")
    if not isinstance(login, str) or not login:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    return User(login=login)


CurrentUser = Annotated[User, Depends(get_current_user)]


def _github_token_from_request(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        payload = decode_session_token(token)
    except JOSEError:
        return None
    gh = payload.get("gh")
    return gh if isinstance(gh, str) else None


def resolve_role(user_login: str, repo: str, github_token: str | None = None) -> RoleName:
    """Resuelve el rol: fila en repo_roles, o inferencia desde GitHub Collaborators API."""
    with database.db_session() as conn:
        if database.user_is_org_admin(conn, user_login):
            return "admin_organizacion"
        existing = database.get_role(conn, user_login, repo)
        if existing is not None:
            return existing

    if github_token and "/" in repo:
        owner, name = repo.split("/", 1)
        permission = _fetch_github_permission(github_token, owner, name, user_login)
        mapped = _map_github_permission(permission) if permission is not None else None
        if mapped is not None:
            with database.db_session() as conn:
                database.upsert_role(conn, user_login, repo, mapped)
            return mapped

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Sin rol asignado en {repo}",
    )


def _map_github_permission(permission: str) -> RoleName | None:
    """Allowlist explícita, denegar por defecto -- no al revés.

    La API de Collaborators de GitHub puede devolver `"none"` (colaborador
    listado sin acceso efectivo) o valores nuevos que no existían cuando se
    escribió esto. Antes, cualquier valor que no fuera exactamente
    `admin`/`maintain`/`write` caía en `revisor` por defecto -- incluido
    `"none"` -- concediendo (y PERSISTIENDO vía `upsert_role`) acceso de
    lectura a alguien sin ningún permiso real en el repo. Ahora un valor no
    reconocido no concede nada: `resolve_role` sigue al 403 de "sin rol
    asignado" en vez de fabricar uno.
    """
    if permission in {"admin", "maintain", "write"}:
        return "mantenedor"
    if permission in {"read", "triage"}:
        return "revisor"
    return None


def _fetch_github_permission(token: str, owner: str, repo: str, user_login: str) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/collaborators/{user_login}/permission"
    try:
        response = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15.0,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    perm = data.get("permission")
    return perm if isinstance(perm, str) else None


def require_role(
    user: User,
    repo: str,
    min_role: RoleName,
    request: Request | None = None,
) -> RoleName:
    github_token = _github_token_from_request(request) if request is not None else None
    role = resolve_role(user.login, repo, github_token=github_token)
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Se requiere rol ≥ {min_role}",
        )
    return role


_OAUTH_STATE_COOKIE = "watchgate_oauth_state"


@router.get("/github/login")
def github_login(response: Response) -> Response:
    client_id = _github_client_id()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="WATCHGATE_GITHUB_CLIENT_ID no configurado",
        )
    redirect_uri = os.environ.get(
        "WATCHGATE_GITHUB_REDIRECT_URI",
        "http://localhost:8000/api/auth/github/callback",
    )
    # Protección CSRF del flujo OAuth: sin `state`, un atacante puede
    # iniciar el flujo con SU PROPIA cuenta de GitHub, capturar el `code`, y
    # hacer que la víctima visite el callback con ese código -- el navegador
    # de la víctima termina con una sesión de WatchGate vinculada a la
    # identidad GitHub del atacante (login CSRF). `state` aleatorio,
    # guardado en una cookie de corta vida propia (no en la sesión, que
    # todavía no existe en este punto del flujo) y comparado en el callback
    # con `secrets.compare_digest`, cierra esto -- mismo mecanismo que ya
    # usa el flujo OIDC vía `authlib`.
    state = secrets.token_urlsafe(32)
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("WATCHGATE_DASHBOARD_SECURE_COOKIE", "0") == "1",
        max_age=600,
        path="/api/auth/github",
    )
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={client_id}&scope=read:org,repo&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    response.status_code = status.HTTP_307_TEMPORARY_REDIRECT
    response.headers["Location"] = url
    return response


@router.get("/github/callback")
def github_callback(code: str, state: str, request: Request, response: Response) -> Response:
    client_id = _github_client_id()
    client_secret = _github_client_secret()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Credenciales GitHub OAuth no configuradas",
        )

    expected_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parámetro state inválido o ausente -- posible CSRF del flujo OAuth.",
        )
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/api/auth/github")

    token_resp = httpx.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        timeout=15.0,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No se obtuvo access_token de GitHub")

    user_resp = httpx.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15.0,
    )
    user_resp.raise_for_status()
    login = user_resp.json()["login"]

    session = create_session_token(login, github_token=access_token)
    set_session_cookie(response, session)
    response.status_code = status.HTTP_307_TEMPORARY_REDIRECT
    response.headers["Location"] = f"{_frontend_origin()}/repos"
    return response


@router.post("/login")
def password_login(body: PasswordLoginIn, response: Response) -> dict[str, str]:
    """Login local con usuario/contraseña (independiente de GitHub/GitLab)."""
    _check_login_rate_limit(body.username)
    with database.db_session() as conn:
        ok = database.authenticate_user(conn, body.username, body.password)
    if not ok:
        _record_failed_login_attempt(body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    _clear_login_attempts(body.username)
    token = create_session_token(body.username)
    set_session_cookie(response, token)
    return {"login": body.username}


@router.post("/dev-login")
def dev_login(body: DevLoginIn, response: Response) -> dict[str, str]:
    """Login de desarrollo (solo si WATCHGATE_DASHBOARD_DEV_MODE=1 y no se ha
    desactivado explícitamente con WATCHGATE_DASHBOARD_DISABLE_DEV_LOGIN=1)."""
    if not _dev_login_enabled():
        raise HTTPException(status_code=404, detail="Dev login deshabilitado")

    with database.db_session() as conn:
        # Asegura que el usuario de demo tenga al menos un rol visible.
        repos = database.list_repos_for_user(
            conn, body.login, is_admin=body.role == "admin_organizacion"
        )
        if not repos:
            database.upsert_role(conn, body.login, "acme/payments-api", body.role)
            if body.role == "admin_organizacion":
                database.upsert_role(conn, body.login, "acme/auth-service", body.role)
        elif body.role == "admin_organizacion":
            for repo in repos or ["acme/payments-api"]:
                database.upsert_role(conn, body.login, repo, body.role)
        else:
            database.upsert_role(conn, body.login, repos[0], body.role)

    token = create_session_token(body.login)
    set_session_cookie(response, token)
    return {"login": body.login, "role": body.role}


@router.get("/me")
def me(user: CurrentUser, request: Request) -> dict[str, object]:
    with database.db_session() as conn:
        is_admin = database.user_is_org_admin(conn, user.login)
        repos = database.list_repos_for_user(conn, user.login, is_admin=is_admin)
    return {"login": user.login, "is_admin": is_admin, "repos": repos}


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}
