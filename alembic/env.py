"""env.py de Alembic para el esquema SQLModel unificado (watchgate/db/).

Deliberadamente NO cubre el esquema propio del Dashboard
(watchgate/dashboard/backend/db.py) -- ese es SQL crudo (sqlite3/psycopg
directos, sin SQLAlchemy) con su propio mecanismo de migración por guardas
(`init_db()` comprueba columna a columna con `PRAGMA table_info`/
`information_schema` y aplica `ALTER TABLE` idempotentes) -- ya probado en
producción, adaptarlo a Alembic sería una reescritura mayor sin necesidad
real. Este Alembic cubre el otro esquema, el de SQLModel
(organizations/users/user_api_keys/user_token_usage/semantic_cache/
pr_scores), que sí es SQLAlchemy nativo y donde Alembic encaja sin fricción.

La URL de conexión se resuelve igual que en producción
(WATCHGATE_DATABASE_URL, ver watchgate/db/connection.py::get_database_url)
en vez de estar fija en alembic.ini -- así `alembic upgrade head` apunta
siempre a la misma base de datos que usaría la propia app en ese entorno,
sin tener que mantener la URL sincronizada en dos sitios.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from watchgate.db.connection import get_database_url
from watchgate.db.models import SQLModel  # noqa: F401 - registra las tablas en metadata

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url())

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
