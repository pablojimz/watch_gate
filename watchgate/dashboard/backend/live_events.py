"""Avisos en vivo (Server-Sent Events) de nuevos análisis de PR.

Sustituye al sondeo desde el frontend (RepoPage.tsx pedía /scores cada
15s sin parar, viera o no algo nuevo): en vez de que el navegador
pregunte "¿hay algo nuevo?" indefinidamente, es el propio servidor el que
avisa -- una única conexión SSE por pestaña, sin tráfico mientras no pasa
nada.

Mecanismo: cuando un worker persiste un score nuevo (insert_aggregated en
db.py, llamado desde tasks.py), publica un mensaje ligero en un canal de
Redis Pub/Sub. Cualquier proceso de dashboard-backend con una conexión SSE
abierta para ese repo (stream_repo_events) lo recibe y reenvía al
navegador como `data: refresh`, que entonces sí vuelve a pedir /scores.
Redis Pub/Sub (no una cola) porque no hace falta persistencia ni entrega
garantizada -- si nadie está escuchando en ese instante, no pasa nada: la
próxima carga de la página ve igualmente el dato ya guardado en Postgres.

Best-effort en ambos sentidos: si Redis no está disponible,
publish_pr_update() nunca debe poder romper el análisis (solo se pierde
el aviso en vivo), y stream_repo_events() se degrada a mandar solo
heartbeats sin avisos en vivo en vez de reventar la conexión SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator

import redis
import redis.asyncio as aioredis

logger = logging.getLogger("watchgate.dashboard.live_events")

# Mismo valor por defecto que tasks.py::get_redis_conn -- se repite aquí
# (en vez de importarlo) para no crear un ciclo de imports: tasks.py
# importa este módulo para llamar a publish_pr_update() tras persistir
# cada score.
_REDIS_URL = os.environ.get("WATCHGATE_REDIS_URL", "redis://localhost:6379/0")

_CHANNEL = "watchgate:pr-updates"

# Menor que el proxy_read_timeout por defecto de nginx (60s) y sin
# problemas para Caddy -- mantiene viva la conexión a través de ambos
# proxies y deja que el navegador detecte una caída real en segundos, no
# minutos.
_HEARTBEAT_SECONDS = 20


def publish_pr_update(repo: str) -> None:
    """Avisa (best-effort) de que `repo` tiene un score nuevo. Se llama
    justo después de insert_aggregated() en cada camino de análisis de
    tasks.py -- un fallo aquí (Redis caído, timeout...) nunca debe
    propagarse: el análisis ya se guardó bien, solo se pierde el aviso en
    vivo."""
    try:
        redis.from_url(_REDIS_URL, socket_connect_timeout=2).publish(
            _CHANNEL, json.dumps({"repo": repo})
        )
    except Exception:
        logger.warning("No se pudo publicar el aviso de PR nuevo para %s", repo, exc_info=True)


async def _stream_events(repo: str | None, log_label: str) -> AsyncIterator[str]:
    """Generador SSE compartido: `data: refresh\\n\\n` cada vez que llega un
    aviso de publish_pr_update() -- filtrado a `repo` si se pasa (ver
    stream_repo_events, para la página de detalle de UN repo), o para
    CUALQUIER repo si `repo` es `None` (ver stream_all_events, para la
    lista `/repos` -- no necesita saber CUÁL repo cambió, solo que algo
    cambió, para volver a pedir su resumen). Comentario de heartbeat cada
    _HEARTBEAT_SECONDS si no hay nada nuevo (mantiene viva la conexión y
    sirve de latido para que el navegador note una caída real)."""
    try:
        client: aioredis.Redis = aioredis.from_url(_REDIS_URL, socket_connect_timeout=2)
        pubsub = client.pubsub()
        await pubsub.subscribe(_CHANNEL)
    except Exception:
        # Degradado sin Redis: la página sigue funcionando (la carga
        # inicial de /scores ya trae el dato), solo no hay aviso en vivo.
        logger.warning(
            "SSE de %s sin Redis disponible -- solo heartbeats, sin avisos en vivo",
            log_label,
            exc_info=True,
        )
        while True:
            await asyncio.sleep(_HEARTBEAT_SECONDS)
            yield ": heartbeat\n\n"

    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=_HEARTBEAT_SECONDS
            )
            if message is None:
                yield ": heartbeat\n\n"
                continue
            try:
                payload = json.loads(message["data"])
            except (TypeError, ValueError, KeyError):
                continue
            if repo is None or payload.get("repo") == repo:
                yield "data: refresh\n\n"
    finally:
        # Se ejecuta también cuando el cliente cierra la pestaña/navega
        # fuera -- Starlette cancela la tarea del generador, lo que lanza
        # aquí dentro y cae en este finally en vez de dejar la suscripción
        # de Redis abierta para siempre.
        await pubsub.unsubscribe(_CHANNEL)
        await pubsub.close()
        await client.close()


def stream_repo_events(repo: str) -> AsyncIterator[str]:
    """SSE para la página de detalle de UN repo -- solo sus propios avisos."""
    return _stream_events(repo, log_label=repo)


def stream_all_events() -> AsyncIterator[str]:
    """SSE para la lista `/repos`: avisa de un score nuevo en CUALQUIER
    repo visible para el usuario (el filtrado por org/rol lo sigue
    aplicando, como siempre, el propio GET que el frontend repite al
    recibir el aviso -- este stream no expone qué repo cambió, así que no
    hace falta re-comprobar permisos por mensaje)."""
    return _stream_events(None, log_label="*")
