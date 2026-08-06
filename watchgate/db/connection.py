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

_DEFAULT_SQLITE_URL = "sqlite:///.watchgate/app.db"


def get_database_url() -> str:
    """Obtiene la URL de la base de datos de entorno o usa la ruta SQLite por defecto."""
    return os.environ.get("WATCHGATE_DATABASE_URL", _DEFAULT_SQLITE_URL)


def build_engine(database_url: str | None = None) -> engine.Engine:
    """Construye el motor SQLAlchemy/SQLModel adecuado según el dialecto."""
    db_url = database_url or get_database_url()

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


def init_db(db_engine: engine.Engine | None = None) -> None:
    """Crea todas las tablas definidas en SQLModel si no existen."""
    target_engine = db_engine or default_engine
    SQLModel.metadata.create_all(target_engine)


def get_session(db_engine: engine.Engine | None = None) -> Generator[Session, None, None]:
    """Generador de sesión de FastAPI para inyección de dependencias."""
    target_engine = db_engine or default_engine
    with Session(target_engine) as session:
        yield session
