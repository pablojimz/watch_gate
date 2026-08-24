"""Modelos ORM (SQLAlchemy 2.0) del esquema propio del Dashboard.

Base declarativa **independiente** de `watchgate.db.models` (que usa
`sqlmodel.SQLModel`, con su propio `MetaData` global) a propósito: el
Dashboard DB (`WATCHGATE_DASHBOARD_DATABASE_URL`, `.watchgate/dashboard.db`
por defecto) y la Engine DB (`WATCHGATE_DATABASE_URL`, `.watchgate/app.db`)
son dos bases de datos físicamente distintas. Si estos modelos compartieran
metadata con los de `watchgate.db.models`, `Base.metadata.create_all(engine)`
intentaría crear las tablas de una base de datos dentro de la otra en
cuanto se llamase contra el motor equivocado -- cada `DeclarativeBase`
propio garantiza un `MetaData` nuevo y aislado (a diferencia de intentar
compartir la metadata global de `sqlmodel.SQLModel` con un segundo grupo de
tablas, que no es un patrón soportado de forma fiable).

Se usa SQLAlchemy 2.0 "clásico" (`Mapped`/`mapped_column`) en vez de
`SQLModel` aquí: los DTOs de entrada/salida de la API ya existen y viven en
`schemas.py` (`RepoSettings`, `UiSettings`, `LlmSettingsOut`, ...), así que
no hace falta que el modelo de persistencia doble como validador Pydantic
-- evita cualquier colisión de nombres con esos esquemas y es la base
declarativa más simple de razonar como segunda base de datos aislada.

Los nombres de columna, defaults y `CHECK` replican EXACTAMENTE el esquema
que antes vivía como SQL crudo en `SCHEMA`/`POSTGRES_SCHEMA` de la versión
anterior de `db.py`, incluidas las columnas que solo llegaban vía
``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` en `init_db()`/
`_init_db_postgres()` (`author_login`, `accepted_by`, `accepted_at`,
`findings_json`, `vulnerabilities_score`, `vulnerabilities_skipped`,
`threat_summary_json`, `static_threat_nature` en `pr_scores`;
`logo_data_url` en `ui_settings`) -- ese historial de ALTER ya no existe
como tal, este es el esquema final que representaba.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from watchgate.db.crypto import EncryptedString


class DashboardBase(DeclarativeBase):
    """Base declarativa propia del Dashboard DB -- `DashboardBase.metadata`
    es un `MetaData` nuevo, independiente del de `watchgate.db.models`."""


class DashboardPRScore(DashboardBase):
    """Histórico de puntuaciones de PRs del Dashboard.

    Distinta de `watchgate.db.models.PRScore` (Engine DB): esta tabla usa
    columnas planas por capa (`static_score`, `deps_score`, ...) en vez de
    un JSON genérico, y vive en una base de datos físicamente separada --
    son el histórico de dos sistemas distintos (Dashboard local-first vs
    Engine SaaS), no se fusionan.
    """

    __tablename__ = "pr_scores"
    __table_args__ = (
        CheckConstraint(
            "human_feedback IN ('correcto','falso_positivo') OR human_feedback IS NULL",
            name="ck_pr_scores_human_feedback",
        ),
        Index("idx_repo_timestamp", "repo", "timestamp"),
        # AUTOINCREMENT real en SQLite (no solo el alias de rowid por
        # defecto): evita que un id se reutilice tras borrar la última fila
        # -- mismo comportamiento que ya tenía el `INTEGER PRIMARY KEY
        # AUTOINCREMENT` original.
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    repo: Mapped[str] = mapped_column(nullable=False)
    pr_number: Mapped[int] = mapped_column(nullable=False)
    # TEXT, no un tipo temporal real: en Postgres un TIMESTAMP se
    # deserializaría como `datetime.datetime`, no `str`, y rompería
    # `AggregatedResult.timestamp: str` -- todo el código que lo consume
    # (agrupar por día, ordenar) ya trabaja con el string ISO 8601 tal cual.
    timestamp: Mapped[str] = mapped_column(nullable=False)
    score: Mapped[int] = mapped_column(nullable=False)
    semaforo: Mapped[str] = mapped_column(nullable=False)

    static_score: Mapped[int | None] = mapped_column(default=None)
    static_skipped: Mapped[bool | None] = mapped_column(default=None)
    deps_score: Mapped[int | None] = mapped_column(default=None)
    deps_skipped: Mapped[bool | None] = mapped_column(default=None)
    vulnerabilities_score: Mapped[int | None] = mapped_column(default=None)
    vulnerabilities_skipped: Mapped[bool | None] = mapped_column(default=None)
    reputation_score: Mapped[int | None] = mapped_column(default=None)
    reputation_skipped: Mapped[bool | None] = mapped_column(default=None)
    semantic_score: Mapped[int | None] = mapped_column(default=None)
    semantic_skipped: Mapped[bool | None] = mapped_column(default=None)
    semantic_justification: Mapped[str | None] = mapped_column(default=None)

    weights_json: Mapped[str] = mapped_column(nullable=False, default="{}")
    author_login: Mapped[str | None] = mapped_column(default=None)
    human_feedback: Mapped[str | None] = mapped_column(default=None)
    accepted_by: Mapped[str | None] = mapped_column(default=None)
    accepted_at: Mapped[str | None] = mapped_column(default=None)
    findings_json: Mapped[str | None] = mapped_column(default=None)
    threat_summary_json: Mapped[str] = mapped_column(nullable=False, default="{}")
    static_threat_nature: Mapped[str | None] = mapped_column(default=None)
    # "open" (default, incluye los análisis de rama principal -- pr_number=0
    # no es una PR real de GitHub, así que nunca puede "cerrarse") | "closed".
    # RepoPollingService._poll_single_candidate (watchgate/service/
    # repo_polling.py) la pasa a "closed" cuando una PR que sí estaba
    # trackeada deja de aparecer en la lista de PRs abiertas de GitHub --
    # nunca se borra la fila (el histórico de auditoría no se destruye),
    # solo deja de contar/mostrarse como pendiente en el dashboard.
    pr_state: Mapped[str] = mapped_column(nullable=False, default="open")


class RepoRole(DashboardBase):
    """Rol de un usuario sobre un repositorio concreto."""

    __tablename__ = "repo_roles"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin_organizacion','mantenedor','revisor')",
            name="ck_repo_roles_role",
        ),
    )

    user_login: Mapped[str] = mapped_column(primary_key=True)
    repo: Mapped[str] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(nullable=False)


class RepoSettingsRow(DashboardBase):
    """Override de configuración de scoring por repositorio."""

    __tablename__ = "repo_settings"

    repo: Mapped[str] = mapped_column(primary_key=True)
    weights_json: Mapped[str] = mapped_column(nullable=False)
    thresholds_json: Mapped[str] = mapped_column(nullable=False)
    layers_enabled_json: Mapped[str] = mapped_column(nullable=False, default="{}")
    risk_colors_json: Mapped[str] = mapped_column(nullable=False, default="{}")
    block_on_high: Mapped[bool] = mapped_column(nullable=False, default=True)
    require_feedback_on_high: Mapped[bool] = mapped_column(nullable=False, default=False)


class OrgSettingsRow(DashboardBase):
    """Configuración de scoring por defecto de la organización (fila única, id=1)."""

    __tablename__ = "org_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_org_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    weights_json: Mapped[str] = mapped_column(nullable=False)
    thresholds_json: Mapped[str] = mapped_column(nullable=False)
    layers_enabled_json: Mapped[str] = mapped_column(nullable=False)
    risk_colors_json: Mapped[str] = mapped_column(nullable=False, default="{}")
    block_on_high: Mapped[bool] = mapped_column(nullable=False, default=True)
    require_feedback_on_high: Mapped[bool] = mapped_column(nullable=False, default=False)


class DashboardUser(DashboardBase):
    """Usuario local del Dashboard (login/contraseña, independiente de GitHub/GitLab)."""

    __tablename__ = "dashboard_users"

    login: Mapped[str] = mapped_column(primary_key=True)
    password_hash: Mapped[str] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)
    github_api_url: Mapped[str | None] = mapped_column(default=None)
    github_token: Mapped[str | None] = mapped_column(EncryptedString, default=None)
    ui_settings_json: Mapped[str | None] = mapped_column(default=None)


class LlmSettingsRow(DashboardBase):
    """Configuración de proveedor/modelo LLM de organización (fila única, id=1)."""

    __tablename__ = "llm_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_llm_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    provider: Mapped[str] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(nullable=False)
    base_url: Mapped[str | None] = mapped_column(default=None)
    # EncryptedString como github_token -- esta es la clave del proveedor
    # LLM de la organización (Anthropic/Gemini/...), el secreto más caro de
    # filtrar de toda esta tabla; era la ÚNICA columna sensible que se
    # guardaba en claro. Sin migración de esquema: EncryptedString es un
    # TypeDecorator sobre String (mismo DDL), y los valores legados en
    # claro los tolera el fallback de lectura de crypto.py (se re-cifran en
    # la siguiente escritura).
    api_key: Mapped[str | None] = mapped_column(EncryptedString, default=None)
    monthly_budget_tokens: Mapped[int | None] = mapped_column(default=None)
    max_diff_tokens: Mapped[int | None] = mapped_column(default=None)
    github_api_url: Mapped[str | None] = mapped_column(default=None)
    github_token: Mapped[str | None] = mapped_column(EncryptedString, default=None)


class UiSettingsRow(DashboardBase):
    """Apariencia del dashboard (fila única, id=1)."""

    __tablename__ = "ui_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_ui_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    primary_color: Mapped[str] = mapped_column(nullable=False)
    accent_color: Mapped[str] = mapped_column(nullable=False)
    radius: Mapped[str] = mapped_column(nullable=False)
    font_scale: Mapped[str] = mapped_column(nullable=False)
    density: Mapped[str] = mapped_column(nullable=False)
    default_theme: Mapped[str] = mapped_column(nullable=False)
    logo_data_url: Mapped[str | None] = mapped_column(default=None)
