"""Prompt de sistema y construcción del prompt de usuario (§7.1)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchgate.core.models import FileChange, NormalizedDiff
from watchgate.core.rag.retriever import RetrievedFragment

FEW_SHOT_DIR = Path(__file__).resolve().parents[4] / "datasets" / "few_shot"

SYSTEM_PROMPT = """Eres un analista de seguridad de cadena de suministro de software.
Tu única tarea es evaluar si el cambio de código (diff) que se te presenta tiene
intención maliciosa, con independencia de quién parezca haberlo firmado: los
atacantes pueden falsificar nombre y correo de autor para simular continuidad
con el historial del proyecto. Evalúa el CONTENIDO del cambio, no la reputación
aparente del autor (esa señal la evalúa otro componente del sistema).

Contexto del proyecto:
- Tipo de proyecto: {project_type}
- Lenguaje(s) principal(es): {languages}
- Resumen de actividad reciente: {recent_activity_summary}

Casos de ataque conocidos recuperados como referencia (pueden no ser relevantes,
úsalos solo si el patrón realmente coincide):
{rag_context}

Debes responder ÚNICAMENTE con un objeto JSON que cumpla exactamente este esquema,
sin texto adicional antes o después:
{{
  "risk_score": <entero 0-100>,
  "category": <uno de: "exfiltracion", "backdoor", "ofuscacion", "escalada_privilegios", "ninguna">,
  "justification": "<una frase en español, concreta, citando la línea o construcción exacta del diff>",
  "confidence": <uno de: "alta", "media", "baja">
}}
"""


def load_few_shot_examples(few_shot_dir: Path = FEW_SHOT_DIR) -> list[dict[str, Any]]:
    """Carga dinámicamente los ejemplos few-shot de datasets/few_shot/*.json,
    cada fichero con forma {"diff_summary": str, "expected_output": {...}}."""
    if not few_shot_dir.is_dir():
        return []
    examples = []
    for path in sorted(few_shot_dir.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            examples.append(json.load(f))
    return examples


FEW_SHOT_EXAMPLES: list[dict[str, Any]] = load_few_shot_examples()


_VERDICT_LABELS = {
    "true_positive": "confirmado por revisión humana como riesgo real",
    "false_positive": "confirmado por revisión humana como falso positivo",
}

# Solapes más cortos que esto casi seguro son ruido (una palabra suelta
# coincidiendo por azar), no el solape real de chunking de indexer.py.
_MIN_MEANINGFUL_OVERLAP_CHARS = 20


def _strip_known_overlap(previous_texts: list[str], text: str) -> str:
    """Optimización de tokens sin perder contexto: si `text` comparte texto
    con un fragmento ya renderizado del mismo caso (chunks adyacentes del
    mismo documento, por el solape deliberado de `_CHUNK_OVERLAP_CHARS` en
    `indexer.py`), quita esa parte repetida. El contenido no cambia -- esas
    frases ya están en el prompt una vez -- solo se deja de enviar dos veces.

    La recuperación por similitud no garantiza el orden del documento: el
    fragmento ya visto puede ser el que va *antes* (su final se repite al
    principio de `text`) o el que va *después* (su principio se repite al
    final de `text`) -- se comprueban ambas direcciones.
    """
    best_prefix_overlap = 0
    best_suffix_overlap = 0
    for previous in previous_texts:
        max_check = min(len(previous), len(text))
        for overlap_len in range(max_check, _MIN_MEANINGFUL_OVERLAP_CHARS - 1, -1):
            if previous.endswith(text[:overlap_len]):
                best_prefix_overlap = max(best_prefix_overlap, overlap_len)
                break
        for overlap_len in range(max_check, _MIN_MEANINGFUL_OVERLAP_CHARS - 1, -1):
            if previous.startswith(text[-overlap_len:]):
                best_suffix_overlap = max(best_suffix_overlap, overlap_len)
                break

    # Si coinciden ambos extremos, nos quedamos con el recorte mayor (más
    # tokens ahorrados) -- en la práctica no suelen darse los dos a la vez.
    if best_prefix_overlap >= best_suffix_overlap and best_prefix_overlap:
        return text[best_prefix_overlap:].lstrip()
    if best_suffix_overlap:
        return text[:-best_suffix_overlap].rstrip()
    return text


def _normalize_whitespace(text: str) -> str:
    """Colapsa líneas en blanco repetidas y espacios finales de línea en
    prosa/markdown (nunca en el diff bajo revisión, eso no se toca). Mismo
    texto legible, menos tokens de puro formato."""
    lines = [line.rstrip() for line in text.splitlines()]
    normalized: list[str] = []
    for line in lines:
        if line == "" and normalized and normalized[-1] == "":
            continue
        normalized.append(line)
    return "\n".join(normalized).strip()


def _render_rag_fragment(fragment: RetrievedFragment, text: str) -> str:
    if fragment.origin == "feedback" and fragment.verdict:
        label = _VERDICT_LABELS.get(fragment.verdict, fragment.verdict)
        return f"- Caso propio «{fragment.case_name}» ({label}): {text}"
    return f"- Caso «{fragment.case_name}»: {text}"


def _render_rag_context(rag_context: list[RetrievedFragment]) -> str:
    if not rag_context:
        return "(sin casos relevantes recuperados)"
    seen_by_case: dict[str, list[str]] = {}
    rendered = []
    for fragment in rag_context:
        previous_texts = seen_by_case.setdefault(fragment.case_name, [])
        deduped = _strip_known_overlap(previous_texts, fragment.text)
        previous_texts.append(fragment.text)
        rendered.append(_render_rag_fragment(fragment, _normalize_whitespace(deduped)))
    return "\n\n".join(rendered)


def _render_few_shot_block(examples: list[dict[str, Any]]) -> str:
    if not examples:
        return ""
    rendered = "\n\n".join(
        f"Diff: {example['diff_summary']}\n"
        f"Respuesta esperada: {json.dumps(example['expected_output'], ensure_ascii=False)}"
        for example in examples
    )
    return f"\n\nEjemplos de referencia (few-shot):\n{rendered}\n"


def _render_dependency_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return ""
    lines = "\n".join(
        f"- {f['name']} ({f['ecosystem']}): {f['vulns_summary']}" for f in findings
    )
    return (
        "\n\nVulnerabilidades conocidas en dependencias nuevas de este PR "
        f"(consulta automática a OSV, no una tool pedida por ti):\n{lines}\n"
    )


def build_system_prompt(
    project_type: str,
    languages: str,
    recent_activity_summary: str,
    rag_context: list[RetrievedFragment],
    few_shot_examples: list[dict[str, Any]] | None = None,
    dependency_findings: list[dict[str, Any]] | None = None,
) -> str:
    base_prompt = SYSTEM_PROMPT.format(
        project_type=project_type,
        languages=languages,
        recent_activity_summary=recent_activity_summary,
        rag_context=_render_rag_context(rag_context),
    )
    examples = FEW_SHOT_EXAMPLES if few_shot_examples is None else few_shot_examples
    return (
        base_prompt
        + _render_dependency_findings(dependency_findings or [])
        + _render_few_shot_block(examples)
    )


def _render_file_change(file_change: FileChange) -> str:
    return f"--- {file_change.path} ({file_change.status.value}) ---\n{file_change.diff_hunk}"


def build_user_prompt(
    diff: NormalizedDiff,
    static_findings_paths: set[str],
    count_tokens: Callable[[str], int],
    max_diff_tokens: int,
) -> str:
    """Regla de construcción del prompt de usuario (§7.1): incluir el diff
    completo si cabe en `max_diff_tokens`; si no, incluir solo los hunks ya
    marcados como sospechosos por la capa estática/dependencias, más un
    resumen textual del resto."""
    commits = "; ".join(diff.commit_messages) or "(sin mensajes)"
    header = f"Repositorio: {diff.repo_path}\nCommits: {commits}\n"
    full_body = "\n".join(_render_file_change(fc) for fc in diff.files)
    full_prompt = f"{header}\n{full_body}"

    if count_tokens(full_prompt) < max_diff_tokens:
        return full_prompt

    truncated_parts = [header]
    for file_change in diff.files:
        if file_change.path in static_findings_paths:
            truncated_parts.append(_render_file_change(file_change))
        else:
            n_lines = file_change.diff_hunk.count("\n") + 1 if file_change.diff_hunk else 0
            truncated_parts.append(
                f"--- {file_change.path}: ... {n_lines} líneas adicionales sin patrones "
                "detectados por análisis estático ..."
            )
    return "\n".join(truncated_parts)
