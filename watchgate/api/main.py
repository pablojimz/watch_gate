"""Servidor principal FastAPI para Engine API de WatchGate."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from watchgate.api.routers import agent, analyze, webhooks
from watchgate.db.connection import init_db
from watchgate.logging_config import configure_logging

# Límite máximo de payload HTTP: 10 MB
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024

_SECRET_PATTERNS = [
    re.compile(r"wg_live_[a-f0-9]{64}"),
    re.compile(r"wg_test_[a-f0-9]{64}"),
    re.compile(r"wg_live_[a-zA-Z0-9_-]{16,}"),
    re.compile(r"wg_test_[a-zA-Z0-9_-]{16,}"),
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{30,}"),
    re.compile(r"sk-[a-zA-Z0-9_-]{32,}"),
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ciclo de vida del servidor: base de datos (logging y sanitizador
    de secretos ya se configuraron a nivel de módulo, antes de construir
    `app` más abajo -- si se hiciera aquí dentro, el "Waiting for
    application startup"/primeras líneas de uvicorn saldrían sin el
    formato elegido, porque uvicorn ya las loguea antes de entrar en el
    lifespan de la propia app)."""
    init_db()
    yield


# A nivel de módulo, antes de construir `app` -- ver docstring de
# `lifespan()`. `configure_logging()` antes que `setup_logging_sanitizer()`
# a propósito: esta última añade el filtro de redacción de secretos tanto
# al logger raíz como a cada handler que exista *en ese momento*
# (`root_logger.handlers`) -- si se llamara al revés, el handler nuevo de
# `configure_logging()` no tendría el filtro añadido directamente (el
# filtro del logger raíz lo cubre igual, pero mejor no depender de esa
# sutileza de `logging`).
configure_logging("engine-api")
setup_logging_sanitizer()

app = FastAPI(
    title="WatchGate Engine API",
    description="Motor de análisis e inferencia de seguridad para Pull Requests SaaS",
    version="1.0.0",
    lifespan=lifespan,
)


_RATE_LIMIT_WINDOW_SECONDS = 60.0
_MAX_REQUESTS_PER_WINDOW = 60
_request_timestamps: dict[str, list[float]] = {}
_rate_limit_lock = threading.Lock()


@app.middleware("http")
async def rate_limiting_middleware(
    request: Request, call_next: Callable[[Request], Any]
) -> Response:
    """Middleware de rate limiting por ventana deslizante (máx 60 req/min)."""
    if request.url.path.startswith("/api/v1/"):
        client_ip = request.client.host if request.client else "unknown"
        raw_key = (
            request.headers.get("X-API-Key") or request.headers.get("Authorization") or client_ip
        )
        client_key = f"{client_ip}:{raw_key[:16]}"

        now = time.time()
        with _rate_limit_lock:
            history = _request_timestamps.setdefault(client_key, [])
            _request_timestamps[client_key] = [
                t for t in history if now - t < _RATE_LIMIT_WINDOW_SECONDS
            ]
            if len(_request_timestamps[client_key]) >= _MAX_REQUESTS_PER_WINDOW:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": (
                            f"Límite de tasa excedido (máximo {_MAX_REQUESTS_PER_WINDOW} "
                            "peticiones/minuto)."
                        )
                    },
                    headers={"Retry-After": "60"},
                )
            _request_timestamps[client_key].append(now)

    response: Response = await call_next(request)
    return response


@app.middleware("http")
async def max_payload_size_middleware(
    request: Request, call_next: Callable[[Request], Any]
) -> Response:
    """Middleware que limita el tamaño máximo de las peticiones HTTP a 10 MB."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length_val = int(content_length)
            if length_val > MAX_PAYLOAD_BYTES:
                msg = f"El tamaño excede el límite permitido ({MAX_PAYLOAD_BYTES} bytes / 10 MB)."
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": msg},
                )
        except ValueError:
            pass

    response: Response = await call_next(request)
    return response


app.include_router(agent.router)
app.include_router(analyze.router)
app.include_router(webhooks.router)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Endpoint de comprobación de estado del servicio."""
    return {"status": "ok", "service": "WatchGate Engine API"}
