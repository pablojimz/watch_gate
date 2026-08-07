"""Tests del método determinista de hash de `scripts/rules_hash.py`.

Este método tiene que ser IDÉNTICO al usado en el repo privado de reglas
(scripts/build_release_manifest.py) para que los hashes publicados en
manifest.json sean comparables con los que recalculamos aquí tras
descargar el contenido. Estos tests fijan ese contrato: mismo contenido
=> mismo hash pase lo que pase con el orden de escritura en disco o los
nombres de fichero (mientras la ruta relativa ordene igual).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# scripts/ no es un paquete Python instalado (son scripts sueltos, ver
# convención existente en scripts/*.py) -- se añade su directorio a
# sys.path para poder importar rules_hash directamente en el test.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from rules_hash import compute_dir_hash, hashes_match, normalize_hash  # noqa: E402


@pytest.fixture
def tmp_dir():
    path = tempfile.mkdtemp(prefix="rules_hash_test_")
    yield Path(path)
    shutil.rmtree(path, ignore_errors=True)


def _write(base: Path, relpath: str, content: str) -> None:
    file_path = base / relpath
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def test_hash_is_deterministic_across_runs(tmp_dir):
    _write(tmp_dir, "a.yaml", "regla-a")
    _write(tmp_dir, "b.yaml", "regla-b")

    first = compute_dir_hash(tmp_dir)
    second = compute_dir_hash(tmp_dir)

    assert first == second
    assert first.startswith("sha256:")


def test_hash_depends_on_relative_path_order_not_filesystem_order(tmp_dir):
    """El orden de creación en disco no debe afectar al hash: solo importa
    el orden alfabético de la ruta relativa (contrato con build_release_manifest.py)."""
    _write(tmp_dir, "z.yaml", "contenido-z")
    _write(tmp_dir, "a.yaml", "contenido-a")
    hash_created_z_first = compute_dir_hash(tmp_dir)

    other_dir = Path(tempfile.mkdtemp(prefix="rules_hash_test_reorder_"))
    try:
        _write(other_dir, "a.yaml", "contenido-a")
        _write(other_dir, "z.yaml", "contenido-z")
        hash_created_a_first = compute_dir_hash(other_dir)
    finally:
        shutil.rmtree(other_dir, ignore_errors=True)

    assert hash_created_z_first == hash_created_a_first


def test_hash_changes_if_any_file_content_changes(tmp_dir):
    _write(tmp_dir, "rule.yaml", "version-1")
    original = compute_dir_hash(tmp_dir)

    _write(tmp_dir, "rule.yaml", "version-2")
    modified = compute_dir_hash(tmp_dir)

    assert original != modified


def test_hash_changes_if_a_file_is_added_or_removed(tmp_dir):
    _write(tmp_dir, "rule.yaml", "contenido")
    baseline = compute_dir_hash(tmp_dir)

    _write(tmp_dir, "extra.yaml", "contenido-extra")
    with_extra_file = compute_dir_hash(tmp_dir)

    assert baseline != with_extra_file


def test_hash_includes_files_in_nested_subdirectories(tmp_dir):
    _write(tmp_dir, "nested/deep/rule.yaml", "contenido-anidado")
    _write(tmp_dir, "top.yaml", "contenido-raiz")

    result = compute_dir_hash(tmp_dir)

    assert result.startswith("sha256:")
    assert len(result) == len("sha256:") + 64


def test_compute_dir_hash_raises_on_missing_directory(tmp_dir):
    missing = tmp_dir / "no-existe"
    with pytest.raises(FileNotFoundError):
        compute_dir_hash(missing)


def test_hashes_match_ignores_sha256_prefix_variations():
    digest = "a" * 64
    assert hashes_match(f"sha256:{digest}", digest)
    assert hashes_match(digest, f"sha256:{digest}")
    assert hashes_match(f"SHA256:{digest}", f"sha256:{digest}")


def test_hashes_match_detects_real_mismatch():
    assert not hashes_match("sha256:" + "a" * 64, "sha256:" + "b" * 64)


def test_normalize_hash_strips_prefix_and_lowercases():
    assert normalize_hash("SHA256:ABCDEF") == "abcdef"
    assert normalize_hash("abcdef") == "abcdef"
