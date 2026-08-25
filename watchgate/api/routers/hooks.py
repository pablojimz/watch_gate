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

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/v1/hooks", tags=["Hooks"])

_HOOK_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "adapters" / "git_hook" / "pre_receive_hook.sh"
)


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
