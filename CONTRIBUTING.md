# Contribuir a WatchGate

Guía rápida para levantar el entorno de desarrollo y las convenciones antes de enviar una Pull Request. Para la arquitectura y el diseño del sistema, ver [`README.md`](README.md) y [`docs/WatchGate_spec_implementacion_IA.md`](docs/WatchGate_spec_implementacion_IA.md).

## Entorno de desarrollo

```bash
# Todas las dependencias, incluido el extra "analysis" (semgrep/yara/chromadb/
# sentence-transformers/anthropic/google-genai) -- necesario para correr la
# suite de tests completa.
poetry install --all-extras
```

Para el stack completo (Postgres, Redis, Engine API, Dashboard) con Docker, ver la sección *Despliegue* de [`README.md`](README.md#despliegue) — `docker compose up --build` levanta todo en modo desarrollo con hot-reload.

## Antes de enviar una Pull Request

```bash
# Tests unitarios
poetry run pytest

# Formateo y linter
poetry run ruff check .
poetry run ruff format --check .

# Tipado estático (mypy --strict)
poetry run mypy

# Límites de arquitectura (core/ no puede depender de adaptadores/UI)
poetry run lint-imports
```

El Makefile expone estos mismos pasos: `make test`, `make lint`.

No hace falta correr la suite de validación (`tests/integration/`, `pytest -m integration`) en cada PR — llama de verdad a la API de un LLM (coste real) y no corre en CI por defecto. Solo hace falta si tu cambio toca la capa semántica o el RAG; en ese caso, `poetry run python -m tests.integration.generate_validation_report` regenera `docs/validation_report.md` contra los ~193 casos de `tests/cases/`.

## Convenciones de commits y ramas

- Mensajes de commit en el estilo `tipo(ámbito): descripción breve` (`fix(rag): ...`, `feat(dashboard): ...`, `perf(static): ...`) — revisa `git log` para ejemplos recientes.
- Un commit por cambio lógico independiente, no mezcles varios fixes no relacionados en el mismo commit.
- Sin ramas de larga duración fuera de `main`; PRs pequeñas y enfocadas.

## Estilo de código

- Comentarios solo cuando el *por qué* no es obvio (una restricción oculta, un bug reproducido, un trade-off) — nunca describiendo *qué* hace el código, eso ya lo dice el nombre.
- `watchgate/core/` no puede importar nada de `watchgate/api/`, `watchgate/cli.py`, `watchgate/dashboard/` ni de ningún adaptador — lo hace cumplir `lint-imports` (ver `pyproject.toml`, sección `[tool.importlinter]`) y `tests/unit/test_architecture.py`.
- Prioriza extender un contrato Pydantic/SQLModel existente (`watchgate/core/models.py`, `watchgate/db/models.py`) antes que inventar una estructura de datos paralela.
