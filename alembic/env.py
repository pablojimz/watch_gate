"""env.py de Alembic para el esquema SQLModel unificado (watchgate/db/), la
Engine DB. El esquema propio del Dashboard
(watchgate/dashboard/backend/models.py) tiene su PROPIO entorno Alembic
separado (`alembic_dashboard/`, ver ahí) -- son dos bases de datos
físicamente distintas (`WATCHGATE_DATABASE_URL` vs
`WATCHGATE_DASHBOARD_DATABASE_URL`), cada una con su propio historial de
migraciones.

La URL de conexión se resuelve igual que en producción
(WATCHGATE_DATABASE_URL, ver watchgate/db/connection.py::get_database_url)
en vez de estar fija en alembic.ini -- así `alembic upgrade head` apunta
siempre a la misma base de datos que usaría la propia app en ese entorno,
sin tener que mantener la URL sincronizada en dos sitios. Pasa también por
`normalize_database_url()` (mismo motivo que `build_engine()`): un DSN
`postgresql://` sin driver explícito resuelve a `psycopg2` por defecto en
SQLAlchemy 2.0, no instalado en este proyecto (solo `psycopg` v3) -- sin
normalizar, `alembic upgrade head` contra la URL exacta que documenta
`.env.example` falla con `ModuleNotFoundError: No module named 'psycopg2'`.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from watchgate.db.connection import get_database_url, normalize_database_url
from watchgate.db.models import SQLModel  # noqa: F401 - registra las tablas en metadata

config = context.config
config.set_main_option("sqlalchemy.url", normalize_database_url(get_database_url()))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


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
