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
import re
import sys
from typing import TYPE_CHECKING

from pythonjsonlogger import jsonlogger

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

_UVICORN_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Antes solo vivía en watchgate/api/main.py (Engine API) -- el Dashboard
# backend nunca tuvo este filtro, pese a ser justo donde viven las
# credenciales VCS por usuario más recientes (PAT de GitHub personal,
# fallback de organización). Movido aquí para que ambos servicios lo
# compartan en vez de que uno se quede sin protección por descuido.
_SECRET_PATTERNS = [
    re.compile(r"wg_live_[a-f0-9]{64}"),
    re.compile(r"wg_test_[a-f0-9]{64}"),
    re.compile(r"wg_live_[a-zA-Z0-9_-]{16,}"),
    re.compile(r"wg_test_[a-zA-Z0-9_-]{16,}"),
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{30,}"),
    re.compile(r"sk-[a-zA-Z0-9_-]{32,}"),
    # PAT de GitHub (clásico y fine-grained) -- no cubiertos antes porque
    # el filtro original solo se pensó para las claves propias de
    # WatchGate/LLM, no para las credenciales VCS que llegaron después.
    re.compile(r"gh[pousr]_[a-zA-Z0-9]{36,}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{22,}"),
]


class CryptographicLogFilter(logging.Filter):
    """Filtro de logging que enmascara claves API y secretos antes de emitirlos."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self.redact(v) if isinstance(v, str) else v for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.redact(arg) if isinstance(arg, str) else arg for arg in record.args
                )
        return True

    @staticmethod
    def redact(text: str) -> str:
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub("[REDACTED_SECRET]", text)
        return text


def setup_logging_sanitizer() -> None:
    """Aplica el filtro de sanitización criptográfica a los loggers principales."""
    log_filter = CryptographicLogFilter()
    root_logger = logging.getLogger()
    root_logger.addFilter(log_filter)
    for handler in root_logger.handlers:
        handler.addFilter(log_filter)


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


def _scrub_sentry_event(event: Event, _hint: Hint) -> Event | None:
    """`before_send`: última línea de defensa antes de que un evento salga
    del proceso hacia Sentry -- redacta cualquier patrón de secreto conocido
    en el mensaje del evento y en cada valor de excepción (`event["exception"]
    ["values"][i]["value"]`, donde vive el `str(exc)` real). No sustituye al
    filtro de logging (`CryptographicLogFilter`, que ni siquiera llega a
    aplicarse aquí -- ver `configure_sentry`), es una capa aparte para lo que
    el SDK de Sentry genera por su cuenta (excepciones no capturadas vía
    `sys.excepthook`, que nunca pasan por el logger de Python)."""
    message = event.get("message")
    if isinstance(message, str):
        event["message"] = CryptographicLogFilter.redact(message)

    for exc_value in event.get("exception", {}).get("values", []):
        value = exc_value.get("value")
        if isinstance(value, str):
            exc_value["value"] = CryptographicLogFilter.redact(value)

    return event


def configure_sentry(service_name: str) -> None:
    """Alerting proactivo (Sentry) -- opt-in vía `WATCHGATE_SENTRY_DSN`, sin
    él esta función no hace nada (ni siquiera importa `sentry_sdk`, así que
    el paquete puede faltar en un entorno mínimo sin romper el arranque).

    Antes de esto, la única forma de enterarse de un fallo real en
    producción era ir a leer `docker compose logs` a mano -- documentado
    como limitación conocida en docs/despliegue.md.

    Configuración deliberadamente conservadora con los secretos que maneja
    este proyecto (tokens de GitHub, claves de LLM, credenciales de VCS):
    - `send_default_pii=False`: no manda IP/cookies/headers de request por
      defecto.
    - `include_local_variables=False`: por defecto sentry-sdk adjunta el
      valor de las variables locales de cada frame del traceback -- un
      `except Exception as e` con un `token`/`password` todavía en scope
      (frecuente en este código: cascada de credenciales, hashing de
      contraseñas) se colaría entero en el evento. Se desactiva del todo en
      vez de confiar en que cada excepción futura recuerde no exponer nada
      sensible en una variable local.
    - Integración de logging del SDK DESACTIVADA a propósito -- por defecto,
      sentry-sdk parchea `logging.Logger.callHandlers` para interceptar
      cada log record directamente en cuanto se genera, sin pasar por los
      handlers del logger raíz (que es donde vive `CryptographicLogFilter`,
      un filtro por-handler, no por-logger). Un log con un secreto sin
      redactar llegaría a Sentry sin pasar por ese filtro. `LoggingIntegration`
      tiene en realidad TRES sub-handlers independientes, los tres a `None`
      aquí a propósito (comprobado leyendo el código fuente del SDK, no
      solo la documentación -- `level`/`event_level=None` NO desactivaban
      el tercero): `level` (breadcrumbs), `event_level` (eventos) y
      `sentry_logs_level` (el producto "Sentry Logs", que se crea con nivel
      INFO por defecto incluso con los otros dos en `None`). Con los tres
      desactivados, Sentry solo captura excepciones no manejadas de verdad
      (vía sus integraciones de FastAPI/Starlette, que sí se mantienen
      activas) -- suficiente para "avisar si algo va mal", que es el
      objetivo real de esta función.
    - `before_send=_scrub_sentry_event`: red de seguridad adicional sobre
      lo que sí llega (mensajes de excepción), redactando los mismos
      patrones que ya usa el logging.
    """
    dsn = os.environ.get("WATCHGATE_SENTRY_DSN")
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("WATCHGATE_SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("WATCHGATE_SENTRY_RELEASE"),
        server_name=service_name,
        send_default_pii=False,
        include_local_variables=False,
        enable_logs=False,
        integrations=[LoggingIntegration(level=None, event_level=None, sentry_logs_level=None)],
        before_send=_scrub_sentry_event,
        traces_sample_rate=0.0,
    )
