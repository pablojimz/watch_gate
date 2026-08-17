"""baseline: esquema Dashboard DB inicial (pr_scores, repo_roles, repo_settings, org_settings, dashboard_users, llm_settings, ui_settings)

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-08-17 00:00:00.000000

Captura el esquema FINAL que antes vivía como SQL crudo en `SCHEMA`/
`POSTGRES_SCHEMA` de `watchgate/dashboard/backend/db.py`, incluidas las
columnas que solo llegaban vía ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``
en el `init_db()` anterior (`author_login`, `accepted_by`, `accepted_at`,
`findings_json`, `vulnerabilities_score`, `vulnerabilities_skipped`,
`threat_summary_json`, `static_threat_nature` en `pr_scores`;
`logo_data_url` en `ui_settings`) -- este baseline ya las incluye
directamente como columnas normales, no como migraciones incrementales
separadas, porque ese historial de ALTER ya no existe como tal en el
código: era el mecanismo de migración por guardas idempotentes que este
propio cambio sustituye por Alembic.

En un despliegue existente que ya tenía estas tablas de antes de adoptar
Alembic aquí, no se corre `upgrade head` contra esta revisión -- se hace
`alembic -c alembic_dashboard.ini stamp head` una sola vez (ver
docs/despliegue.md), igual que ya se documenta para la Engine DB.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pr_scores",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("semaforo", sa.String(), nullable=False),
        sa.Column("static_score", sa.Integer(), nullable=True),
        sa.Column("static_skipped", sa.Boolean(), nullable=True),
        sa.Column("deps_score", sa.Integer(), nullable=True),
        sa.Column("deps_skipped", sa.Boolean(), nullable=True),
        sa.Column("vulnerabilities_score", sa.Integer(), nullable=True),
        sa.Column("vulnerabilities_skipped", sa.Boolean(), nullable=True),
        sa.Column("reputation_score", sa.Integer(), nullable=True),
        sa.Column("reputation_skipped", sa.Boolean(), nullable=True),
        sa.Column("semantic_score", sa.Integer(), nullable=True),
        sa.Column("semantic_skipped", sa.Boolean(), nullable=True),
        sa.Column("semantic_justification", sa.String(), nullable=True),
        sa.Column("weights_json", sa.String(), nullable=False),
        sa.Column("author_login", sa.String(), nullable=True),
        sa.Column("human_feedback", sa.String(), nullable=True),
        sa.Column("accepted_by", sa.String(), nullable=True),
        sa.Column("accepted_at", sa.String(), nullable=True),
        sa.Column("findings_json", sa.String(), nullable=True),
        sa.Column("threat_summary_json", sa.String(), nullable=False),
        sa.Column("static_threat_nature", sa.String(), nullable=True),
        sa.CheckConstraint(
            "human_feedback IN ('correcto','falso_positivo') OR human_feedback IS NULL",
            name="ck_pr_scores_human_feedback",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("idx_repo_timestamp", "pr_scores", ["repo", "timestamp"], unique=False)

    op.create_table(
        "repo_roles",
        sa.Column("user_login", sa.String(), nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin_organizacion','mantenedor','revisor')",
            name="ck_repo_roles_role",
        ),
        sa.PrimaryKeyConstraint("user_login", "repo"),
    )

    op.create_table(
        "repo_settings",
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("weights_json", sa.String(), nullable=False),
        sa.Column("thresholds_json", sa.String(), nullable=False),
        sa.Column("layers_enabled_json", sa.String(), nullable=False),
        sa.Column("risk_colors_json", sa.String(), nullable=False),
        sa.Column("block_on_high", sa.Boolean(), nullable=False),
        sa.Column("require_feedback_on_high", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("repo"),
    )

    op.create_table(
        "org_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weights_json", sa.String(), nullable=False),
        sa.Column("thresholds_json", sa.String(), nullable=False),
        sa.Column("layers_enabled_json", sa.String(), nullable=False),
        sa.Column("risk_colors_json", sa.String(), nullable=False),
        sa.Column("block_on_high", sa.Boolean(), nullable=False),
        sa.Column("require_feedback_on_high", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_org_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dashboard_users",
        sa.Column("login", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("login"),
    )

    op.create_table(
        "llm_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("api_key", sa.String(), nullable=True),
        sa.Column("monthly_budget_tokens", sa.Integer(), nullable=True),
        sa.Column("max_diff_tokens", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_llm_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ui_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("primary_color", sa.String(), nullable=False),
        sa.Column("accent_color", sa.String(), nullable=False),
        sa.Column("radius", sa.String(), nullable=False),
        sa.Column("font_scale", sa.String(), nullable=False),
        sa.Column("density", sa.String(), nullable=False),
        sa.Column("default_theme", sa.String(), nullable=False),
        sa.Column("logo_data_url", sa.String(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_ui_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("ui_settings")
    op.drop_table("llm_settings")
    op.drop_table("dashboard_users")
    op.drop_table("org_settings")
    op.drop_table("repo_settings")
    op.drop_table("repo_roles")
    op.drop_index("idx_repo_timestamp", table_name="pr_scores")
    op.drop_table("pr_scores")
