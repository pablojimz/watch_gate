"""Ejecuta el pipeline completo (5 capas reales, con llamadas reales al LLM)
sobre los casos class="malicious" de tests/cases/ y cuenta, por capa, cuantos
casos produce al menos un Finding (== "detectado" por esa capa).

Uso:
    poetry run python scratchpad/detect_por_capa.py

Escribe resultados incrementales a scratchpad/detect_por_capa_raw.json y un
resumen final a scratchpad/detect_por_capa_resumen.md.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

from tests.integration.pipeline_runner import discover_cases, run_full_pipeline

RAW_PATH = Path(__file__).parent / "detect_por_capa_raw.json"
SUMMARY_PATH = Path(__file__).parent / "detect_por_capa_resumen.md"
_MAX_WORKERS = 8

LAYER_NAMES = ["static", "dependencies", "vulnerabilities", "reputation", "semantic"]


def _malicious_cases() -> list[Path]:
    cases = []
    for case_dir in discover_cases():
        expected = json.loads((case_dir / "expected.json").read_text())
        if expected.get("class") == "malicious":
            cases.append(case_dir)
    return cases


def _run_one(case_dir: Path) -> dict[str, object]:
    try:
        result = run_full_pipeline(case_dir)
    except Exception as exc:  # noqa: BLE001
        return {
            "caso": case_dir.name,
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }
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
            "threat_nature": lr.threat_nature.value if lr.threat_nature else None,
        }
    return {
        "caso": case_dir.name,
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
        futures = {pool.submit(_run_one, c): c.name for c in cases}
        for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            row = future.result()
            rows.append(row)
            RAW_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
            print(f"  [{i}/{len(cases)}] {row['caso']}: "
                  f"{row.get('semaforo', row.get('error'))}")

    rows.sort(key=lambda r: str(r["caso"]))
    RAW_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    errors = [r for r in rows if "error" in r]
    ok_rows = [r for r in rows if "error" not in r]

    lines = [
        "# Deteccion por capa -- casos malicious",
        "",
        f"Total casos: {len(rows)} ({len(ok_rows)} ejecutados, {len(errors)} con error)",
        "",
        "| Capa | Detectados (findings>0) | % sobre ejecutados | Skipped |",
        "|---|---:|---:|---:|",
    ]
    for name in LAYER_NAMES:
        detected = sum(
            1 for r in ok_rows
            if r["layers"].get(name, {}).get("presente")
            and not r["layers"][name].get("skipped")
            and r["layers"][name].get("n_findings", 0) > 0
        )
        skipped = sum(
            1 for r in ok_rows
            if r["layers"].get(name, {}).get("presente")
            and r["layers"][name].get("skipped")
        )
        pct = 100 * detected // len(ok_rows) if ok_rows else 0
        lines.append(f"| {name} | {detected} | {pct}% | {skipped} |")

    if errors:
        lines += ["", "## Casos con error", ""]
        for r in errors:
            lines.append(f"- `{r['caso']}`: {r['error']}")

    SUMMARY_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nListo. Resumen en {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
