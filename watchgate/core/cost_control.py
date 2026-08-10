"""Control de coste de la capa semántica (spec §8, A.3.3)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, final

try:
    import tiktoken
except ImportError:
    tiktoken = None

from watchgate.core.layers._semantic.client import SemanticOutput
from watchgate.core.models import FileChange, LayerResult, NormalizedDiff

logger = logging.getLogger("watchgate.core.cost_control")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS semantic_cache (
    diff_hash TEXT PRIMARY KEY,
    output_json TEXT,
    created_at DATETIME
);
CREATE TABLE IF NOT EXISTS token_usage (
    repo TEXT,
    month TEXT,
    tokens_used INTEGER,
    PRIMARY KEY (repo, month)
);
"""

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
_encoder: tiktoken.Encoding | None = None
_encoder_load_failed = False


def _get_encoder() -> Any | None:
    """`None` si tiktoken no está disponible o no pudo cargar el encoding."""
    global _encoder, _encoder_load_failed
    if tiktoken is None or _encoder_load_failed:
        return None
    if _encoder is not None:
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
    _conn: sqlite3.Connection | None
    _lock: threading.Lock

    def __init__(
        self, db_path: str, max_diff_tokens: int, monthly_budget_tokens: int | None
    ) -> None:
        self.db_path = db_path
        self.max_diff_tokens = max_diff_tokens
        self.monthly_budget_tokens = monthly_budget_tokens
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + Lock: orchestrator.py ejecuta las capas en
        # un ThreadPoolExecutor, así que esta instancia se usa desde un hilo
        # distinto al que la construyó. El timeout=30.0 previene bloqueos de SQLite.
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        self._lock = threading.Lock()
        with self._lock:
            _ = self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("CostController se ha cerrado.")
        return self._conn

    def __enter__(self) -> CostController:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None

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
        conn = self._get_conn()
        with self._lock:
            row: tuple[str] | None = conn.execute(
                "SELECT output_json FROM semantic_cache WHERE diff_hash = ?", (diff_hash_value,)
            ).fetchone()
        if row is None:
            return None
        raw_json = str(row[0])
        return SemanticOutput.model_validate(json.loads(raw_json))

    def store_cached(self, diff_hash_value: str, output: SemanticOutput) -> None:
        conn = self._get_conn()
        with self._lock:
            _ = conn.execute(
                """
                INSERT OR REPLACE INTO semantic_cache (diff_hash, output_json, created_at)
                VALUES (?, ?, ?)
                """,
                (diff_hash_value, output.model_dump_json(), datetime.now(UTC).isoformat()),
            )
            conn.commit()

    # -- Presupuesto mensual ------------------------------------------------

    def _current_month(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    def record_usage(self, repo: str, tokens_used: int) -> None:
        month = self._current_month()
        conn = self._get_conn()
        with self._lock:
            _ = conn.execute(
                """
                INSERT INTO token_usage (repo, month, tokens_used) VALUES (?, ?, ?)
                ON CONFLICT(repo, month) DO UPDATE SET
                    tokens_used = tokens_used + excluded.tokens_used
                """,
                (repo, month, tokens_used),
            )
            conn.commit()

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
        conn = self._get_conn()
        with self._lock:
            row: tuple[int] | None = conn.execute(
                "SELECT tokens_used FROM token_usage WHERE repo = ? AND month = ?", (repo, month)
            ).fetchone()
        used = int(row[0]) if row else 0
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
