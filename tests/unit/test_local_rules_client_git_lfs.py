"""Tests de integración de la mecánica real de git+LFS y del clon disperso
PERSISTENTE de `scripts/local_rules_client.py`, contra un repo git+LFS
local (remoto `file://`, sin red ni token real -- mismo patrón que
`tests/unit/test_sync_rules_git_lfs.py`).

A diferencia de `sync_rules._checkout_from_url` (que re-clona en un
tempdir de usar-y-tirar en cada ejecución), aquí el punto central a
probar es justo lo contrario: que el clon en `cache_dir` se REUTILIZA
entre llamadas sucesivas, que el sparse-checkout se AMPLÍA (nunca se
reemplaza, así que no borra del disco claves de una llamada anterior), y
que moverse a un tag nuevo no corrompe el contenido ya resuelto de una
ruta cuyo hash no cambió entre versiones.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import local_rules_client as lrc  # noqa: E402
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
    """Construye un repo git+LFS local con DOS versiones etiquetadas:

    - v1: rules/semgrep/custom/python/ (LFS) + dist/yara_scored/webshells/ (LFS)
    - v2: rules/semgrep/custom/python/ SIN CAMBIOS (mismo contenido, mismo
      hash) + dist/yara_scored/webshells/ con contenido DISTINTO (hash
      distinto)

    Así se puede probar, con un único fixture, tanto el caso "clave sin
    cambios entre versiones" (python) como "clave que sí cambió y hace
    falta re-sincronizar" (webshells).
    """
    work = Path(tempfile.mkdtemp(prefix="local_rules_client_git_lfs_test_"))
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
        "regla-python-v1", encoding="utf-8"
    )
    (source / "dist/yara_scored/webshells").mkdir(parents=True)
    (source / "dist/yara_scored/webshells/w.yar").write_text(
        "rule webshell_v1 {}", encoding="utf-8"
    )

    (source / ".gitattributes").write_text(
        "rules/semgrep/**/*.yaml filter=lfs diff=lfs merge=lfs -text\n"
        "dist/yara_scored/**/*.yar filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    _run(["git", "lfs", "track", "rules/semgrep/**/*.yaml"], source)
    _run(["git", "lfs", "track", "dist/yara_scored/**/*.yar"], source)
    _run(["git", "add", "."], source)
    _run(["git", "commit", "-q", "-m", "v1"], source)
    _run(["git", "tag", "v1"], source)

    # v2: python SIN CAMBIOS; webshells con contenido nuevo.
    (source / "dist/yara_scored/webshells/w.yar").write_text(
        "rule webshell_v2 {}", encoding="utf-8"
    )
    _run(["git", "add", "."], source)
    _run(["git", "commit", "-q", "-m", "v2"], source)
    _run(["git", "tag", "v2"], source)

    yield source

    shutil.rmtree(work, ignore_errors=True)


def test_ensure_repo_cache_clones_once_and_is_idempotent(rules_repo_fixture, tmp_path):
    cache_dir = tmp_path / "cache" / "rules-repo"
    url = rules_repo_fixture.as_posix()

    lrc._ensure_repo_cache_from_url(cache_dir, url)
    assert (cache_dir / ".git").exists()

    # Segunda llamada: no debe re-clonar (si lo intentase, `git clone`
    # sobre un directorio ya no vacío fallaría) -- solo refresca la URL.
    lrc._ensure_repo_cache_from_url(cache_dir, url)
    assert (cache_dir / ".git").exists()


def test_sync_worktree_checks_out_exact_tag_and_resolves_real_lfs_content(
    rules_repo_fixture, tmp_path
):
    cache_dir = tmp_path / "cache" / "rules-repo"
    url = rules_repo_fixture.as_posix()
    lrc._ensure_repo_cache_from_url(cache_dir, url)

    lrc._sync_worktree(cache_dir, "v1", "", [f"{lrc.CUSTOM_PREFIX}/python"])

    rule_file = cache_dir / lrc.CUSTOM_PREFIX / "python" / "rule1.yaml"
    assert rule_file.read_text(encoding="utf-8") == "regla-python-v1"
    lrc._assert_no_lfs_pointers(cache_dir / lrc.CUSTOM_PREFIX / "python")  # no debe lanzar


def test_sync_worktree_expands_sparse_checkout_without_dropping_previous_keys(
    rules_repo_fixture, tmp_path
):
    """Requisito (2): "en cada llamada, ampliar el sparse-checkout" --
    pedir una carpeta nueva no debe hacer desaparecer del disco una
    carpeta ya resuelta en una llamada anterior."""
    cache_dir = tmp_path / "cache" / "rules-repo"
    url = rules_repo_fixture.as_posix()
    lrc._ensure_repo_cache_from_url(cache_dir, url)

    lrc._sync_worktree(cache_dir, "v1", "", [f"{lrc.CUSTOM_PREFIX}/python"])
    assert (cache_dir / lrc.CUSTOM_PREFIX / "python" / "rule1.yaml").exists()

    lrc._sync_worktree(cache_dir, "v1", "", [f"{lrc.YARA_PREFIX}/webshells"])
    # La carpeta pedida en la primera llamada sigue viva tras ampliar el
    # sparse-checkout con una carpeta nueva.
    assert (cache_dir / lrc.CUSTOM_PREFIX / "python" / "rule1.yaml").exists()
    assert (cache_dir / lrc.YARA_PREFIX / "webshells" / "w.yar").exists()


def test_sync_worktree_switching_tags_preserves_unchanged_key_and_updates_changed_key(
    rules_repo_fixture, tmp_path
):
    """Núcleo del mecanismo de caché: al pasar de v1 a v2 (una nueva
    versión activa), la clave "python" -- sin cambios entre ambas
    versiones -- conserva su contenido ya resuelto; la clave "webshells"
    -- que sí cambió -- se resincroniza con el contenido nuevo al
    volver a pedirla explícitamente."""
    cache_dir = tmp_path / "cache" / "rules-repo"
    url = rules_repo_fixture.as_posix()
    lrc._ensure_repo_cache_from_url(cache_dir, url)

    python_pattern = f"{lrc.CUSTOM_PREFIX}/python"
    webshells_pattern = f"{lrc.YARA_PREFIX}/webshells"

    lrc._sync_worktree(cache_dir, "v1", "", [python_pattern, webshells_pattern])
    hash_v1_python = compute_dir_hash(cache_dir / python_pattern)
    webshells_v1_content = (cache_dir / webshells_pattern / "w.yar").read_text(encoding="utf-8")
    assert webshells_v1_content == "rule webshell_v1 {}"

    # Nueva versión activa: python ya está en la caché con el hash
    # correcto (no se vuelve a pedir), webshells sí cambió y se vuelve a
    # sincronizar explícitamente.
    lrc._sync_worktree(cache_dir, "v2", "", [webshells_pattern])

    python_content = (cache_dir / python_pattern / "rule1.yaml").read_text(encoding="utf-8")
    webshells_v2_content = (cache_dir / webshells_pattern / "w.yar").read_text(encoding="utf-8")
    assert compute_dir_hash(cache_dir / python_pattern) == hash_v1_python
    assert python_content == "regla-python-v1"
    assert webshells_v2_content == "rule webshell_v2 {}"


def test_cone_mode_leaks_ancestor_file_but_it_stays_unresolved(rules_repo_fixture, tmp_path):
    """Misma defensa que `sync_rules._checkout_from_url` frente al "cone
    mode leak" (docs/integracion_repo_reglas.md §5.3): rules/semgrep/
    config.yaml se cuela sin pedirlo, pero debe quedarse como puntero LFS
    sin resolver."""
    cache_dir = tmp_path / "cache" / "rules-repo"
    url = rules_repo_fixture.as_posix()
    lrc._ensure_repo_cache_from_url(cache_dir, url)
    lrc._sync_worktree(cache_dir, "v1", "", [f"{lrc.CUSTOM_PREFIX}/python"])

    leaked = cache_dir / "rules/semgrep/config.yaml"
    assert leaked.exists(), (
        "cone mode debería colar config.yaml (si no, el test ya no es representativo)"
    )
    assert b"version https://git-lfs.github.com/spec" in leaked.read_bytes()[:200]


def _hash_at_tag(repo: Path, tag: str, rel_dir: str) -> str:
    """Calcula el hash real del contenido de `rel_dir` TAL COMO ERA en
    `tag`, vía un worktree aparte -- necesario porque, en el fixture, el
    directorio de trabajo de `repo` queda en el estado de la ÚLTIMA
    versión creada (v2), no en el de `tag` (v1)."""
    worktree = repo.parent / f"worktree-{tag}"
    _run(["git", "worktree", "add", "--detach", str(worktree), tag], repo)
    try:
        return compute_dir_hash(worktree / rel_dir)
    finally:
        _run(["git", "worktree", "remove", "--force", str(worktree)], repo)


def test_get_verified_rules_end_to_end_against_real_git_lfs_repo(
    rules_repo_fixture, tmp_path, monkeypatch
):
    """`get_verified_rules()` de punta a punta, con la Releases API
    mockeada (sin red) pero el checkout de Git+LFS real contra el repo
    local del fixture."""
    monkeypatch.setenv(lrc.ENV_REPO_CACHE_DIR, str(tmp_path / "cache" / "rules-repo"))
    monkeypatch.setenv(lrc.ENV_STATE_FILE, str(tmp_path / "cache" / "verified_state.json"))
    monkeypatch.setenv(lrc.ENV_TOKEN, "fake-token")

    real_python_hash = _hash_at_tag(rules_repo_fixture, "v1", "rules/semgrep/custom/python")
    real_webshells_hash = _hash_at_tag(rules_repo_fixture, "v1", "dist/yara_scored/webshells")
    manifest = {
        "version": "v1",
        "hashes": {
            "semgrep": {"custom": {"python": real_python_hash}, "third_party": {}},
            "yara": {"webshells": real_webshells_hash},
        },
    }
    monkeypatch.setattr(
        lrc, "fetch_release_manifest", lambda repo, ref, token, asset: ("v1", b"{}", manifest)
    )
    # `_ensure_repo_cache` calcularía la URL real de GitHub -- se sustituye
    # SOLO la construcción de la URL por la del repo local del fixture,
    # dejando intacta la mecánica real de git+LFS (`_ensure_repo_cache_from_url`).
    fixture_url = rules_repo_fixture.as_posix()

    def _fake_ensure_repo_cache(cache_dir, token):  # noqa: ANN001 -- firma espejo de la real
        lrc._ensure_repo_cache_from_url(cache_dir, fixture_url)

    monkeypatch.setattr(lrc, "_ensure_repo_cache", _fake_ensure_repo_cache)

    result = lrc.get_verified_rules(languages=["python"], include_yara=True)

    assert result.version == "v1"
    assert (result.custom["python"] / "rule1.yaml").read_text(encoding="utf-8") == "regla-python-v1"
    assert (result.yara["webshells"] / "w.yar").read_text(encoding="utf-8") == "rule webshell_v1 {}"
