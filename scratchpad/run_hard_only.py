"""Ejecuta solo los casos 'hard' de la muestra y los añade al raw json
existente (los otros 13 ya estan guardados)."""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

from tests.integration.pipeline_runner import discover_cases, run_full_pipeline

RAW_PATH = Path(__file__).parent / "detect_por_capa_dificultad_raw.json"
LAYER_NAMES = ["static", "dependencies", "vulnerabilities", "reputation", "semantic"]


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

    _get_embedding_model().encode(["precarga"])

    existing = json.loads(RAW_PATH.read_text()) if RAW_PATH.exists() else []
    done_names = {r["caso"] for r in existing}

    hard_cases = []
    for case_dir in discover_cases():
        expected = json.loads((case_dir / "expected.json").read_text())
        if expected.get("class") == "malicious" and expected.get("difficulty") == "hard":
            if case_dir.name not in done_names:
                hard_cases.append(case_dir)
        if len(hard_cases) >= 5:
            break

    print(f"Ejecutando {len(hard_cases)} casos hard restantes: {[c.name for c in hard_cases]}")
    rows = list(existing)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_run_one, c, "hard"): c.name for c in hard_cases}
        for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            row = future.result()
            rows.append(row)
            RAW_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
            print(f"  [{i}/{len(hard_cases)}] {row['caso']}: {row.get('semaforo', row.get('error'))}")

    print("Listo.")


if __name__ == "__main__":
    main()
