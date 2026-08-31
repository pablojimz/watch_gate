"""main.py — app FastAPI del dashboard (spec §13 / A.4)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import _dev_mode, _secret, ensure_safe_startup_config
from watchgate.dashboard.backend.auth import router as auth_router
from watchgate.dashboard.backend.auth_oidc import router as oidc_router
from watchgate.dashboard.backend.auth_oidc import setup_oidc
from watchgate.dashboard.backend.routers.agent_access import router as agent_access_router
from watchgate.dashboard.backend.routers.feedback import router as feedback_router
from watchgate.dashboard.backend.routers.keys import router as keys_router
from watchgate.dashboard.backend.routers.llm_settings import router as llm_router
from watchgate.dashboard.backend.routers.metrics import router as metrics_router
from watchgate.dashboard.backend.routers.rag import router as rag_router
from watchgate.dashboard.backend.routers.repos import router as repos_router
from watchgate.dashboard.backend.routers.scores import router as scores_router
from watchgate.dashboard.backend.routers.ui_settings import router as ui_router
from watchgate.dashboard.backend.routers.user_settings import router as user_settings_router
from watchgate.dashboard.backend.routers.webhooks import router as webhooks_router
from watchgate.dashboard.backend.routers.yara_rules import router as yara_rules_router
from watchgate.db.connection import init_db as init_api_keys_db
from watchgate.logging_config import configure_logging, configure_sentry, setup_logging_sanitizer

logger = logging.getLogger(__name__)


def _rag_sync_interval_hours() -> float:
    """Cada cuántas horas se encola `run_rag_sync` (avisos de seguridad
    reales -> corpus RAG -> reindexado, en el worker). 24 por defecto;
    `WATCHGATE_RAG_SYNC_INTERVAL_HOURS=0` (o negativo) lo desactiva; un
    valor no numérico cae al default en vez de tumbar el arranque."""
    raw = os.environ.get("WATCHGATE_RAG_SYNC_INTERVAL_HOURS", "24")
    try:
        return float(raw)
    except ValueError:
        logger.warning("WATCHGATE_RAG_SYNC_INTERVAL_HOURS=%r no es un número; se usa 24.", raw)
        return 24.0


async def _rag_sync_loop(interval_hours: float) -> None:
    """Encola el RAG sync al arrancar y luego cada `interval_hours`.

    Solo ENCOLA (redis-py bloqueante -> run_in_threadpool); el trabajo real
    (descarga de avisos + embeddings + ChromaDB) corre en dashboard-worker,
    que es quien usa el índice en los análisis. La tarea es idempotente
    (mismo aviso -> mismo fichero, sin cambios -> sin reindexar), así que
    un reinicio del backend que vuelva a encolar de inmediato es barato."""
    from watchgate.dashboard.backend.tasks import get_queue

    while True:
        try:
            await run_in_threadpool(
                get_queue().enqueue, "watchgate.dashboard.backend.tasks.run_rag_sync"
            )
            logger.info("RAG sync encolado; el próximo se encolará en %.1f horas.", interval_hours)
        except Exception:  # noqa: BLE001 -- Redis caído no debe matar el loop
            logger.exception("No se pudo encolar el RAG sync periódico; se reintentará.")
        await asyncio.sleep(interval_hours * 3600)


def _score_retention_days() -> int:
    """Cuántos días se conserva el histórico de `pr_scores` antes de
    purgarse -- petición explícita: no acumular para siempre. 30 por
    defecto; `WATCHGATE_SCORE_RETENTION_DAYS=0` (o negativo) lo
    desactiva; un valor no numérico cae al default en vez de tumbar el
    arranque."""
    raw = os.environ.get("WATCHGATE_SCORE_RETENTION_DAYS", "30")
    try:
        return int(raw)
    except ValueError:
        logger.warning("WATCHGATE_SCORE_RETENTION_DAYS=%r no es un número; se usa 30.", raw)
        return 30


async def _score_retention_loop(retention_days: int) -> None:
    """Encola la purga de retención al arrancar y luego una vez al día --
    mismo patrón que `_rag_sync_loop` (solo encola, el borrado real corre
    en dashboard-worker vía `tasks.py::purge_old_scores`)."""
    from watchgate.dashboard.backend.tasks import get_queue

    while True:
        try:
            await run_in_threadpool(
                get_queue().enqueue,
                "watchgate.dashboard.backend.tasks.purge_old_scores",
                retention_days,
            )
            logger.info("Purga de retención (%d días) encolada; la próxima en 24h.", retention_days)
        except Exception:  # noqa: BLE001 -- Redis caído no debe matar el loop
            logger.exception("No se pudo encolar la purga de retención periódica; se reintentará.")
        await asyncio.sleep(24 * 3600)


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
    interval_hours = _rag_sync_interval_hours()
    rag_sync_task: asyncio.Task[None] | None = None
    if interval_hours > 0:
        rag_sync_task = asyncio.create_task(_rag_sync_loop(interval_hours))
    retention_days = _score_retention_days()
    retention_task: asyncio.Task[None] | None = None
    if retention_days > 0:
        retention_task = asyncio.create_task(_score_retention_loop(retention_days))
    yield
    if rag_sync_task is not None:
        rag_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await rag_sync_task
    if retention_task is not None:
        retention_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await retention_task


def create_app() -> FastAPI:
    # Antes que ensure_safe_startup_config()/el warning de dev-mode de
    # abajo -- ambos loguean durante la propia construcción de la app
    # (module-level `app = create_app()`, no dentro de `lifespan()`), así
    # que si esto fuera después esos mensajes se emitirían con el
    # formato/handler por defecto de Python en vez del elegido aquí.
    configure_logging("dashboard-backend")
    # A diferencia del Engine API (api/main.py), este servicio nunca había
    # tenido el filtro de redacción de secretos -- justo donde viven ahora
    # las credenciales VCS por usuario (PAT de GitHub personal, fallback de
    # organización).
    setup_logging_sanitizer()
    configure_sentry("dashboard-backend")
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
    app.include_router(agent_access_router, prefix="/api")
    # repos_router (prefix "/repos/external") va ANTES que scores_router:
    # scores.py define un catch-all `DELETE /repos/{repo:path}` (borra por
    # nombre de repo) que, al matchear cualquier ruta bajo "/repos/", se
    # comía también las peticiones a `DELETE /repos/external/{repo_id}` de
    # repos.py (borrado por id de MonitoredRepo) si este último se
    # registraba después -- FastAPI/Starlette resuelve rutas en el orden
    # de registro, primer match gana. Reproducido en vivo: el endpoint
    # específico nunca llegaba a ejecutarse, siempre respondía 200 el
    # catch-all sin borrar nada real.
    app.include_router(repos_router, prefix="/api")
    app.include_router(scores_router, prefix="/api")
    app.include_router(keys_router, prefix="/api")
    app.include_router(feedback_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(llm_router, prefix="/api")
    app.include_router(ui_router, prefix="/api")
    app.include_router(user_settings_router, prefix="/api")
    app.include_router(webhooks_router, prefix="/api")
    app.include_router(rag_router, prefix="/api")
    app.include_router(yara_rules_router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
