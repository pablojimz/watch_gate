#!/usr/bin/env python3
"""Cálculo determinista del hash de integridad de una carpeta de reglas.

Este módulo replica EXACTAMENTE el método usado por
`scripts/build_release_manifest.py` en el repo privado de reglas
(pablojimz/Repo-reglas-SEMGREP-y-YARA) para que el hash calculado aquí,
sobre el contenido descargado, sea comparable byte a byte con el hash
publicado en `manifest.json` / en el payload del repository_dispatch:

    1. Listar recursivamente los ficheros de la carpeta.
    2. Ordenarlos alfabéticamente por su ruta relativa (POSIX, '/').
    3. Concatenar su contenido binario, SIN separadores entre ficheros.
    4. Calcular SHA-256 sobre esa concatenación.

Se aísla en un módulo aparte (sin dependencias de red/git) para poder
testearlo unitariamente sin necesidad de credenciales ni de clonar nada
(ver tests/unit/test_rules_hash.py).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

HASH_PREFIX = "sha256:"


def compute_dir_hash(directory: Path) -> str:
    """Calcula el hash determinista de todos los ficheros bajo `directory`.

    Devuelve el hash con el mismo formato "sha256:<hex>" que usa el
    manifest publicado, para poder comparar directamente por igualdad
    de cadena (ver `normalize_hash` para el lado que compara).
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"No existe la carpeta a hashear: {directory}")

    files = sorted(
        (p for p in directory.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(directory).as_posix(),
    )

    digest = hashlib.sha256()
    for file_path in files:
        digest.update(file_path.read_bytes())

    return f"{HASH_PREFIX}{digest.hexdigest()}"


def normalize_hash(value: str) -> str:
    """Normaliza un hash del manifest para comparar sin importar si lleva
    el prefijo "sha256:" o no (defensivo ante variaciones de formato entre
    versiones del manifest)."""
    value = value.strip().lower()
    if value.startswith(HASH_PREFIX):
        value = value[len(HASH_PREFIX) :]
    return value


def hashes_match(computed: str, expected: str) -> bool:
    """Compara dos hashes ignorando el prefijo "sha256:" si está presente."""
    return normalize_hash(computed) == normalize_hash(expected)
