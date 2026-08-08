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

    # `Path.is_file()`/`read_bytes()` siguen symlinks por defecto: un
    # symlink dentro de una carpeta de reglas descargada de un repo externo
    # comprometido haría que se hasheara (y luego se copiara al activar) el
    # contenido de un fichero AJENO del filesystem del runner, no el
    # contenido real e inmutable del tag que se está sincronizando -- rompe
    # la garantía central de este mecanismo. Se rechaza explícitamente en
    # vez de seguirlo o ignorarlo en silencio.
    all_entries = sorted(
        directory.rglob("*"), key=lambda p: p.relative_to(directory).as_posix()
    )
    for entry in all_entries:
        if entry.is_symlink():
            raise ValueError(
                f"'{entry}' es un symlink -- no se permite dentro de una carpeta de "
                "reglas a hashear (podría apuntar a contenido ajeno al repo de reglas "
                "sincronizado). Verificación abortada."
            )
    files = [p for p in all_entries if p.is_file()]

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
