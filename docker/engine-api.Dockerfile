# Imagen del Engine API (watchgate/api/main.py) -- el servicio que exponen
# los adaptadores externos (GitHub Action, agentes de IA vía
# /api/v1/agent/*, hook pre-receive delegando a un servidor central) para
# analizar diffs sin tener que instalar la CLI en cada sitio.
#
# Build multi-stage: la primera capa instala TODAS las dependencias del
# proyecto (semgrep, yara-python, chromadb + sentence-transformers/torch
# para la capa semántica/RAG -- son pesadas, ~1.5 GB, inherentes al
# proyecto, no a esta imagen) en un venv aislado; la segunda copia solo ese
# venv ya resuelto + el código de la app, sin el toolchain de compilación.
#
# Build:  docker build -f docker/engine-api.Dockerfile -t watchgate-engine-api .
# Run:    docker run -p 8080:8080 --env-file .env watchgate-engine-api

FROM python:3.11-slim AS builder

# build-essential: sentence-transformers/chromadb traen dependencias con
# extensiones nativas que a veces no publican wheel para todas las
# plataformas -- sin esto, `poetry install` puede fallar a mitad intentando
# compilar. git: lo necesita GitPython (aunque el Engine API en sí no clona
# repos, es una dependencia transitiva del paquete).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN pip install --no-cache-dir poetry

# Copiar solo los manifiestos primero -- capa de dependencias cacheable
# aparte del código, para que un cambio en watchgate/*.py no invalide la
# instalación completa de torch/semgrep/etc. en cada build.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-directory

COPY watchgate ./watchgate
COPY README.md ./
RUN poetry install --only main


FROM python:3.11-slim AS runtime

# curl: healthcheck contra GET /health (ver más abajo). git: GitPython
# (watchgate.core.diffparser) lo necesita en runtime, no solo durante el
# build -- sin esto, el proceso crashea en el primer import con
# "Bad git executable" en cuanto cualquier endpoint toca diffparser.
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

# .watchgate/ es donde cae el SQLite por defecto (watchgate/db/connection.py)
# y el cache de CostController si no se configuran WATCHGATE_DATABASE_URL/
# equivalentes -- sin este directorio (y sin permisos, corriendo como
# usuario no-root) el arranque falla con "unable to open database file" en
# cuanto cualquier endpoint toca la BD. En producción, usa Postgres (ver
# docker-compose.yml) o monta un volumen aquí; sin volumen, se pierde en
# cada recreación del contenedor.
RUN mkdir -p /app/.watchgate && chown watchgate:watchgate /app/.watchgate

USER watchgate
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "watchgate.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
