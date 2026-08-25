"""Como scratchpad/detect_por_capa.py, pero ademas cruza deteccion por capa
con la dificultad (`expected.json["difficulty"]`) de cada caso malicious.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

from tests.integration.pipeline_runner import discover_cases, run_full_pipeline

RAW_PATH = Path(__file__).parent / "detect_por_capa_dificultad_raw.json"
SUMMARY_PATH = Path(__file__).parent / "detect_por_capa_dificultad_resumen.md"
_MAX_WORKERS = 4  # diagnosticado: con 6+ workers, Semgrep (llamado por la
# capa static dentro de cada run_full_pipeline, que ya paraleliza
# internamente hasta 8 procesos semgrep-core por caso) entra en timeout de
# 60s por contención real de CPU (4 cores, 2 procesos uvicorn --reload en
# background ya consumen ~0.77 de un core) -- no tiene relación con el
# chunking/map-reduce de la capa semántica (un caso aislado, sin
# contención, tarda ~13s).

LAYER_NAMES = ["static", "dependencies", "vulnerabilities", "reputation", "semantic"]
DIFFICULTIES = ["easy", "medium", "hard"]


def _malicious_cases() -> list[tuple[Path, str]]:
    """Los 55 casos class=malicious completos (ya no una muestra -- el
    fix de aislamiento de tree-sitter en subproceso hace que los casos
    con ficheros gigantes ya no crasheen el proceso)."""
    cases: list[tuple[Path, str]] = []
    for case_dir in discover_cases():
        expected = json.loads((case_dir / "expected.json").read_text())
        if expected.get("class") != "malicious":
            continue
        cases.append((case_dir, expected.get("difficulty", "-")))
    return cases


def _run_one(case_dir: Path, difficulty: str) -> dict[str, object]:
    try:
        result = run_full_pipeline(case_dir)
    except Exception as exc:  # noqa: BLE001
        return {"caso": case_dir.name, "dificultad": difficulty, "error": f"{type(exc).__name__}: {exc}"[:300]}
    layers: dict[str, object] = {}
    for name in LAYER_NAMES:
        lr = result.layer_results.get(name)
        if lr is None:
            layers[name] = {"presente": False}
            continue
        layers[name] = {
            "presente": True,
            "skipped": lr.skipped,
            "risk_score": lr.risk_score,
            "n_findings": len(lr.findings),
        }
    return {
        "caso": case_dir.name,
        "dificultad": difficulty,
        "score": result.score,
        "semaforo": result.semaforo.value,
        "layers": layers,
    }


def main() -> None:
    from watchgate.core.rag.retriever import _get_embedding_model

    print("Precargando modelo de embeddings...")
    _get_embedding_model().encode(["precarga"])

    cases = _malicious_cases()
    print(f"Ejecutando {len(cases)} casos maliciosos con {_MAX_WORKERS} hilos...")

    rows: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_run_one, c, d): c.name for c, d in cases}
        for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            row = future.result()
            rows.append(row)
            RAW_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
            print(f"  [{i}/{len(cases)}] {row['caso']} ({row['dificultad']}): "
                  f"{row.get('semaforo', row.get('error'))}")

    rows.sort(key=lambda r: str(r["caso"]))
    RAW_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    ok_rows = [r for r in rows if "error" not in r]
    errors = [r for r in rows if "error" in r]

    lines = [
        "# Deteccion por capa x dificultad -- los 55 casos malicious completos",
        "",
        f"Total: {len(rows)} ({len(ok_rows)} ejecutados, {len(errors)} con error)",
        "",
    ]

    # Tabla 1: por capa, global
    lines += ["## Por capa (global)", "", "| Capa | Detectados | % | Skipped |", "|---|---:|---:|---:|"]
    for name in LAYER_NAMES:
        detected = sum(
            1 for r in ok_rows
            if r["layers"].get(name, {}).get("presente")
            and not r["layers"][name].get("skipped")
            and r["layers"][name].get("n_findings", 0) > 0
        )
        skipped = sum(1 for r in ok_rows if r["layers"].get(name, {}).get("skipped"))
        pct = 100 * detected // len(ok_rows) if ok_rows else 0
        lines.append(f"| {name} | {detected}/{len(ok_rows)} | {pct}% | {skipped} |")

    # Tabla 2: por dificultad, resultado agregado final (score/semaforo)
    lines += ["", "## Por dificultad (resultado agregado final)", "",
              "| Dificultad | N | Rojo | Amarillo | Verde | % rojo+amarillo |", "|---|---:|---:|---:|---:|---:|"]
    for diff in DIFFICULTIES:
        group = [r for r in ok_rows if r["dificultad"] == diff]
        if not group:
            continue
        n = len(group)
        rojo = sum(1 for r in group if r["semaforo"] == "rojo")
        amarillo = sum(1 for r in group if r["semaforo"] == "amarillo")
        verde = sum(1 for r in group if r["semaforo"] == "verde")
        pct = 100 * (rojo + amarillo) // n
        lines.append(f"| {diff} | {n} | {rojo} | {amarillo} | {verde} | {pct}% |")

    # Tabla 3: cruce capa x dificultad
    lines += ["", "## Cruce: % detectado por capa, desglosado por dificultad", "",
              "| Capa | " + " | ".join(DIFFICULTIES) + " |", "|---|" + "---:|" * len(DIFFICULTIES)]
    for name in LAYER_NAMES:
        cells = []
        for diff in DIFFICULTIES:
            group = [r for r in ok_rows if r["dificultad"] == diff]
            if not group:
                cells.append("-")
                continue
            detected = sum(
                1 for r in group
                if r["layers"].get(name, {}).get("presente")
                and not r["layers"][name].get("skipped")
                and r["layers"][name].get("n_findings", 0) > 0
            )
            cells.append(f"{detected}/{len(group)} ({100*detected//len(group)}%)")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    if errors:
        lines += ["", "## Casos con error", ""]
        for r in errors:
            lines.append(f"- `{r['caso']}` ({r['dificultad']}): {r['error']}")

    SUMMARY_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nListo. Resumen en {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
