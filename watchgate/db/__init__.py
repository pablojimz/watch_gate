"""Paquete unificado de persistencia de WatchGate (watchgate/db/).

Proporciona abstracción relacional híbrida con SQLModel (SQLite en dev/test,
PostgreSQL en producción SaaS) para usuarios, API Keys, cuotas de tokens,
caché semántica e histórico de puntuaciones.
"""

from __future__ import annotations

from watchgate.db.connection import get_session, init_db
from watchgate.db.models import (
    PRScore,
    SemanticCache,
    User,
    UserAPIKey,
    UserTokenUsage,
)

__all__ = [
    "PRScore",
    "SemanticCache",
    "User",
    "UserAPIKey",
    "UserTokenUsage",
    "get_session",
    "init_db",
]
