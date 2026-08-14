import hashlib
import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from starlette.concurrency import run_in_threadpool

from watchgate.dashboard.backend.tasks import get_queue

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# El secreto se configurará en la App de GitHub
_WEBHOOK_SECRET = os.environ.get("WATCHGATE_GITHUB_WEBHOOK_SECRET", "")


def verify_signature(payload_body: bytes, secret_token: str, signature_header: str) -> None:
    if not signature_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta firma")

    hash_object = hmac.new(secret_token.encode("utf-8"), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Firma inválida")


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
) -> Response:
    """Recibe webhooks de GitHub App (repositorios managed)."""

    # 1. Validar firma
    payload_body = await request.body()
    verify_signature(payload_body, _WEBHOOK_SECRET, x_hub_signature_256 or "")

    # 2. Ignorar eventos que no nos importan (solo queremos pull_request opened o synchronize)
    if x_github_event != "pull_request":
        return Response(status_code=status.HTTP_200_OK)

    payload = await request.json()
    action = payload.get("action")
    if action not in ("opened", "synchronize"):
        return Response(status_code=status.HTTP_200_OK)

    # 3. Extraer info
    repo_path = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]

    # TODO: Aquí deberíamos buscar el org_id y vcs_connection_id correspondientes
    # al installation_id del webhook. Como no se incluye en el payload directo sin
    # consultar base de datos, lo dejamos encolado o lo resolvemos en el worker.

    # Para la implementación actual del Worker, necesita el org_id y vcs_connection_id.
    # En un webhook real de GitHub App viene el `installation.id` en el payload.
    installation_id = str(payload.get("installation", {}).get("id", ""))

    if not installation_id:
        return Response(status_code=status.HTTP_200_OK)

    # El worker de managed mode no existe aún (run_audit_scan asume audited o similar,
    # pero requiere org_id explícito). Vamos a usar RQ para encolarlo a un worker especial
    # que resuelva todo desde el installation_id.
    # queue.enqueue() habla con Redis por un socket bloqueante (redis-py
    # estándar, no async) -- este endpoint SÍ es `async def` (lo exige
    # `await request.body()`/`request.json()` de arriba, para leer el
    # payload antes de verificar la firma), así que sin `run_in_threadpool`
    # esa llamada bloquea el event loop entero: mientras Redis responde,
    # ninguna otra petición concurrente al dashboard se procesa en este
    # proceso, no solo la del propio webhook.
    queue = get_queue()
    await run_in_threadpool(
        queue.enqueue,
        "watchgate.dashboard.backend.tasks.run_managed_scan",
        repo_path,
        pr_number,
        installation_id,
    )

    return Response(status_code=status.HTTP_202_ACCEPTED)
