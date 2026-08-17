"""Motor de conexión a base de datos híbrido para WatchGate.

Soporta SQLite en desarrollo/testing local con modo WAL y timeouts
de 30 segundos, y PostgreSQL en entornos de producción SaaS mediante
la variable de entorno WATCHGATE_DATABASE_URL.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import engine, event
from sqlmodel import Session, SQLModel, create_engine

from watchgate.db.schema_guard import SchemaOutOfDateError, check_schema_matches_metadata

_DEFAULT_SQLITE_URL = "sqlite:///.watchgate/app.db"

__all__ = [
    "SchemaOutOfDateError",
    "build_engine",
    "default_engine",
    "get_database_url",
    "get_db_session",
    "get_session",
    "init_db",
    "normalize_database_url",
]


def get_database_url() -> str:
    """Obtiene la URL de la base de datos de entorno o usa la ruta SQLite por defecto."""
    return os.environ.get("WATCHGATE_DATABASE_URL", _DEFAULT_SQLITE_URL)


def normalize_database_url(database_url: str) -> str:
    """Normaliza un DSN `postgres(ql)://` sin driver explícito a
    `postgresql+psycopg://` (SQLAlchemy 2.0 resuelve un DSN `postgresql://`
    a pelo contra el driver `psycopg2` por defecto, no `psycopg` v3 -- y
    `psycopg2` no es una dependencia del proyecto, solo `psycopg[binary]`.
    Sin esto, `create_engine()` contra la URL exacta que documenta
    `.env.example` fallaría con `ModuleNotFoundError: No module named
    'psycopg2'` en el primer arranque contra Postgres real). No toca URLs
    que ya traen un driver explícito (`postgresql+psycopg://`,
    `postgresql+asyncpg://`, ...) ni URLs de otros dialectos (sqlite)."""
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://") :]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def build_engine(database_url: str | None = None) -> engine.Engine:
    """Construye el motor SQLAlchemy/SQLModel adecuado según el dialecto."""
    db_url = normalize_database_url(database_url or get_database_url())

    connect_args: dict[str, Any] = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30.0

    db_engine = create_engine(db_url, connect_args=connect_args, echo=False)

    if db_url.startswith("sqlite"):

        @event.listens_for(db_engine, "connect")
        def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return db_engine


# Engine por defecto a nivel de módulo
default_engine = build_engine()


_MIGRATION_HINT = (
    "Aplica la migración pendiente con `alembic upgrade head` (o, si es "
    "un entorno de desarrollo sin datos que conservar, borra/recrea la base "
    "de datos) antes de arrancar esta versión. Si la base de datos ya tenía "
    "estas tablas de antes de adoptar Alembic, primero hace falta "
    "`alembic stamp head` una sola vez -- ver docs/despliegue.md."
)


def init_db(db_engine: engine.Engine | None = None) -> None:
    """Crea todas las tablas definidas en SQLModel si no existen.

    Antes de crear nada, comprueba que las tablas que YA existen tengan
    todas las columnas que el código actual espera -- ver
    `check_schema_matches_metadata`. `create_all()` por sí solo nunca migra
    una tabla existente, así que sin este chequeo el desajuste se
    descubriría mucho más tarde, a mitad de una petición cualquiera.
    """
    target_engine = db_engine or default_engine
    check_schema_matches_metadata(target_engine, SQLModel.metadata, migration_hint=_MIGRATION_HINT)
    SQLModel.metadata.create_all(target_engine)


def get_session(db_engine: engine.Engine | None = None) -> Generator[Session, None, None]:
    """Generador de sesión de SQLModel."""
    target_engine = db_engine or default_engine
    with Session(target_engine) as session:
        yield session


def get_db_session() -> Generator[Session, None, None]:
    """Generador de sesión de FastAPI sin parámetros para inyección de dependencias."""
    with Session(default_engine) as session:
        yield session
