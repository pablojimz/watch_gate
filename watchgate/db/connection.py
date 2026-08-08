"""Motor de conexión a base de datos híbrido para WatchGate.

Soporta SQLite en desarrollo/testing local con modo WAL y timeouts
de 30 segundos, y PostgreSQL en entornos de producción SaaS mediante
la variable de entorno WATCHGATE_DATABASE_URL.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import engine, event, inspect
from sqlmodel import Session, SQLModel, create_engine

_DEFAULT_SQLITE_URL = "sqlite:///.watchgate/app.db"


class SchemaOutOfDateError(RuntimeError):
    """La base de datos ya existe pero le faltan columnas que el código
    actual espera -- ver `_check_schema_matches_models` para el porqué."""


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


def _check_schema_matches_models(target_engine: engine.Engine) -> None:
    """Aborta con un mensaje claro si una tabla YA EXISTE en la base de
    datos pero le faltan columnas que los modelos de SQLModel actuales
    esperan.

    `SQLModel.metadata.create_all()` (más abajo) solo crea tablas que no
    existen -- nunca añade columnas nuevas a una tabla ya existente. No hay
    ningún script de migración real (Alembic o equivalente) en este
    proyecto todavía. Sin este chequeo, desplegar una versión del código
    que añade columnas (como `org_id` en la Fase 1 multi-tenant) contra
    cualquier base de datos con esas tablas ya creadas produce un apagón
    confuso: `OperationalError: no such column` mucho más tarde, en medio
    de `create_api_key`/`save_pr_score`, sin relación aparente con el
    despliegue que lo causó. Se prefiere fallar aquí, en el arranque, con
    un mensaje que dice exactamente qué falta y qué hacer.

    No intenta migrar nada por su cuenta -- una columna nueva puede
    necesitar backfill, un `NOT NULL` puede necesitar un valor por
    defecto pensado, y un cambio de primary key (como el de
    `semantic_cache` en esa misma fase) no es ni siquiera un `ALTER TABLE
    ADD COLUMN`. Eso requiere una migración real, no un parche automático
    en el arranque.
    """
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    problems: list[str] = []
    for table_name, table in SQLModel.metadata.tables.items():
        if table_name not in existing_tables:
            continue  # create_all() la creará entera y correcta más abajo.
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        expected_columns = {col.name for col in table.columns}
        missing = sorted(expected_columns - existing_columns)
        if missing:
            problems.append(f"  - tabla '{table_name}': faltan columnas {missing}")

    if problems:
        raise SchemaOutOfDateError(
            "La base de datos existente no coincide con el esquema actual de "
            "WatchGate -- faltan columnas que el código espera:\n"
            + "\n".join(problems)
            + "\nEste proyecto todavía no tiene migraciones automáticas (Alembic o "
            "equivalente). Aplica manualmente los `ALTER TABLE` necesarios (o, si es "
            "un entorno de desarrollo sin datos que conservar, borra/recrea la base "
            "de datos) antes de arrancar esta versión."
        )


def init_db(db_engine: engine.Engine | None = None) -> None:
    """Crea todas las tablas definidas en SQLModel si no existen.

    Antes de crear nada, comprueba que las tablas que YA existen tengan
    todas las columnas que el código actual espera -- ver
    `_check_schema_matches_models`. `create_all()` por sí solo nunca migra
    una tabla existente, así que sin este chequeo el desajuste se
    descubriría mucho más tarde, a mitad de una petición cualquiera.
    """
    target_engine = db_engine or default_engine
    _check_schema_matches_models(target_engine)
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
