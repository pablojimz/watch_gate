"""Esquemas Pydantic de la API del dashboard."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from watchgate.core.models import AggregatedResult, Semaforo

RoleName = Literal["admin_organizacion", "mantenedor", "revisor"]
FeedbackValue = Literal["correcto", "falso_positivo"]


class User(BaseModel):
    login: str


class ScoreOut(BaseModel):
    """AggregatedResult enriquecido con id de fila, autor y feedback humano."""

    id: int
    score: int = Field(ge=0, le=100)
    semaforo: Semaforo
    layer_results: dict
    weights_used: dict[str, float]
    pr_id: str
    repo: str
    timestamp: str
    author_login: str | None = None
    human_feedback: FeedbackValue | None = None

    @classmethod
    def from_aggregated(
        cls,
        score_id: int,
        result: AggregatedResult,
        human_feedback: FeedbackValue | None,
        author_login: str | None = None,
    ) -> ScoreOut:
        return cls(
            id=score_id,
            score=result.score,
            semaforo=result.semaforo,
            layer_results={k: v.model_dump() for k, v in result.layer_results.items()},
            weights_used=result.weights_used,
            pr_id=result.pr_id,
            repo=result.repo,
            timestamp=result.timestamp,
            author_login=author_login,
            human_feedback=human_feedback,
        )


class FeedbackIn(BaseModel):
    feedback: FeedbackValue


class RepoRoleIn(BaseModel):
    user_login: str
    repo: str
    role: RoleName


class RepoRoleOut(BaseModel):
    user_login: str
    repo: str
    role: RoleName


class RepoSettings(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "static": 0.25,
            "deps": 0.25,
            "reputation": 0.15,
            "semantic": 0.35,
        }
    )
    thresholds: dict[str, int] = Field(default_factory=lambda: {"amarillo": 34, "rojo": 66})
    layers_enabled: dict[str, bool] = Field(
        default_factory=lambda: {
            "static": True,
            "deps": True,
            "reputation": True,
            "semantic": True,
        }
    )
    risk_colors: dict[str, str] = Field(
        default_factory=lambda: {
            "verde": "#3d9b5f",
            "amarillo": "#d4a017",
            "rojo": "#c23b3b",
        }
    )
    block_on_high: bool = True
    require_feedback_on_high: bool = False
    source: Literal["default", "repo"] = "default"


class IngestScoreIn(BaseModel):
    """Cuerpo para persistir un AggregatedResult desde el adaptador CI."""

    result: AggregatedResult
    author_login: str | None = None


class DevLoginIn(BaseModel):
    login: str
    role: RoleName = "revisor"


class PasswordLoginIn(BaseModel):
    username: str
    password: str


class RepoMetricRow(BaseModel):
    repo: str
    prs: int
    avg_score: float
    verde: int
    amarillo: int
    rojo: int
    feedback_pending: int


class TrendPoint(BaseModel):
    day: str
    avg_score: float
    count: int


class OrgMetrics(BaseModel):
    total_prs: int
    avg_score: float
    repos_count: int
    by_semaforo: dict[str, int]
    feedback_correct: int
    feedback_false_positive: int
    feedback_pending: int
    layer_avg: dict[str, float]
    by_repo: list[RepoMetricRow]
    trend: list[TrendPoint]


LlmProvider = Literal["anthropic", "gemini", "openai", "local"]


class LlmSettingsOut(BaseModel):
    provider: LlmProvider = "anthropic"
    model: str = "claude-sonnet-5"
    base_url: str | None = None
    api_key_set: bool = False
    api_key_masked: str | None = None
    monthly_budget_tokens: int | None = 2_000_000
    max_diff_tokens: int | None = 80_000


class LlmSettingsIn(BaseModel):
    provider: LlmProvider = "anthropic"
    model: str = "claude-sonnet-5"
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    monthly_budget_tokens: int | None = 2_000_000
    max_diff_tokens: int | None = 80_000

class UiSettings(BaseModel):
    primary_color: str = "#3b6ea5"
    accent_color: str = "#5b7c99"
    radius: Literal["none", "sm", "md", "lg"] = "md"
    font_scale: Literal["sm", "md", "lg"] = "md"
    density: Literal["compact", "comfortable"] = "comfortable"
    default_theme: Literal["light", "dark", "system"] = "system"
