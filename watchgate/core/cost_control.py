"""Control de coste de la capa semántica (spec §8, A.3.3)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import final

import tiktoken
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from watchgate.core.layers._semantic.client import SemanticOutput
from watchgate.core.models import FileChange, LayerResult, NormalizedDiff
from watchgate.db.models import RepoTokenUsage, SemanticCache

# De watchgate.db.token_cache, NO de watchgate.db.repository: ese módulo
# tiene un import diferido hacia watchgate.dashboard.backend.db
# (check_user_repo_permission) que el contrato de arquitectura
# (tests/unit/test_architecture.py) cuenta como alcanzable incluso estando
# dentro de una función -- importar de aquí evita que watchgate.core
# alcance watchgate.dashboard transitivamente. Ver el docstring de
# watchgate/db/token_cache.py.
from watchgate.db.token_cache import (
    get_repo_token_usage,
    get_semantic_cache,
    record_repo_token_usage,
    set_semantic_cache,
)

logger = logging.getLogger("watchgate.core.cost_control")

# Sin concepto de organización/tenant real (modo CLI/engine local, un solo
# repo analizado directamente) -- reusa el modelo `SemanticCache` de
# `watchgate.db.models` (misma tabla que usa el modo SaaS) fijando siempre
# el mismo `org_id` por defecto, para que el lookup siga siendo solo por
# `diff_hash` (comportamiento idéntico al de antes de esta migración).
_LOCAL_ORG_ID = "default-org"

_TRUNCATION_MARKER = "[...truncado, {n} líneas adicionales sin hallazgos previos...]"
_CHARS_PER_TOKEN_ESTIMATE = 4  # fallback si tiktoken no está disponible (ver estimate_tokens)

# o200k_base es el encoding de los modelos GPT-4o/o200k -- no coincide token a
# token con los tokenizadores reales de Anthropic/Gemini/un modelo local, pero
# es una aproximación real basada en cómo se agrupan las subpalabras, mucho
# más fiel que contar caracteres (que no distingue "aaaa" de código denso en
# símbolos, donde el ratio real de caracteres/token es muy distinto). Mismo
# criterio que ya usa el proyecto hermano de optimización de costes
# (mercedes-uma-hackathon/backend/shared/tools.py). Cacheado a nivel de
# módulo: instanciarlo por llamada sería un coste real evitable (mismo motivo
# que `_get_embedding_model()` en rag/retriever.py).
#
# `import tiktoken` arriba es incondicional a propósito, sin
# `try/except ImportError` -- es una dependencia declarada de verdad en
# pyproject.toml/poetry.lock (`poetry add tiktoken`), no opcional; un
# `try/except` ahí solo cambia `tiktoken` de módulo a `None`, lo que rompe
# mypy contra la anotación `tiktoken.Encoding` de abajo (ya revertido una
# vez en este mismo fichero, ver historial de `cost_control.py`). Lo que sí
# puede fallar de verdad, y por eso el `try/except` de `_get_encoder` sigue
# ahí, es la DESCARGA del fichero de encoding en el primer uso si no hay red.
_encoder: tiktoken.Encoding | None = None
_encoder_load_failed = False


def _get_encoder() -> tiktoken.Encoding | None:
    global _encoder, _encoder_load_failed
    if _encoder is not None or _encoder_load_failed:
        return _encoder
    try:
        _encoder = tiktoken.get_encoding("o200k_base")
    except Exception as exc:  # noqa: BLE001 - fallback deliberado, ver docstring
        _encoder_load_failed = True
        logger.warning(
            "No se pudo cargar el encoding de tiktoken (¿sin red la primera vez?), "
            "usando el heurístico de ~4 caracteres/token: %r",
            exc,
        )
    return _encoder


def diff_hash(diff: NormalizedDiff) -> str:
    """Hash determinista del diff: el mismo diff exacto (tras un rebase sin
    cambios de contenido) produce el mismo hash."""
    payload = json.dumps(diff.model_dump(), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@final
class CostController:
    db_path: str
    max_diff_tokens: int
    monthly_budget_tokens: int | None
    _engine: Engine | None

    def __init__(
        self, db_path: str, max_diff_tokens: int, monthly_budget_tokens: int | None
    ) -> None:
        self.db_path = db_path
        self.max_diff_tokens = max_diff_tokens
        self.monthly_budget_tokens = monthly_budget_tokens
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # Motor SQLAlchemy propio y aislado -- NO el compartido de
        # `watchgate.db.connection` (Engine DB/SaaS): esta es una caché de
        # PROCESO por repositorio/fichero, sin concepto de organización ni
        # tenant. `check_same_thread=False`: orchestrator.py ejecuta las
        # capas en un ThreadPoolExecutor, así que esta instancia se usa
        # desde un hilo distinto al que la construyó. `timeout=30.0`
        # previene bloqueos de SQLite bajo escrituras concurrentes.
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30.0},
        )
        # Solo las dos tablas que este fichero usa de verdad -- `SemanticCache`/
        # `RepoTokenUsage` viven en `SQLModel.metadata` junto con el resto del
        # esquema de la Engine DB, pero este fichero SQLite es su propia base
        # de datos aislada, no la Engine DB compartida (`.watchgate/app.db`):
        # sin `tables=[...]`, `create_all()` intentaría crear TODAS las tablas
        # del esquema (organizations, users, ...) también aquí.
        # `Model.__table__` no está en los stubs de SQLModel (limitación de
        # tipado conocida, ya presente en record_token_usage/
        # record_repo_token_usage) -- no es un error real.
        tables = [
            SemanticCache.__table__,  # type: ignore[attr-defined]
            RepoTokenUsage.__table__,  # type: ignore[attr-defined]
        ]
        SQLModel.metadata.create_all(self._engine, tables=tables)

    def _get_engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("CostController se ha cerrado.")
        return self._engine

    def __enter__(self) -> CostController:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.dispose()
            except Exception:  # noqa: BLE001
                pass
            self._engine = None

    def __del__(self) -> None:
        self.close()

    # -- Tokens ----------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """Estimación real de tokens vía tiktoken (encoding o200k_base) --
        no coincide token a token con el tokenizer real de cada proveedor
        (Anthropic/Gemini/local no publican el suyo), pero es sensiblemente
        más fiel que contar caracteres, sobre todo en código denso en
        símbolos (JSON, minificado, base64), donde el ratio real de
        caracteres/token se aleja mucho de la media del texto en prosa que
        asumía el heurístico anterior. Cae al heurístico de ~4
        caracteres/token solo si tiktoken no pudo cargar su encoding (ver
        `_get_encoder`) -- una estimación de coste no debe poder tumbar el
        análisis por un problema de red puntual."""
        if not text:
            return 0
        encoder = _get_encoder()
        if encoder is not None:
            return max(1, len(encoder.encode(text)))
        return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)

    def _diff_text_size(self, diff: NormalizedDiff) -> int:
        return sum(self.estimate_tokens(f.diff_hunk) for f in diff.files if not f.is_binary)

    def should_truncate(self, diff: NormalizedDiff) -> bool:
        return self._diff_text_size(diff) > self.max_diff_tokens

    def truncate_diff(self, diff: NormalizedDiff, static_findings: list[object]) -> NormalizedDiff:
        """Prioriza los ficheros con hallazgos previos (estática/deps) y
        recorta el resto hasta caber en `max_diff_tokens`."""
        flagged_paths = {getattr(f, "path", f) for f in static_findings}

        def _priority(fc: FileChange) -> int:
            return 0 if fc.path in flagged_paths else 1

        ordered = sorted(diff.files, key=_priority)

        budget = self.max_diff_tokens
        new_files: list[FileChange] = []
        for fc in ordered:
            tokens = self.estimate_tokens(fc.diff_hunk)
            is_flagged = fc.path in flagged_paths

            if tokens <= budget:
                new_files.append(fc)
                budget -= tokens
                continue

            if is_flagged:
                # Los ficheros marcados se incluyen íntegros aunque se pase
                # del presupuesto (prioridad sobre el recorte).
                new_files.append(fc)
                budget = max(0, budget - tokens)
                continue

            # No cabe y no está marcado: se trunca su contenido.
            max_chars = max(0, budget * _CHARS_PER_TOKEN_ESTIMATE)
            truncated_text = fc.diff_hunk[:max_chars]
            remaining_lines = fc.diff_hunk[max_chars:].count("\n")
            truncated_text += "\n" + _TRUNCATION_MARKER.format(n=remaining_lines)
            new_files.append(fc.model_copy(update={"diff_hunk": truncated_text}))
            budget = 0

        return diff.model_copy(update={"files": new_files})

    # -- Caché -------------------------------------------------------------

    def get_cached(self, diff_hash_value: str) -> SemanticOutput | None:
        """Tipado con `SemanticOutput` (no `dict` plano): es el mismo tipo
        que `SemanticLayer` produce y espera de vuelta (`CostControllerLike`
        en `_semantic/layer.py`) -- guardar/leer un `dict` suelto rompía esa
        integración (`store_cached` no podía serializar un `SemanticOutput`
        con `json.dumps` directo; reproducido en la revisión)."""
        with Session(self._get_engine()) as session:
            raw_json = get_semantic_cache(session, diff_hash_value, org_id=_LOCAL_ORG_ID)
        if raw_json is None:
            return None
        return SemanticOutput.model_validate(json.loads(raw_json))

    def store_cached(self, diff_hash_value: str, output: SemanticOutput) -> None:
        with Session(self._get_engine()) as session:
            set_semantic_cache(
                session, diff_hash_value, output.model_dump_json(), org_id=_LOCAL_ORG_ID
            )

    # -- Presupuesto mensual ------------------------------------------------

    def _current_month(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    def record_usage(self, repo: str, tokens_used: int) -> None:
        month = self._current_month()
        with Session(self._get_engine()) as session:
            record_repo_token_usage(session, repo, tokens_used, month=month)

    def budget_remaining(self, repo: str) -> int:
        # None = sin tope configurado (ilimitado a propósito). <= 0 es lo
        # contrario: un operador que fija presupuesto cero quiere decir "no
        # gastes nada", no "sin límite" -- tratarlos igual invertía la
        # intención (bug real, encontrado con should_skip() devolviendo
        # False para monthly_budget_tokens=0, reproducido en la revisión).
        if self.monthly_budget_tokens is None:
            return 999_999_999
        if self.monthly_budget_tokens <= 0:
            return 0
        month = self._current_month()
        with Session(self._get_engine()) as session:
            used = get_repo_token_usage(session, repo, month=month)
        return self.monthly_budget_tokens - used

    def should_skip(self, repo: str) -> bool:
        """Degradación controlada: si no queda presupuesto, la capa semántica
        debe omitirse *antes* de llamar al LLM."""
        return self.budget_remaining(repo) <= 0


def build_skipped_budget_result() -> LayerResult:
    """Resultado estándar cuando se omite la capa semántica por presupuesto
    agotado (spec §8)."""
    return LayerResult(
        layer_name="semantic",
        risk_score=0,
        justification="",
        skipped=True,
        skip_reason="Presupuesto de tokens agotado para este repositorio este mes",
    )
