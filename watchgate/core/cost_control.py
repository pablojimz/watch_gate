"""Control de coste de la capa semántica (spec §8, A.3.3)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from watchgate.core.models import FileChange, LayerResult, NormalizedDiff

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
_CHARS_PER_TOKEN_ESTIMATE = 4  # aproximación conservadora sin depender de un tokenizer externo


def diff_hash(diff: NormalizedDiff) -> str:
    """Hash determinista del diff: el mismo diff exacto (tras un rebase sin
    cambios de contenido) produce el mismo hash."""
    payload = json.dumps(diff.model_dump(), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CostController:
    def __init__(self, db_path: str, max_diff_tokens: int, monthly_budget_tokens: int) -> None:
        self.db_path = db_path
        self.max_diff_tokens = max_diff_tokens
        self.monthly_budget_tokens = monthly_budget_tokens
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- Tokens ----------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """Estimación de tokens sin depender de un tokenizer externo del
        proveedor: ~4 caracteres por token (aproximación estándar para
        texto en inglés/código; conservadora para español)."""
        if not text:
            return 0
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

    def get_cached(self, diff_hash_value: str) -> dict[str, object] | None:
        row = self._conn.execute(
            "SELECT output_json FROM semantic_cache WHERE diff_hash = ?", (diff_hash_value,)
        ).fetchone()
        if row is None:
            return None
        result: dict[str, object] = json.loads(row[0])
        return result

    def store_cached(self, diff_hash_value: str, output: dict[str, object]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO semantic_cache (diff_hash, output_json, created_at) "
            "VALUES (?, ?, ?)",
            (diff_hash_value, json.dumps(output), datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    # -- Presupuesto mensual ------------------------------------------------

    def _current_month(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    def record_usage(self, repo: str, tokens_used: int) -> None:
        month = self._current_month()
        self._conn.execute(
            """
            INSERT INTO token_usage (repo, month, tokens_used) VALUES (?, ?, ?)
            ON CONFLICT(repo, month) DO UPDATE SET tokens_used = tokens_used + excluded.tokens_used
            """,
            (repo, month, tokens_used),
        )
        self._conn.commit()

    def budget_remaining(self, repo: str) -> int:
        month = self._current_month()
        row = self._conn.execute(
            "SELECT tokens_used FROM token_usage WHERE repo = ? AND month = ?", (repo, month)
        ).fetchone()
        used = row[0] if row else 0
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
