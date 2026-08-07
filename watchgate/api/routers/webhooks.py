"""Router REST para recepción de Webhooks de GitHub App (POST /api/v1/webhooks/github)."""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


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


@router.post("/github")
async def handle_github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    """Procesa un webhook entrante desde GitHub App con verificación de firma HMAC-SHA256."""
    webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET") or os.environ.get(
        "WATCHGATE_GITHUB_WEBHOOK_SECRET"
    )

    body = await request.body()

    if webhook_secret:
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
            "event": x_github_event,
            "action": action,
            "repo": repo_name,
            "pr_id": pr_id,
        }

    return {
        "status": "ignored",
        "event": x_github_event,
        "action": action,
        "reason": "Evento no procesable por WatchGate Engine API",
    }
