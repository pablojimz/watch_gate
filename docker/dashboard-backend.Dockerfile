# Imagen del backend del Dashboard (watchgate/dashboard/backend/main.py).
# El frontend (React/Vite) se construye y se sirve por separado -- ver
# watchgate/dashboard/frontend/Dockerfile -- este backend solo expone la
# API REST (login, scores, settings, keys...), sin servir ficheros
# estáticos (ver CORS configurable vía WATCHGATE_DASHBOARD_CORS_ORIGINS).
#
# Mismas dependencias pesadas que engine-api.Dockerfile (un único paquete
# `watchgate`, sin extras separados por servicio todavía -- ver nota en
# docs/despliegue.md) aunque este servicio en concreto no las necesite en
# tiempo de ejecución; no se ha separado el empaquetado por no ser
# necesario para tener algo desplegable hoy.
#
# Build:  docker build -f docker/dashboard-backend.Dockerfile -t watchgate-dashboard-backend .
# Run:    docker run -p 8000:8000 --env-file .env watchgate-dashboard-backend

FROM python:3.11-slim AS builder

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
RUN poetry install --only main --no-root --no-directory

COPY watchgate ./watchgate
COPY README.md ./
RUN poetry install --only main


FROM python:3.11-slim AS runtime

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
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# .watchgate/ es donde caen el SQLite por defecto y el índice RAG local si
# no se configuran WATCHGATE_DASHBOARD_DATABASE_URL/WATCHGATE_CHROMA_URL --
# en un despliegue real de verdad, usa Postgres (ver docker-compose.yml) o
# monta un volumen aquí; sin volumen, este directorio se pierde en cada
# recreación del contenedor.
RUN mkdir -p /app/.watchgate && chown watchgate:watchgate /app/.watchgate

USER watchgate
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "watchgate.dashboard.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
