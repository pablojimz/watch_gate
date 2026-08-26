"""Router REST para distribuir el hook `pre-receive` por HTTP
(GET /api/v1/hooks/pre-receive).

Sin esto, instalar el hook en un servidor Git REAL (no el Forgejo local de
`docker-compose.gitserver.yml`) exigía tener el repo `watch_gate` clonado
ahí solo para copiar un script -- con este endpoint es un `curl` directo
contra el Engine API ya desplegado. El fichero servido es el ÚNICO fuente
(`watchgate/adapters/git_hook/pre_receive_hook.sh`); no hay copia
duplicada en ningún otro sitio. Sin autenticación a propósito: el script
no contiene ningún secreto (la API key de cada repo se exporta aparte,
nunca hardcodeada aquí) -- exigir una clave para poder descargarlo
solo complicaría el único paso que se quería simplificar.
"""

from __future__ import annotations

import logging
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse

from watchgate.api.auth import require_scope
from watchgate.db.models import Organization, User, UserAPIKey

logger = logging.getLogger("watchgate.api.hooks")

router = APIRouter(prefix="/api/v1/hooks", tags=["Hooks"])

_HOOK_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "adapters" / "git_hook" / "pre_receive_hook.sh"
)

# Snapshot subido por `docker/git-server-hooks/upload_snapshot.sh` -- tope
# generoso (repo grande de verdad, no un mirror de juguete) pero no
# ilimitado: sin esto, un `.tar` mal formado o gigante podría colgar el
# proceso de extracción indefinidamente.
_MAX_SNAPSHOT_BYTES = 500 * 1024 * 1024


@router.get("/pre-receive", response_class=PlainTextResponse)
def get_pre_receive_hook() -> str:
    """Devuelve el script del hook `pre-receive` tal cual, listo para
    `curl -fsSL .../pre-receive -o hooks/pre-receive.d/watchgate`."""
    try:
        return _HOOK_SCRIPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El script del hook no está disponible en este despliegue.",
        ) from exc


def _extract_snapshot_files(raw: bytes) -> dict[str, str]:
    """`{path: contenido}` de un tarball (`git archive`, con o sin gzip) --
    ficheros binarios/no-UTF-8 se omiten en vez de fallar la extracción
    entera (mismo criterio que `GitHubClient.get_file_content`)."""
    files: dict[str, str] = {}
    with tarfile.open(fileobj=BytesIO(raw), mode="r:*") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            try:
                files[member.name] = extracted.read().decode("utf-8")
            except UnicodeDecodeError:
                continue
    return files


@router.post("/repo-snapshot", status_code=status.HTTP_202_ACCEPTED)
async def upload_repo_snapshot(
    snapshot: UploadFile,
    auth: Annotated[
        tuple[UserAPIKey, User, Organization], Depends(require_scope("analysis:write"))
    ],
) -> dict[str, str]:
    """Recibe un snapshot completo (`git archive`, tar/tar.gz) de un repo de
    servidor Git propio y construye su mapa de conocimiento -- ver
    `docker/git-server-hooks/upload_snapshot.sh` (quien lo sube, una vez al
    instalar el hook o cuando se quiera refrescar el mapa) y
    `core/repo_graph.py::index_repo_files` (el pipeline real, disparado vía
    `dashboard/backend/tasks.py::index_uploaded_repo_snapshot`).

    Misma autenticación que `POST /api/v1/analyze` -- la API key ya viene
    atada a un `MonitoredRepo` concreto al crearla (ver
    `connect_git_server_repo`), así que no hace falta que el cliente
    indique qué repo es aparte: lo dice la propia clave.

    202 inmediato + encolado en RQ (`dashboard-worker`, proceso aparte) --
    NO se procesa aquí mismo con `BackgroundTasks`: verificado en vivo que
    indexar un repo real (232 ficheros, resumen de LLM por cada uno) deja
    el proceso del Engine API sin capacidad de servir NADA más -- ni
    `/api/v1/analyze` ni su propio healthcheck -- mientras dura."""
    api_key, _user, _org = auth
    if api_key.monitored_repo_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta API key no está atada a ningún repositorio.",
        )

    raw = await snapshot.read()
    if len(raw) > _MAX_SNAPSHOT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Snapshot de {len(raw)} bytes supera el límite de {_MAX_SNAPSHOT_BYTES}.",
        )

    try:
        files = _extract_snapshot_files(raw)
    except tarfile.TarError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo leer el snapshot como tar: {exc}",
        ) from exc

    from watchgate.db.connection import get_session
    from watchgate.db.models import MonitoredRepo

    with next(get_session()) as session:
        repo = session.get(MonitoredRepo, api_key.monitored_repo_id)
        repo_path = repo.repo_path if repo else api_key.monitored_repo_id

    from watchgate.dashboard.backend.tasks import get_queue, index_uploaded_repo_snapshot

    job_id = f"repo-graph-{api_key.monitored_repo_id}"
    queue = get_queue()
    existing_job = queue.fetch_job(job_id)
    if existing_job is not None and not existing_job.is_failed:
        return {
            "status": "already_building",
            "repo_path": repo_path,
            "files_received": str(len(files)),
        }
    if existing_job is not None:
        existing_job.delete()
    queue.enqueue(
        index_uploaded_repo_snapshot,
        api_key.monitored_repo_id,
        repo_path,
        files,
        job_id=job_id,
        job_timeout="30m",
    )

    return {"status": "accepted", "repo_path": repo_path, "files_received": str(len(files))}
