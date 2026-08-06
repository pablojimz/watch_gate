"""Genera `docs/validation_report.md` a partir de una ejecución real de la
suite de aceptación (spec §14). No se escribe a mano -- se regenera
ejecutando este script, para que nunca quede desactualizado respecto al
código real:

    poetry run python -m tests.integration.generate_validation_report

Llama de verdad a la API de Gemini para cada caso de `tests/cases/` (mismo
coste que `pytest -m integration`); no se ejecuta en CI por defecto. Con
cientos de casos, se ejecutan en paralelo (hilos, la propia llamada HTTP a
Gemini libera el GIL) para que la tanda completa tarde minutos y no horas.
"""

from __future__ import annotations

import concurrent.futures
import json
from datetime import UTC, datetime
from pathlib import Path

from tests.integration.pipeline_runner import discover_cases, run_full_pipeline

REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "validation_report.md"
RAW_RESULTS_PATH = Path(__file__).resolve().parents[2] / "docs" / "validation_report_raw.json"
_MAX_WORKERS = 6


def _acceptable_semaforos(expected: dict[str, object]) -> set[str]:
    value = expected["semaforo"]
    return {value} if isinstance(value, str) else set(value)  # type: ignore[arg-type]


def _fmt_expected(expected: dict[str, object]) -> str:
    value = expected["semaforo"]
    label = value if isinstance(value, str) else "/".join(value)  # type: ignore[arg-type]
    return f"{label} (min. {expected.get('min_score', 0)})"


def _run_one(case_dir: Path) -> dict[str, object]:
    expected = json.loads((case_dir / "expected.json").read_text())
    try:
        result = run_full_pipeline(case_dir)
    except Exception as exc:  # noqa: BLE001 - un caso roto no debe tumbar toda la tanda
        return {
            "caso": case_dir.name,
            "clase": expected.get("class", "canonico"),
            "dificultad": expected.get("difficulty", "-"),
            "esperado": _fmt_expected(expected),
            "obtenido": "ERROR",
            "score": None,
            "cumple": "ERROR",
            "categoria": "-",
            "justificacion": f"{type(exc).__name__}: {exc}"[:200],
        }
    acceptable = _acceptable_semaforos(expected)
    ok = result.semaforo.value in acceptable and result.score >= expected.get("min_score", 0)
    semantic = result.layer_results.get("semantic")
    return {
        "caso": case_dir.name,
        "clase": expected.get("class", "canonico"),
        "dificultad": expected.get("difficulty", "-"),
        "esperado": _fmt_expected(expected),
        "obtenido": f"{result.semaforo.value} ({result.score})",
        "score": result.score,
        "cumple": "OK" if ok else "DIVERGE",
        "categoria": semantic.category.value if semantic and semantic.category else "-",
        "justificacion": (semantic.justification if semantic else "")[:220],
    }


def _summary_table(rows: list[dict[str, object]]) -> list[str]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for r in rows:
        key = (str(r["clase"]), str(r["dificultad"]))
        groups.setdefault(key, []).append(r)

    lines = ["| Clase | Dificultad | N | OK | % OK |", "|---|---|---:|---:|---:|"]
    for (clase, dificultad), group in sorted(groups.items()):
        n = len(group)
        n_ok = sum(1 for r in group if r["cumple"] == "OK")
        lines.append(f"| {clase} | {dificultad} | {n} | {n_ok} | {100 * n_ok // n}% |")
    return lines


def main() -> None:
    cases = discover_cases()
    # Precarga el modelo de embeddings en el hilo principal, de uno en uno, antes
    # de lanzar el pool: cargarlo por primera vez desde varios hilos a la vez
    # cuelga (deadlock reproducido en la práctica, probablemente en el pool de
    # hilos interno de `tokenizers`). Una vez cargado, `.encode()` concurrente
    # sobre el modelo ya inicializado no ha mostrado el mismo problema.
    from watchgate.core.rag.retriever import _get_embedding_model

    print("Precargando el modelo de embeddings...")
    _get_embedding_model().encode(["precarga"])

    print(f"Ejecutando {len(cases)} casos con {_MAX_WORKERS} hilos en paralelo...")
    rows: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_run_one, case_dir): case_dir.name for case_dir in cases}
        for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            row = future.result()
            rows.append(row)
            print(f"  [{i}/{len(cases)}] {row['caso']}: {row['cumple']} ({row['obtenido']})")

    rows.sort(key=lambda r: (str(r["clase"]), str(r["dificultad"]), str(r["caso"])))
    RAW_RESULTS_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    n_ok = sum(1 for r in rows if r["cumple"] == "OK")
    n_error = sum(1 for r in rows if r["cumple"] == "ERROR")
    diverging = [r for r in rows if r["cumple"] != "OK"]

    lines = [
        "# Informe de validación — suite de aceptación (spec §14)",
        "",
        f"Generado automáticamente el {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} "
        "ejecutando `tests/integration/generate_validation_report.py` contra la API real de "
        "Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. "
        f"Resultados en bruto de cada caso en `docs/validation_report_raw.json`.",
        "",
        f"**Resultado global: {n_ok}/{len(rows)} casos dentro de lo esperado "
        f"({100 * n_ok // len(rows)}%)"
        + (f", {n_error} con error de ejecución" if n_error else "")
        + ".**",
        "",
        "> `static_layer.py`/`deps_layer.py` (Línea 3) siguen sin implementar: el score de "
        "esta suite es la media ponderada renormalizada de `reputation` (0.15) + `semantic` "
        "(0.40) únicamente, no las 4 capas de la memoria §8.",
        "",
        "## Resumen por clase y dificultad",
        "",
        *_summary_table(rows),
        "",
        f"## Casos que divergen de lo esperado ({len(diverging)})",
        "",
        "| Caso | Esperado | Obtenido | Categoría | Justificación (semántica) |",
        "|---|---|---|---|---|",
    ]
    for r in diverging:
        just = str(r["justificacion"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{r['caso']}` | {r['esperado']} | {r['obtenido']} | {r['categoria']} | {just} |"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nEscrito {REPORT_PATH} ({n_ok}/{len(rows)} casos OK, {len(diverging)} divergen)")


if __name__ == "__main__":
    main()
