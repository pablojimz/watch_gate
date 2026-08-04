"""Contratos de datos — base de todo lo demás.

Ver docs/WatchGate_spec_implementacion_IA.md §1 y §6 (ReputationMetadata).
Ningún otro módulo redefine estas clases: AggregatedResult.model_dump_json()
es el único contrato que consumen el comentario de PR y el dashboard.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class FileChange(BaseModel):
    path: str
    old_path: str | None = None  # solo si status == RENAMED
    status: FileStatus
    diff_hunk: str  # texto crudo del hunk unificado
    additions: int
    deletions: int
    is_binary: bool = False
    language: str | None = None  # inferido de la extensión de path; None si no se reconoce


class CommitAuthor(BaseModel):
    name: str
    email: str
    login: str | None = None  # username de plataforma, si el adaptador lo resuelve


class NormalizedDiff(BaseModel):
    base_sha: str
    head_sha: str
    repo_path: str
    files: list[FileChange]
    commit_messages: list[str]
    authors: list[CommitAuthor]


class RiskCategory(str, Enum):
    EXFILTRACION = "exfiltracion"
    BACKDOOR = "backdoor"
    OFUSCACION = "ofuscacion"
    ESCALADA_PRIVILEGIOS = "escalada_privilegios"
    NINGUNA = "ninguna"


class Confidence(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class LayerResult(BaseModel):
    layer_name: str
    risk_score: int = Field(ge=0, le=100)
    justification: str
    category: RiskCategory | None = None  # solo la capa semántica lo rellena
    confidence: Confidence | None = None
    skipped: bool = False  # true si la capa se desactivó o se omitió por presupuesto
    skip_reason: str | None = None
    tool_calls_made: int = 0  # solo semántica; para auditoría de A.3.1


class Semaforo(str, Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"


class AggregatedResult(BaseModel):
    score: int = Field(ge=0, le=100)
    semaforo: Semaforo
    layer_results: dict[str, LayerResult]
    weights_used: dict[str, float]
    pr_id: str
    repo: str
    timestamp: str  # ISO 8601


class ReputationMetadata(BaseModel):
    """Contrato exacto que el adaptador debe rellenar (spec §6)."""

    author_login: str | None
    author_account_age_days: int | None
    author_prior_contributions_to_repo: int
    commit_email_matches_verified_email: bool
    commit_is_signed: bool
    signing_key_seen_before_for_login: bool | None  # None si no aplica (no firmado)
    repo_has_history_of_signed_commits: bool
