.PHONY: install lint test run-demo dashboard-backend dashboard-frontend dashboard-install docker-up docker-down migrate migration migrate-dashboard migration-dashboard

install:
	# --all-extras: incluye el extra "analysis" (semgrep/yara/chromadb/
	# sentence-transformers/anthropic/google-genai) -- necesario para
	# desarrollo y para correr la suite de tests completa. Ver la nota en
	# pyproject.toml sobre por qué existe ese extra (imagen Docker del
	# Dashboard backend más ligera, no un cambio en el flujo de desarrollo).
	poetry install --all-extras

lint:
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run mypy
	poetry run lint-imports

# `python -m pytest` (no el script `pytest` suelto): así el intérprete añade el
# directorio actual a sys.path y watchgate se resuelve aunque el mecanismo de
# instalación editable (basado en un .pth) falle en el entorno de turno.
test:
	poetry run python -m pytest --cov --cov-report=term-missing

run-demo:
	poetry run python -m watchgate.cli analyze --base HEAD~1 --head HEAD

dashboard-install:
	cd watchgate/dashboard/frontend && npm install

dashboard-backend:
	WATCHGATE_DASHBOARD_DEV_MODE=1 WATCHGATE_DASHBOARD_SEED=1 \
		poetry run uvicorn watchgate.dashboard.backend.main:app --reload --reload-dir watchgate --port 8000

dashboard-frontend:
	cd watchgate/dashboard/frontend && npm run dev

# Stack completo (Engine API + Dashboard backend/frontend + Postgres real)
# vía Docker Compose -- ver docs/despliegue.md.
docker-up:
	docker compose up --build

docker-down:
	docker compose down

# Migraciones del esquema SQLModel (watchgate/db/, Engine DB) -- ver
# docs/despliegue.md para el flujo completo (incluye cómo adoptar Alembic
# en una base de datos ya existente con `alembic stamp head`). El esquema
# propio del Dashboard (watchgate/dashboard/backend/models.py) usa un
# segundo entorno Alembic separado, ver los targets *-dashboard abajo y
# alembic_dashboard/env.py -- son dos bases de datos físicamente
# distintas, cada una con su propio historial de migraciones.
migrate:
	poetry run alembic upgrade head

# Uso: make migration m="añadir columna x a pr_scores"
migration:
	poetry run alembic revision --autogenerate -m "$(m)"

# Migraciones del esquema del Dashboard DB (watchgate/dashboard/backend/models.py).
migrate-dashboard:
	poetry run alembic -c alembic_dashboard.ini upgrade head

# Uso: make migration-dashboard m="añadir columna x a repo_settings"
migration-dashboard:
	poetry run alembic -c alembic_dashboard.ini revision --autogenerate -m "$(m)"
