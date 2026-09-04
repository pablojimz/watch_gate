import hashlib
import hmac
import logging
import os
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from starlette.concurrency import run_in_threadpool

from watchgate.dashboard.backend.tasks import (
    ANALYSIS_JOB_TIMEOUT_SECONDS,
    get_queue,
    repo_is_authorized,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

logger = logging.getLogger("watchgate.webhooks")


def _webhook_secret() -> str | None:
    """Secreto del webhook de la GitHub App, leído POR PETICIÓN.

    Antes era un `_WEBHOOK_SECRET = os.environ.get(..., "")` a nivel de
    módulo, con dos problemas reales:

    - Fail-open: con la variable sin configurar, la firma se verificaba con
      clave VACÍA -- cualquiera puede calcular ese HMAC y mandar webhooks
      falsos que encolan `run_managed_scan` (consumiendo cuota LLM real).
      El endpoint equivalente de la Engine API (api/routers/webhooks.py)
      ya hacía fail-closed con 503; este es el mismo criterio.
    - Leído en import: cambiar la variable exigía reiniciar el proceso, y
      los tests tenían que monkeypatchear el atributo del módulo en vez del
      entorno.

    Acepta los dos nombres de variable, igual que la Engine API.
    """
    return os.environ.get("WATCHGATE_GITHUB_WEBHOOK_SECRET") or os.environ.get(
        "GITHUB_WEBHOOK_SECRET"
    )


def verify_signature(payload_body: bytes, secret_token: str | None, signature_header: str) -> None:
    if not secret_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El servidor no tiene configurado el secreto del webhook de GitHub "
                "(WATCHGATE_GITHUB_WEBHOOK_SECRET / GITHUB_WEBHOOK_SECRET) -- no se "
                "puede verificar la autenticidad del payload."
            ),
        )
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
    verify_signature(payload_body, _webhook_secret(), x_hub_signature_256 or "")

    # 2. Ignorar eventos que no nos importan (solo queremos pull_request opened o synchronize)
    if x_github_event != "pull_request":
        return Response(status_code=status.HTTP_200_OK)

    payload = await request.json()
    action = payload.get("action")
    if action not in ("opened", "synchronize"):
        return Response(status_code=status.HTTP_200_OK)

    # 3. Extraer info -- con .get() en cadena en vez de indexado directo: un
    # payload firmado pero malformado (p. ej. un redelivery editado a mano
    # desde la UI de GitHub) debe responder 400, no reventar con KeyError/500.
    repo_path = payload.get("repository", {}).get("full_name")
    pr_number = payload.get("pull_request", {}).get("number")
    if not repo_path or not isinstance(pr_number, int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload de pull_request sin repository.full_name o pull_request.number",
        )

    # El worker (run_managed_scan) resuelve org_id y vcs_connection_id a
    # partir del installation_id que GitHub incluye en el payload.
    installation_id = str(payload.get("installation", {}).get("id", ""))

    if not installation_id:
        return Response(status_code=status.HTTP_200_OK)

    # Rechazo real de "repos no autorizados", ANTES de encolar nada: sin
    # esto, cualquier repo al que la GitHub App tuviera acceso (decisión
    # del admin de GitHub al instalarla, no nuestra) se analizaba igual, y
    # pausar un repo desde el dashboard no tenía ningún efecto en este
    # camino -- ver el docstring de repo_is_authorized() en tasks.py.
    # session.exec() es bloqueante (SQLAlchemy síncrono), igual que el
    # queue.enqueue() de abajo -- mismo motivo para el run_in_threadpool.
    authorized, reason = await run_in_threadpool(repo_is_authorized, installation_id, repo_path)
    if not authorized:
        logger.warning(
            "Webhook rechazado para %s (installation_id=%s): %s",
            repo_path,
            installation_id,
            reason,
        )
        return Response(status_code=status.HTTP_403_FORBIDDEN)

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
        job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
    )

    return Response(status_code=status.HTTP_202_ACCEPTED)
