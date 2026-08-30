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


class ThreatNature(str, Enum):
    VULNERABILITY = "vulnerabilidad"
    MALICIOUS = "malicioso"
    UNCERTAIN = "incertidumbre"


class Finding(BaseModel):
    file_path: str
    line: int | None = None
    end_line: int | None = None
    rule_id: str
    message: str
    severity: str = "warning"  # "error", "warning", "info"
    threat_nature: ThreatNature = ThreatNature.VULNERABILITY


def compute_dominant_threat_nature(findings: list[Finding]) -> ThreatNature | None:
    """Calcula la naturaleza de amenaza dominante a partir de una lista de hallazgos.

    Jerarquía estricta: MALICIOUS > VULNERABILITY > UNCERTAIN.
    Devuelve None si la lista está vacía.
    """
    if not findings:
        return None
    natures = {f.threat_nature for f in findings}
    if ThreatNature.MALICIOUS in natures:
        return ThreatNature.MALICIOUS
    if ThreatNature.VULNERABILITY in natures:
        return ThreatNature.VULNERABILITY
    if ThreatNature.UNCERTAIN in natures:
        return ThreatNature.UNCERTAIN
    return None


class LayerResult(BaseModel):
    layer_name: str
    risk_score: int = Field(ge=0, le=100)
    justification: str
    findings: list[Finding] = Field(default_factory=list)
    category: RiskCategory | None = None  # solo la capa semántica lo rellena
    confidence: Confidence | None = None
    threat_nature: ThreatNature | None = None  # naturaleza dominante
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
    effective_weights: dict[str, float] = Field(default_factory=dict)
    pr_id: str
    repo: str
    timestamp: str  # ISO 8601
    threat_summary: dict[str, int] = Field(
        default_factory=lambda: {
            ThreatNature.MALICIOUS.value: 0,
            ThreatNature.VULNERABILITY.value: 0,
            ThreatNature.UNCERTAIN.value: 0,
        }
    )


class ReputationMetadata(BaseModel):
    """Contrato exacto que el adaptador debe rellenar (spec §6)."""

    author_login: str | None
    author_account_age_days: int | None
    author_prior_contributions_to_repo: int
    commit_email_matches_verified_email: bool
    commit_is_signed: bool
    signing_key_seen_before_for_login: bool | None  # None si no aplica (no firmado)
    repo_has_history_of_signed_commits: bool
    author_public_repos: int | None = None
    author_followers: int | None = None
    # A diferencia de los campos de arriba, esto NO lo rellena el adaptador
    # de GitHub (no tiene forma de saberlo -- es historial propio de
    # WatchGate, no de la plataforma): lo rellena la capa de persistencia
    # del Dashboard (dashboard/backend/tasks.py, vía
    # db.py::author_has_prior_high_risk_pr) consultando si este mismo autor
    # ya tuvo, en cualquier repo, un PR anterior con score > 70. Por eso el
    # default es False -- "no se ha comprobado o no hay historial", nunca
    # "limpio confirmado".
    author_has_prior_high_risk_pr: bool = False
