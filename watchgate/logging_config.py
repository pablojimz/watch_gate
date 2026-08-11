"""logging_config.py — logging para los servicios de larga duración
(Engine API, Dashboard backend).

Deliberadamente NO toca la CLI (`watchgate/cli.py` tiene su propia
configuración en `_setup_logging()`, pensada para que la lea una persona
en una terminal -- texto plano, niveles por flag `-v`/`--debug`/`-q`) ni el
adaptador de GitHub Action (proceso corto, su salida son los prints del
propio adaptador). El público de este módulo son los dos servicios HTTP
que corren indefinidamente y cuyos logs se leen con `docker compose logs`
o un agregador real (Datadog/CloudWatch/lo que sea) -- ahí un log de una
sola línea de texto libre por evento es mucho más difícil de grepear/
filtrar/alertar que un objeto JSON con campos consistentes.

`WATCHGATE_LOG_FORMAT=json` (recomendado en producción/contenedores) |
`text` (por defecto -- más legible arrancando en local a mano).
`WATCHGATE_LOG_LEVEL` controla el nivel, `INFO` por defecto.
"""

from __future__ import annotations

import logging
import os
import sys

from pythonjsonlogger import jsonlogger

_UVICORN_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(service_name: str) -> None:
    """Configura el logger raíz (y los de uvicorn, que si no se tocan
    aparte siguen con su propio formato por defecto aunque el raíz ya esté
    en JSON) con un único handler a stdout -- stdout, no un fichero, para
    que en Docker `docker logs`/`docker compose logs` lo capture sin
    configuración adicional, el patrón estándar de contenedores."""
    level_name = os.environ.get("WATCHGATE_LOG_LEVEL", "INFO").upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
    log_format = os.environ.get("WATCHGATE_LOG_FORMAT", "text").lower()

    handler = logging.StreamHandler(sys.stdout)
    formatter: logging.Formatter
    if log_format == "json":
        # python-json-logger no publica anotaciones de tipos completas para
        # su __init__ -- ignore puntual, no del módulo entero.
        formatter = jsonlogger.JsonFormatter(  # type: ignore[no-untyped-call]
            "%(levelname)s %(name)s %(message)s",
            rename_fields={"levelname": "level", "name": "logger"},
            static_fields={"service": service_name},
            timestamp=True,
        )
    else:
        formatter = logging.Formatter(
            f"[%(asctime)s] [{service_name}] [%(levelname)s] %(name)s: %(message)s"
        )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for uvicorn_logger_name in _UVICORN_LOGGER_NAMES:
        uv_logger = logging.getLogger(uvicorn_logger_name)
        uv_logger.handlers = [handler]
        uv_logger.propagate = False
