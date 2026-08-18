"""Tests de integración de `_checkout_from_url` contra un repo git+LFS
REAL local (sin red: se usa un remoto `file://`, así que no hace falta
token ni conexión a GitHub).

Reproduce, de punta a punta, los dos bugs concretos que ya se dieron en
producción y que motivaron el diseño actual:
  1. Sin `lfs: true` / Git LFS mal resuelto, se hashea el PUNTERO de texto
     en vez del contenido real de la regla (ver `_assert_no_lfs_pointers`).
  2. Sparse-checkout en modo cone cuela, sin pedirlo, los ficheros sueltos
     de cada carpeta ANCESTRA (aquí vive rules/semgrep/config.yaml, que
     nunca debemos tocar) -- ver el docstring de `_checkout_from_url`.

Se salta automáticamente si `git` o `git-lfs` no están instalados en la
máquina (no debería pasar en CI: ubuntu-latest los trae, y así se
comprobó al construir este flujo -- ver la conversación de depuración
real de sync-rules.yml / reconcile-rules.yml).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import sync_rules as sr  # noqa: E402
from rules_hash import compute_dir_hash  # noqa: E402

_GIT_AVAILABLE = shutil.which("git") is not None
_GIT_LFS_AVAILABLE = shutil.which("git-lfs") is not None or shutil.which("git-lfs.exe") is not None
pytestmark = pytest.mark.skipif(
    not (_GIT_AVAILABLE and _GIT_LFS_AVAILABLE),
    reason="git y/o git-lfs no están instalados en esta máquina",
)


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd} falló: {result.stderr}")
    return result.stdout


@pytest.fixture
def rules_repo_fixture():
    """Construye un repo git+LFS local con la misma forma que el repo de
    reglas real: rules/semgrep/config.yaml (ancestro problemático,
    LFS-tracked), rules/semgrep/custom/python/ (LFS-tracked) y
    dist/yara_scored/webshells/ (LFS-tracked), taggeado."""
    work = Path(tempfile.mkdtemp(prefix="sync_rules_git_lfs_test_"))
    source = work / "source"
    source.mkdir()

    _run(["git", "init", "-q"], source)
    _run(["git", "config", "user.email", "test@example.com"], source)
    _run(["git", "config", "user.name", "Test"], source)
    _run(["git", "lfs", "install", "--local"], source)

    (source / "rules/semgrep").mkdir(parents=True)
    (source / "rules/semgrep/config.yaml").write_text(
        "litellm: config no relacionada\n", encoding="utf-8"
    )

    (source / "rules/semgrep/custom/python").mkdir(parents=True)
    (source / "rules/semgrep/custom/python/rule1.yaml").write_text(
        "regla-python-real", encoding="utf-8"
    )

    (source / "dist/yara_scored/webshells").mkdir(parents=True)
    (source / "dist/yara_scored/webshells/w.yar").write_text("rule webshell {}", encoding="utf-8")

    (source / ".gitattributes").write_text(
        "rules/semgrep/**/*.yaml filter=lfs diff=lfs merge=lfs -text\n"
        "dist/yara_scored/**/*.yar filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    _run(["git", "lfs", "track", "rules/semgrep/**/*.yaml"], source)
    _run(["git", "lfs", "track", "dist/yara_scored/**/*.yar"], source)
    _run(["git", "add", "."], source)
    _run(["git", "commit", "-q", "-m", "init"], source)
    _run(["git", "tag", "v-test"], source)

    yield source

    shutil.rmtree(work, ignore_errors=True)


def test_checkout_resolves_real_lfs_content_not_pointers(rules_repo_fixture, tmp_path):
    """Reproduce el bug original: verifica que tras el checkout disperso el
    contenido es el fichero real, no un puntero LFS de ~130 bytes."""
    dest = tmp_path / "dest"
    patterns = ["rules/semgrep/custom/python", "dist/yara_scored/webshells"]

    sr._checkout_from_url(rules_repo_fixture.as_posix(), "v-test", dest, patterns)

    rule_file = dest / "rules/semgrep/custom/python/rule1.yaml"
    assert rule_file.read_text(encoding="utf-8") == "regla-python-real"
    yar_file = dest / "dist/yara_scored/webshells/w.yar"
    assert yar_file.read_text(encoding="utf-8") == "rule webshell {}"

    # No debe quedar ningún puntero sin resolver en las carpetas pedidas.
    for pattern in patterns:
        sr._assert_no_lfs_pointers(dest / pattern)  # no debe lanzar


def test_checkout_computed_hash_matches_hash_of_original_content(rules_repo_fixture, tmp_path):
    """Round-trip completo: el hash recalculado tras el checkout disperso
    debe coincidir con el que se habría calculado sobre el contenido
    original antes de subirlo -- es la propiedad que hace posible verificar
    por hash contra el manifest publicado."""
    expected_hash = compute_dir_hash(rules_repo_fixture / "rules/semgrep/custom/python")

    dest = tmp_path / "dest"
    sr._checkout_from_url(
        rules_repo_fixture.as_posix(), "v-test", dest, ["rules/semgrep/custom/python"]
    )

    assert compute_dir_hash(dest / "rules/semgrep/custom/python") == expected_hash


def test_cone_mode_leaks_ancestor_file_but_it_stays_unresolved(rules_repo_fixture, tmp_path):
    """Reproduce el segundo bug real: cone mode materializa
    rules/semgrep/config.yaml sin que lo pidamos (vive en una carpeta
    ancestra de la que sí pedimos). Debe quedarse como puntero SIN
    resolver -- nunca se descarga ni se toca -- y el checkout no debe
    fallar por ello (antes fallaba con 'Resource not accessible')."""
    dest = tmp_path / "dest"
    sr._checkout_from_url(
        rules_repo_fixture.as_posix(), "v-test", dest, ["rules/semgrep/custom/python"]
    )

    leaked = dest / "rules/semgrep/config.yaml"
    assert leaked.exists(), (
        "cone mode debería colar config.yaml (si no, el test ya no es representativo)"
    )
    assert b"version https://git-lfs.github.com/spec" in leaked.read_bytes()[:200], (
        "config.yaml debería seguir siendo un puntero LFS sin resolver, nunca contenido real"
    )


def test_assert_no_lfs_pointers_raises_on_unresolved_pointer(rules_repo_fixture, tmp_path):
    """Si mirásemos la carpeta ancestra completa (que el código de
    producción NUNCA hace -- solo mira las carpetas exactas por clave),
    `_assert_no_lfs_pointers` sí debe detectar el puntero sin resolver."""
    dest = tmp_path / "dest"
    sr._checkout_from_url(
        rules_repo_fixture.as_posix(), "v-test", dest, ["rules/semgrep/custom/python"]
    )

    with pytest.raises(RuntimeError, match="PUNTERO de Git LFS sin resolver"):
        sr._assert_no_lfs_pointers(dest / "rules/semgrep")


def test_checkout_with_no_patterns_only_materializes_root_files(rules_repo_fixture, tmp_path):
    dest = tmp_path / "dest"
    sr._checkout_from_url(rules_repo_fixture.as_posix(), "v-test", dest, [])
    assert not (dest / "rules").exists()
    assert (dest / ".gitattributes").exists()
