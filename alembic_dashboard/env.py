"""env.py de Alembic para el esquema del Dashboard (watchgate/dashboard/backend/).

Segundo entorno Alembic, separado de `alembic/env.py` (que cubre
`watchgate/db/models.py`, la Engine DB): son dos bases de datos físicamente
distintas (`WATCHGATE_DASHBOARD_DATABASE_URL` vs `WATCHGATE_DATABASE_URL`),
cada una con su propio historial de migraciones -- compartir uno mezclaría
el esquema de una dentro de la otra en cuanto se corriera `upgrade head`
contra el motor equivocado.

La URL de conexión se resuelve igual que en producción (mismo criterio que
`watchgate.dashboard.backend.db._database_url`, ver ahí) en vez de estar
fija en `alembic_dashboard.ini` -- así `alembic -c alembic_dashboard.ini
upgrade head` apunta siempre a la misma base de datos que usaría la propia
app en ese entorno, sin tener que mantener la URL sincronizada en dos sitios.
Pasa también por `normalize_database_url()` (mismo motivo que
`build_engine()`/`alembic/env.py`): un DSN `postgresql://` sin driver
explícito resuelve a `psycopg2` por defecto en SQLAlchemy 2.0, no instalado
en este proyecto -- sin normalizar, `alembic -c alembic_dashboard.ini
upgrade head` contra la URL exacta que documenta `.env.example` falla con
`ModuleNotFoundError: No module named 'psycopg2'` (reproducido en vivo).
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from watchgate.dashboard.backend.db import _database_url
from watchgate.dashboard.backend.models import DashboardBase  # noqa: F401 - registra las tablas
from watchgate.db.connection import normalize_database_url

config = context.config
config.set_main_option("sqlalchemy.url", normalize_database_url(_database_url(None)))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = DashboardBase.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
