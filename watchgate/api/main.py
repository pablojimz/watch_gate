"""Servidor principal FastAPI para Engine API de WatchGate."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from watchgate.api.routers import agent, analyze, webhooks
from watchgate.db.connection import init_db

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
                    k: self.redact(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.redact(arg) if isinstance(arg, str) else arg
                    for arg in record.args
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
    """Ciclo de vida del servidor: inicializa base de datos y sanitizador de logs."""
    setup_logging_sanitizer()
    init_db()
    yield


app = FastAPI(
    title="WatchGate Engine API",
    description="Motor de análisis e inferencia de seguridad para Pull Requests SaaS",
    version="1.0.0",
    lifespan=lifespan,
)


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
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
