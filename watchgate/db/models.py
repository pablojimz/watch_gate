"""Modelos relacionales unificados de WatchGate utilizando SQLModel.

Combina validación Pydantic v2 y ORM SQLAlchemy 2.0 en un único esquema.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """Usuario registrado de la plataforma WatchGate / SaaS."""

    __tablename__ = "users"  # type: ignore[assignment]

    id: str = Field(primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    role: str = Field(default="revisor")  # "admin_organizacion" | "mantenedor" | "revisor"
    custom_llm_api_key: str | None = None  # Opcional: Clave cifrada para modalidad BYOK
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserAPIKey(SQLModel, table=True):
    """Vault de API Keys por usuario con almacenamiento exclusivo por hash SHA-256."""

    __tablename__ = "user_api_keys"  # type: ignore[assignment]

    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    name: str  # Nombre descriptivo (ej. "Runner CI Producción")
    key_prefix: str  # Primeros caracteres públicos (ej. "wg_live_4a8f")
    key_hash: str = Field(unique=True, index=True)  # SHA-256(raw_token)
    scopes: str = Field(default="analysis:write,scores:read")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


class UserTokenUsage(SQLModel, table=True):
    """Consumo mensual acumulado de tokens de LLM por usuario."""

    __tablename__ = "user_token_usage"  # type: ignore[assignment]

    user_id: str = Field(foreign_key="users.id", primary_key=True)
    month: str = Field(primary_key=True)  # Formato "YYYY-MM"
    tokens_used: int = Field(default=0)


class SemanticCache(SQLModel, table=True):
    """Caché unificada de respuestas de la capa semántica por hash de diff."""

    __tablename__ = "semantic_cache"  # type: ignore[assignment]

    diff_hash: str = Field(primary_key=True)
    output_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PRScore(SQLModel, table=True):
    """Histórico de puntuaciones de análisis de Pull Requests."""

    __tablename__ = "pr_scores"  # type: ignore[assignment]

    id: str = Field(primary_key=True)
    repo: str = Field(index=True)
    pr_id: str
    user_id: str | None = Field(foreign_key="users.id", default=None)
    score: int
    semaforo: str  # "verde" | "amarillo" | "rojo"
    layer_results_json: str
    weights_used_json: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
