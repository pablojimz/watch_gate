# Imagen del backend del Dashboard (watchgate/dashboard/backend/main.py).
# El frontend (React/Vite) se construye y se sirve por separado -- ver
# watchgate/dashboard/frontend/Dockerfile -- este backend solo expone la
# API REST (login, scores, settings, keys...), sin servir ficheros
# estáticos (ver CORS configurable vía WATCHGATE_DASHBOARD_CORS_ORIGINS).
#
# A diferencia de engine-api.Dockerfile, instalamos el extra "analysis"
# (semgrep/yara-python/chromadb/sentence-transformers-torch/anthropic/
# google-genai) -- este servicio (y particularmente el Worker RQ asociado)
# sí ejecuta ahora análisis completos de repositorios asíncronamente
# (ver watchgate/dashboard/backend/tasks.py).
#
# Build:  docker build -f docker/dashboard-backend.Dockerfile -t watchgate-dashboard-backend .
# Run:    docker run -p 8000:8000 --env-file .env watchgate-dashboard-backend

FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --extras analysis --no-root --no-directory

COPY watchgate ./watchgate
COPY README.md ./
# alembic.ini/alembic: sin esto, ni este contenedor ni dashboard-worker (que
# reutiliza esta imagen) pueden ejecutar `alembic upgrade head` -- migrar el
# esquema queda forzosamente atado al contenedor engine-api, que sí los trae
# (ver docker/engine-api.Dockerfile y docs/despliegue.md).
# alembic_dashboard.ini/alembic_dashboard: segundo entorno Alembic, esquema
# propio del Dashboard DB (watchgate/dashboard/backend/models.py) -- este
# SÍ es el contenedor natural desde el que correrlo (ver docs/despliegue.md).
COPY alembic.ini ./
COPY alembic ./alembic
COPY alembic_dashboard.ini ./
COPY alembic_dashboard ./alembic_dashboard
RUN poetry install --only main --extras analysis


FROM python:3.14-slim AS runtime

# curl: healthcheck. git: GitPython (watchgate.core.diffparser) es una
# dependencia transitiva del paquete `watchgate` -- aunque el Dashboard
# backend no lo use directamente, sin git el proceso puede crashear en el
# primer import (visto en vivo en el Engine API con el mismo paquete).
RUN apt-get update && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 watchgate

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/watchgate /app/watchgate
COPY --from=builder /app/README.md /app/README.md
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic_dashboard.ini /app/alembic_dashboard.ini
COPY --from=builder /app/alembic_dashboard /app/alembic_dashboard
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# .watchgate/ es donde caen el SQLite por defecto y el índice RAG local si
# no se configuran WATCHGATE_DASHBOARD_DATABASE_URL/WATCHGATE_CHROMA_URL --
# en un despliegue real de verdad, usa Postgres (ver docker-compose.yml) o
# monta un volumen aquí; sin volumen, este directorio se pierde en cada
# recreación del contenedor.
RUN mkdir -p /app/.watchgate && chown watchgate:watchgate /app/.watchgate

# watchgate/core/rag/corpus/ llega de la COPY de arriba propiedad de root
# (sin --chown) -- dashboard-worker escribe ahí avisos nuevos en cada
# sincronización periódica (tasks.py::run_rag_sync -> threat_feed.py) y,
# sin este chown, esa escritura siempre falla con PermissionError contra
# el usuario `watchgate` no-root de abajo (reproducido en vivo: cada ciclo
# de sync fallaba, sin excepción). Mismo motivo que el chown de
# .watchgate/ arriba: sin volumen aparte, los avisos sincronizados se
# pierden en cada recreación del contenedor -- aceptable por ahora
# (run_rag_sync los vuelve a traer), documentado por si en el futuro
# interesa un volumen para no perder el historial de reindexados.
RUN chown -R watchgate:watchgate /app/watchgate/core/rag/corpus

USER watchgate
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "watchgate.dashboard.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
