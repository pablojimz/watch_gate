"""Guard genérico de esquema: aborta el arranque con un mensaje claro si una
base de datos existente le faltan columnas que el código actual espera.

Extraído de `watchgate/db/connection.py` (que lo usaba solo para la Engine
DB) para que también lo reuse `watchgate/dashboard/backend/db.py` (Dashboard
DB) -- misma garantía de despliegue, dos bases de datos físicas distintas,
un único sitio que mantener.
"""

from __future__ import annotations

from sqlalchemy import MetaData, engine, inspect


class SchemaOutOfDateError(RuntimeError):
    """La base de datos ya existe pero le faltan columnas que el código
    actual espera -- ver `check_schema_matches_metadata` para el porqué."""


def check_schema_matches_metadata(
    target_engine: engine.Engine,
    metadata: MetaData,
    *,
    migration_hint: str,
) -> None:
    """Aborta con un mensaje claro si una tabla YA EXISTE en la base de
    datos pero le faltan columnas que `metadata` (SQLModel/SQLAlchemy)
    actualmente espera.

    `metadata.create_all()` (que cada caller invoca después de este check)
    solo crea tablas que no existen -- nunca añade columnas nuevas a una
    tabla ya existente, y Alembic tampoco se ejecuta solo en cada arranque a
    propósito (aplicar migraciones es un paso explícito de despliegue, no
    algo que deba correr sin supervisión en cada boot -- sobre todo con más
    de una réplica arrancando a la vez contra la misma base de datos). Sin
    este chequeo, desplegar una versión del código que añade columnas contra
    una base de datos a la que no se le aplicó la migración produce un
    apagón confuso: `OperationalError: no such column` mucho más tarde, en
    medio de cualquier función de acceso, sin relación aparente con el
    despliegue que lo causó. Se prefiere fallar aquí, en el arranque, con un
    mensaje que dice exactamente qué falta y qué hacer (`migration_hint`).
    """
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    problems: list[str] = []
    for table_name, table in metadata.tables.items():
        if table_name not in existing_tables:
            continue  # create_all() la creará entera y correcta después.
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
            + f"\n{migration_hint}"
        )
