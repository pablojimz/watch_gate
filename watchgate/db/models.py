"""Modelos relacionales unificados de WatchGate utilizando SQLModel.

Combina validación Pydantic v2 y ORM SQLAlchemy 2.0 en un único esquema.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Organization(SQLModel, table=True):
    """Organización / Tenant cliente de WatchGate SaaS."""

    __tablename__ = "organizations"

    id: str = Field(primary_key=True)
    name: str
    plan_tier: str = Field(default="starter")  # "starter" | "pro" | "enterprise"
    monthly_token_quota: int = Field(default=1_000_000)
    policy_json: str | None = Field(default=None)  # Overrides corporativos de gobernanza
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class User(SQLModel, table=True):
    """Usuario registrado de la plataforma WatchGate / SaaS."""

    __tablename__ = "users"

    id: str = Field(primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    role: str = Field(default="revisor")  # "admin_organizacion" | "mantenedor" | "revisor"
    org_id: str | None = Field(default=None, foreign_key="organizations.id", index=True)
    custom_llm_api_key: str | None = None  # Opcional: Clave cifrada para modalidad BYOK
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserAPIKey(SQLModel, table=True):
    """Vault de API Keys con almacenamiento exclusivo por hash SHA-256."""

    __tablename__ = "user_api_keys"

    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    org_id: str | None = Field(default=None, foreign_key="organizations.id", index=True)
    default_agent_name: str | None = Field(default=None)
    name: str  # Nombre descriptivo (ej. "Runner CI Producción")
    key_prefix: str  # Primeros caracteres públicos (ej. "wg_live_4a8f")
    key_hash: str = Field(unique=True, index=True)  # SHA-256(raw_token)
    scopes: str = Field(default="analysis:write,scores:read")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


class UserTokenUsage(SQLModel, table=True):
    """Consumo mensual acumulado de tokens de LLM por usuario u organización."""

    __tablename__ = "user_token_usage"

    user_id: str = Field(primary_key=True)
    month: str = Field(primary_key=True)  # Formato "YYYY-MM"
    org_id: str | None = Field(default=None, foreign_key="organizations.id", index=True)
    tokens_used: int = Field(default=0)


class SemanticCache(SQLModel, table=True):
    """Caché unificada de respuestas de la capa semántica por hash de diff y organización."""

    __tablename__ = "semantic_cache"

    org_id: str = Field(default="default-org", primary_key=True)
    diff_hash: str = Field(primary_key=True)
    output_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PRScore(SQLModel, table=True):
    """Histórico de puntuaciones de análisis de Pull Requests."""

    __tablename__ = "pr_scores"

    id: str = Field(primary_key=True)
    repo: str = Field(index=True)
    pr_id: str
    user_id: str | None = Field(foreign_key="users.id", default=None)
    org_id: str | None = Field(foreign_key="organizations.id", default=None, index=True)
    agent_id: str | None = Field(default=None, index=True)
    score: int
    semaforo: str  # "verde" | "amarillo" | "rojo"
    layer_results_json: str
    weights_used_json: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class RepoRole(SQLModel, table=True):
    """Asignación de rol por usuario y repositorio."""

    __tablename__ = "repo_roles"

    user_login: str = Field(primary_key=True)
    repo: str = Field(primary_key=True)
    role: str = Field(default="revisor")
