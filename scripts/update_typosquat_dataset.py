#!/usr/bin/env python3
"""Script auxiliar para actualizar las listas de referencia de typosquatting.

Consulta las APIs de PyPI/npm (o fuentes públicas) para actualizar
datasets/typosquat_reference/{pypi,npm,crates,aur}.txt.
"""

from __future__ import annotations

from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets" / "typosquat_reference"


def main() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Directorio de datasets de typosquatting: {DATASET_DIR}")
    for name in ["pypi.txt", "npm.txt", "crates.txt", "aur.txt"]:
        path = DATASET_DIR / name
        if path.exists():
            lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            print(f"  - {name}: {len(lines)} paquetes registrados.")
        else:
            print(f"  - {name}: No existe.")


if __name__ == "__main__":
    main()
