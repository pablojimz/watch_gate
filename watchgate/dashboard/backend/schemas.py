"""Esquemas Pydantic de la API del dashboard."""

from __future__ import annotations

import ipaddress
import os
import urllib.parse
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from watchgate.core.models import AggregatedResult, Semaforo

RoleName = Literal["admin_organizacion", "mantenedor", "revisor"]
FeedbackValue = Literal["correcto", "falso_positivo"]


def normalize_login(value: str) -> str:
    """Forma canónica de un login: sin espacios de sobra y en minúsculas.

    Punto único de normalización para que "Alice", "alice" y " alice " sean
    siempre el mismo usuario en todo el sistema (login local, dev-login,
    OAuth GitHub/OIDC, y el campo de texto libre que un admin escribe en
    Configuración → Accesos para asignar un rol) -- sin esto, la misma
    persona podía acabar duplicada por una diferencia de mayúsculas o un
    espacio, ya que `repo_roles`/`dashboard_users` comparan el string tal
    cual. Se aplica tanto en los esquemas de entrada (ver validadores más
    abajo) como en las funciones de `db.py` que reciben un login, para que
    la garantía no dependa de que el caller pase siempre por un esquema.
    """
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("El nombre de usuario no puede estar vacío")
    return normalized


class User(BaseModel):
    login: str


class ScoreOut(BaseModel):
    """AggregatedResult enriquecido con id de fila, autor y feedback humano."""

    id: int
    score: int = Field(ge=0, le=100)
    semaforo: Semaforo
    layer_results: dict[str, Any]
    weights_used: dict[str, float]
    pr_id: str
    repo: str
    timestamp: str
    author_login: str | None = None
    human_feedback: FeedbackValue | None = None
    accepted_by: str | None = None
    accepted_at: str | None = None
    # Conteo de hallazgos por naturaleza ("malicioso"/"vulnerabilidad"/
    # "incertidumbre") agregado de TODAS las capas de la PR -- mismo campo
    # y misma semántica que AggregatedResult.threat_summary, ya usado en
    # el comentario de PR y la salida de consola (ver comment_template.py
    # / formatters/console.py), para que el dashboard muestre el mismo
    # desglose 🚨/⚠️/❓.
    threat_summary: dict[str, int] = Field(default_factory=dict)
    # "open" (por defecto) | "closed" -- ver DashboardPRScore.pr_state. El
    # análisis de rama principal (pr_id="main") siempre queda "open": no es
    # una PR real de GitHub, nunca puede "cerrarse" por polling.
    pr_state: str = "open"

    @classmethod
    def from_aggregated(
        cls,
        score_id: int,
        result: AggregatedResult,
        human_feedback: FeedbackValue | None,
        author_login: str | None = None,
        accepted_by: str | None = None,
        accepted_at: str | None = None,
        pr_state: str = "open",
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
            accepted_by=accepted_by,
            accepted_at=accepted_at,
            pr_state=pr_state,
            threat_summary=result.threat_summary,
        )


class AcceptScoreOut(ScoreOut):
    """`ScoreOut` + resultado del intento de merge en GitHub que dispara
    `POST /scores/{id}/accept` (ver routers/feedback.py::accept_score).

    `merge_attempted=False` cuando el repo no tiene una conexión de
    GitHub real guardada (score ingerido solo vía POST /scores desde CI
    genérico, o análisis de un hook local sin PR real) -- en ese caso el
    endpoint se comporta exactamente igual que antes de añadir el merge
    automático: solo queda registrada la aceptación humana."""

    merge_attempted: bool = False
    merged: bool | None = None
    merge_message: str | None = None


class FeedbackIn(BaseModel):
    feedback: FeedbackValue


class RepoRoleIn(BaseModel):
    user_login: str
    repo: str
    role: RoleName

    @field_validator("user_login")
    @classmethod
    def _normalize_user_login(cls, value: str) -> str:
        return normalize_login(value)


class RepoRoleOut(BaseModel):
    user_login: str
    repo: str
    role: RoleName
    # "audited" | "managed" (ver MonitoredRepo.monitor_type, Engine DB) --
    # `None` si `repo` no está conectado como repo externo (p. ej. llegó
    # por ingesta directa del adaptador de GitHub Action, sin pasar nunca
    # por "Auditoría Externa"). Ver list_all_roles en routers/feedback.py.
    monitor_type: str | None = None


class DashboardUserOut(BaseModel):
    """Cuenta local (login/contraseña) del Dashboard, independiente de
    GitHub/GitLab -- ver `admin/users` en `routers/feedback.py`. No
    incluye el hash de contraseña (nunca viaja de vuelta al cliente)."""

    login: str
    display_name: str


class DashboardUserCreate(BaseModel):
    login: str
    display_name: str
    password: str = Field(min_length=8, description="Mínimo 8 caracteres")
    # Ambos opcionales: si se rellenan los dos, el alta asigna ese rol
    # inicial en el mismo paso (vía el `upsert_role` ya existente, no
    # lógica nueva) -- sin repetir el viaje aparte a la gestión de roles
    # por repo para el caso más común (usuario nuevo que solo necesita
    # acceso a un repo). Esa gestión separada se mantiene igual para
    # cambios posteriores o roles en más repos.
    repo: str | None = None
    role: RoleName | None = None

    @field_validator("login")
    @classmethod
    def _normalize_login(cls, value: str) -> str:
        return normalize_login(value)


class RepoSettings(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "static": 0.25,
            "deps": 0.15,
            "vulnerabilities": 0.10,
            "reputation": 0.15,
            "semantic": 0.35,
        }
    )
    thresholds: dict[str, int] = Field(default_factory=lambda: {"amarillo": 34, "rojo": 66})
    layers_enabled: dict[str, bool] = Field(
        default_factory=lambda: {
            "static": True,
            "deps": True,
            "vulnerabilities": True,
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


class CiConfigOut(BaseModel):
    """Configuración de un repo lista para que la Action la aplique.

    Subconjunto de RepoSettings + LlmSettingsOut (org-wide) relevante para
    `watchgate.config.WatchGateConfig` -- deliberadamente NO incluye
    risk_colors/require_feedback_on_high (solo tienen sentido para la UI del
    dashboard, la Action no hace nada con ellos) ni la API key del LLM (la
    Action usa su propio secreto de CI, esto nunca viaja por HTTP). Las
    claves de `weights`/`thresholds` siguen la convención propia del
    dashboard ("deps"/"amarillo"/"rojo") -- traducirlas a la del motor
    ("dependencies"/"yellow"/"red") es responsabilidad de quien consuma este
    endpoint, no de este esquema.
    """

    weights: dict[str, float]
    thresholds: dict[str, int]
    layers_enabled: dict[str, bool]
    block_on_high: bool
    monthly_budget_tokens: int | None
    max_diff_tokens: int | None


class DevLoginIn(BaseModel):
    login: str
    role: RoleName = "revisor"

    @field_validator("login")
    @classmethod
    def _normalize_login(cls, value: str) -> str:
        return normalize_login(value)


class PasswordLoginIn(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        return normalize_login(value)


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


class AgentMetricRow(BaseModel):
    agent_id: str
    tokens_used: int
    analyses_count: int
    avg_score: float


class AgentUsageMetrics(BaseModel):
    total_tokens_used: int
    agents_count: int
    by_agent: list[AgentMetricRow]
    # Proveedor/modelo que analiza de verdad -- config de todo el
    # despliegue (WATCHGATE_LLM_PROVIDER/_MODEL), no por agente: WatchGate
    # usa siempre el mismo LLM para su propio análisis semántico,
    # independientemente de qué agente externo llamó a la API. Se muestra
    # aquí porque "qué modelo estamos usando" es justo lo que alguien
    # mirando esta tabla espera encontrar (confundido antes con la
    # columna "Agente / Identificador", que es otra cosa).
    llm_provider: str
    llm_model: str


def validate_github_api_url(value: str | None) -> str:
    if not value or not value.strip():
        return "https://api.github.com"
    val = value.strip()
    parsed = urllib.parse.urlparse(val)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("github_api_url debe comenzar con http:// o https://")

    hostname = (parsed.hostname or "").lower()
    dev_mode = os.environ.get("WATCHGATE_DASHBOARD_DEV_MODE", "1") == "1"
    if not dev_mode:
        if hostname in ("localhost", "127.0.0.1", "::1", "169.254.169.254"):
            raise ValueError("No se permiten URLs locales o de metadatos en modo producción")
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None

        if ip and (ip.is_private or ip.is_loopback or ip.is_link_local):
            raise ValueError("No se permiten direcciones IP privadas/locales en modo producción")
    return val


LlmProvider = Literal["anthropic", "gemini", "openai", "local"]


class LlmSettingsOut(BaseModel):
    provider: LlmProvider = "anthropic"
    model: str = "claude-sonnet-5"
    base_url: str | None = None
    api_key_set: bool = False
    api_key_masked: str | None = None
    monthly_budget_tokens: int | None = 2_000_000
    max_diff_tokens: int | None = 80_000
    github_api_url: str = "https://api.github.com"
    github_token_set: bool = False
    github_token_masked: str | None = None


class LlmSettingsIn(BaseModel):
    provider: LlmProvider = "anthropic"
    model: str = "claude-sonnet-5"
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    monthly_budget_tokens: int | None = 2_000_000
    max_diff_tokens: int | None = 80_000
    github_api_url: str | None = "https://api.github.com"
    github_token: str | None = None
    clear_github_token: bool = False

    @field_validator("github_api_url")
    @classmethod
    def _validate_github_api_url(cls, value: str | None) -> str | None:
        return validate_github_api_url(value)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, description="Mínimo 8 caracteres")


class MyRepoRole(BaseModel):
    repo: str
    role: RoleName


class UserSettingsOut(BaseModel):
    login: str
    display_name: str
    # Rol más alto agregado de todos los repos (compatibilidad con lo que
    # ya consumía el frontend) -- `repo_roles` de abajo es el desglose
    # completo, un elemento por repo, para "en qué repos soy qué".
    role: RoleName
    repo_roles: list[MyRepoRole] = Field(default_factory=list)
    github_api_url: str = "https://api.github.com"
    github_token_set: bool = False
    github_token_masked: str | None = None
    ui_settings: UiSettings | None = None


class UserSettingsIn(BaseModel):
    display_name: str | None = None
    github_api_url: str | None = "https://api.github.com"
    github_token: str | None = None
    clear_github_token: bool = False
    ui_settings: UiSettings | None = None

    @field_validator("github_api_url")
    @classmethod
    def _validate_github_api_url(cls, value: str | None) -> str | None:
        return validate_github_api_url(value)


# Cap del logo como data: URL embebida directamente en ui_settings (nunca un
# fichero en disco/objeto en la nube -- no hay almacenamiento de assets en
# el dashboard todavía). ~400_000 caracteres de base64 son ~290 KB reales,
# de sobra para un logo y lo bastante bajo para no inflar cada respuesta de
# /api/settings/ui ni el propio favicon en cada carga del dashboard.
_MAX_LOGO_DATA_URL_LENGTH = 400_000


class UiSettings(BaseModel):
    primary_color: str = "#3b6ea5"
    accent_color: str = "#5b7c99"
    radius: Literal["none", "sm", "md", "lg"] = "md"
    font_scale: Literal["sm", "md", "lg"] = "md"
    density: Literal["compact", "comfortable"] = "comfortable"
    default_theme: Literal["light", "dark", "system"] = "system"
    logo_data_url: str | None = Field(default=None, max_length=_MAX_LOGO_DATA_URL_LENGTH)

    @field_validator("logo_data_url")
    @classmethod
    def _validate_logo_data_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.startswith("data:image/"):
            raise ValueError("logo_data_url debe ser una data URL de imagen (data:image/...)")
        return value
