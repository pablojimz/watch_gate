"""main.py — app FastAPI del dashboard (spec §13 / A.4)."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import _dev_mode, _secret, ensure_safe_startup_config
from watchgate.dashboard.backend.auth import router as auth_router
from watchgate.dashboard.backend.auth_oidc import router as oidc_router
from watchgate.dashboard.backend.auth_oidc import setup_oidc
from watchgate.dashboard.backend.routers.feedback import router as feedback_router
from watchgate.dashboard.backend.routers.keys import router as keys_router
from watchgate.dashboard.backend.routers.llm_settings import router as llm_router
from watchgate.dashboard.backend.routers.metrics import router as metrics_router
from watchgate.dashboard.backend.routers.scores import router as scores_router
from watchgate.dashboard.backend.routers.ui_settings import router as ui_router
from watchgate.db.connection import init_db as init_api_keys_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    with database.db_session() as conn:
        database.init_db(conn)
        if os.environ.get("WATCHGATE_DASHBOARD_SEED", "1") == "1":
            database.seed_demo(conn)
    # Esquema aparte (SQLModel, watchgate/db/) que usa routers/keys.py --
    # sin esto, el propio arranque del dashboard nunca crea las tablas
    # users/user_api_keys y POST /api/keys falla con "no such table" en
    # cuanto se despliega de verdad (los tests de keys.py no lo detectan
    # porque sobreescriben get_db_session con un engine propio ya
    # inicializado).
    init_api_keys_db()
    setup_oidc()
    yield


def create_app() -> FastAPI:
    ensure_safe_startup_config()
    if _dev_mode():
        logger.warning(
            "WATCHGATE_DASHBOARD_DEV_MODE=1: login de desarrollo habilitado y "
            "secreto de sesión por defecto permitido si no se fija uno propio. "
            "No usar esta configuración en un despliegue real "
            "(WATCHGATE_DASHBOARD_DEV_MODE=0 + WATCHGATE_DASHBOARD_SECRET propio)."
        )

    app = FastAPI(title="WatchGate Dashboard", version="0.1.0", lifespan=lifespan)

    origins = [
        o.strip()
        for o in os.environ.get(
            "WATCHGATE_DASHBOARD_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Necesario para el flujo OIDC (state en sesión de Authlib). Mismo
    # secreto que las cookies de sesión propias (auth._secret) -- un único
    # sitio que puede fallar el arranque si es inseguro, ver
    # ensure_safe_startup_config().
    app.add_middleware(SessionMiddleware, secret_key=_secret())

    app.include_router(auth_router, prefix="/api")
    app.include_router(oidc_router, prefix="/api")
    app.include_router(scores_router, prefix="/api")
    app.include_router(keys_router, prefix="/api")
    app.include_router(feedback_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(llm_router, prefix="/api")
    app.include_router(ui_router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
