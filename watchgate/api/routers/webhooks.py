"""Router REST para recepción de Webhooks de GitHub App (POST /api/v1/webhooks/github)."""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

logger = logging.getLogger("watchgate.api.webhooks")

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


def _require_webhook_secret(secret: str | None, provider: str, env_vars: str) -> str:
    """Exige que el secreto del webhook esté configurado -- fail CLOSED, no
    abierto.

    Antes, si la variable de entorno no estaba configurada, el endpoint
    simplemente no verificaba nada y aceptaba cualquier payload como
    legítimo (`if webhook_secret: verificar` / sin `else`). Un operador que
    desplegara sin fijar el secreto exponía el endpoint a cualquiera en
    internet, sin ningún aviso. Ahora la ausencia del secreto es en sí
    misma un error de configuración del servidor (503), no una via libre.
    """
    if not secret:
        logger.error(
            "Webhook de %s recibido pero ninguna de las variables de entorno %s está "
            "configurada -- el payload no se puede verificar. Rechazando (fail-closed).",
            provider,
            env_vars,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"El servidor no tiene configurado el secreto del webhook de {provider} "
                f"({env_vars}) -- no se puede verificar la autenticidad del payload."
            ),
        )
    return secret


def _verify_github_signature(
    payload_body: bytes, signature_header: str | None, secret: str
) -> bool:
    """Verifica la firma HMAC-SHA256 del webhook enviado por GitHub."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[7:]
    computed_signature = hmac.new(
        secret.encode("utf-8"), payload_body, digestmod="sha256"
    ).hexdigest()

    return hmac.compare_digest(computed_signature, expected_signature)


def _verify_gitlab_token(token_header: str | None, secret: str) -> bool:
    """Verifica el token de secreto enviado en la cabecera X-Gitlab-Token."""
    if not token_header or not secret:
        return False
    return hmac.compare_digest(token_header.strip(), secret.strip())


@router.post("/github")
async def handle_github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    """Procesa un webhook entrante desde GitHub App con verificación de firma HMAC-SHA256."""
    webhook_secret = _require_webhook_secret(
        os.environ.get("GITHUB_WEBHOOK_SECRET")
        or os.environ.get("WATCHGATE_GITHUB_WEBHOOK_SECRET"),
        provider="GitHub",
        env_vars="GITHUB_WEBHOOK_SECRET / WATCHGATE_GITHUB_WEBHOOK_SECRET",
    )

    body = await request.body()

    if not _verify_github_signature(body, x_hub_signature_256, webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma HMAC X-Hub-Signature-256 inválida o no coincidente.",
        )

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    action = payload.get("action", "unknown")

    if x_github_event == "pull_request":
        pr_data = payload.get("pull_request", {})
        pr_id = str(pr_data.get("number", payload.get("number", "")))
        repo_name = payload.get("repository", {}).get("full_name", "")

        return {
            "status": "accepted",
            "provider": "github",
            "event": x_github_event,
            "action": action,
            "repo": repo_name,
            "pr_id": pr_id,
        }

    return {
        "status": "ignored",
        "provider": "github",
        "event": x_github_event,
        "action": action,
        "reason": "Evento no procesable por WatchGate Engine API",
    }


@router.post("/gitlab")
async def handle_gitlab_webhook(
    request: Request,
    x_gitlab_event: str | None = Header(default=None, alias="X-Gitlab-Event"),
    x_gitlab_token: str | None = Header(default=None, alias="X-Gitlab-Token"),
) -> dict[str, Any]:
    """Procesa un webhook entrante desde GitLab con verificación de token de secreto."""
    webhook_secret = _require_webhook_secret(
        os.environ.get("GITLAB_WEBHOOK_SECRET")
        or os.environ.get("WATCHGATE_GITLAB_WEBHOOK_SECRET"),
        provider="GitLab",
        env_vars="GITLAB_WEBHOOK_SECRET / WATCHGATE_GITLAB_WEBHOOK_SECRET",
    )

    if not _verify_gitlab_token(x_gitlab_token, webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token X-Gitlab-Token inválido o no coincidente.",
        )

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    object_kind = payload.get("object_kind", "unknown")

    if x_gitlab_event == "Merge Request Hook" or object_kind == "merge_request":
        attrs = payload.get("object_attributes", {})
        mr_id = str(attrs.get("iid", payload.get("id", "")))
        repo_name = payload.get("project", {}).get("path_with_namespace", "")

        return {
            "status": "accepted",
            "provider": "gitlab",
            "event": x_gitlab_event or object_kind,
            "action": attrs.get("action", "open"),
            "repo": repo_name,
            "pr_id": mr_id,
        }

    return {
        "status": "ignored",
        "provider": "gitlab",
        "event": x_gitlab_event or object_kind,
        "reason": "Evento no procesable por WatchGate Engine API",
    }


@router.post("/bitbucket")
async def handle_bitbucket_webhook(
    request: Request,
    x_event_key: str | None = Header(default=None, alias="X-Event-Key"),
    x_hub_signature: str | None = Header(default=None, alias="X-Hub-Signature"),
) -> dict[str, Any]:
    """Procesa un webhook entrante desde Bitbucket con verificación de firma HMAC-SHA256."""
    webhook_secret = _require_webhook_secret(
        os.environ.get("BITBUCKET_WEBHOOK_SECRET")
        or os.environ.get("WATCHGATE_BITBUCKET_WEBHOOK_SECRET"),
        provider="Bitbucket",
        env_vars="BITBUCKET_WEBHOOK_SECRET / WATCHGATE_BITBUCKET_WEBHOOK_SECRET",
    )

    body = await request.body()

    if not _verify_github_signature(body, x_hub_signature, webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma HMAC X-Hub-Signature inválida o no coincidente.",
        )

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    if x_event_key and x_event_key.startswith("pullrequest:"):
        pr_data = payload.get("pullrequest", {})
        pr_id = str(pr_data.get("id", ""))
        repo_name = payload.get("repository", {}).get("full_name", "")

        return {
            "status": "accepted",
            "provider": "bitbucket",
            "event": x_event_key,
            "repo": repo_name,
            "pr_id": pr_id,
        }

    return {
        "status": "ignored",
        "provider": "bitbucket",
        "event": x_event_key,
        "reason": "Evento no procesable por WatchGate Engine API",
    }
