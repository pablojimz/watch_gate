"""Tests de `scripts/local_rules_client.py`: la lógica de verificación
"a demanda" para ejecuciones LOCALES del análisis estático, sin tocar red
ni Git real (para la mecánica real de git+LFS y del clon disperso
persistente, ver `tests/unit/test_local_rules_client_git_lfs.py`).

Cubre, con datos en memoria/disco temporal:
  - resolución de claves pedidas (lenguajes / third-party / YARA siempre
    completo), con validación de charset seguro
  - aplanado de hashes del manifest a claves "semgrep.custom.<lenguaje>" etc.
  - `get_verified_rules()` de punta a punta con el checkout de Git
    sustituido por un doble de prueba: camino feliz, caché de verificación
    (segunda llamada NO toca Git), fallo cerrado todo-o-nada (una clave
    manipulada no debe dejar pasar ni las que sí verificaron, ni debe
    actualizar el estado cacheado), hash ausente en el manifest
  - la CLI (`main`): validación de argumentos, código de salida distinto
    de 0 en caso de fallo, impresión de la versión activa y las rutas
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# scripts/ no es un paquete instalado -- se añade su directorio a sys.path
# para poder importar local_rules_client directamente (mismo patrón que
# test_sync_rules.py / test_rules_hash.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import local_rules_client as lrc  # noqa: E402
from rules_hash import compute_dir_hash  # noqa: E402


@pytest.fixture
def tmp_dir():
    path = Path(tempfile.mkdtemp(prefix="local_rules_client_test_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def cache_paths(tmp_dir, monkeypatch):
    """Aísla las dos rutas de caché configurables en un directorio
    temporal, para que ningún test toque `~/.cache/watch_gate` de verdad."""
    repo_cache = tmp_dir / "cache" / "rules-repo"
    state_file = tmp_dir / "cache" / "verified_state.json"
    monkeypatch.setenv(lrc.ENV_REPO_CACHE_DIR, str(repo_cache))
    monkeypatch.setenv(lrc.ENV_STATE_FILE, str(state_file))
    monkeypatch.setenv(lrc.ENV_TOKEN, "fake-token")
    return {"repo_cache": repo_cache, "state_file": state_file}


def _write(base: Path, relpath: str, content: str) -> None:
    file_path = base / relpath
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------
# Configuración de caché por variable de entorno (requisito: nunca
# hardcodear rutas).
# --------------------------------------------------------------------------


def test_repo_cache_dir_defaults_under_home_cache_watch_gate(monkeypatch):
    monkeypatch.delenv(lrc.ENV_REPO_CACHE_DIR, raising=False)
    assert lrc.repo_cache_dir() == Path.home() / ".cache" / "watch_gate" / "rules-repo"


def test_repo_cache_dir_honors_env_override(monkeypatch, tmp_dir):
    override = tmp_dir / "custom-cache"
    monkeypatch.setenv(lrc.ENV_REPO_CACHE_DIR, str(override))
    assert lrc.repo_cache_dir() == override


def test_verified_state_file_defaults_under_home_cache_watch_gate(monkeypatch):
    monkeypatch.delenv(lrc.ENV_STATE_FILE, raising=False)
    expected = Path.home() / ".cache" / "watch_gate" / "verified_state.json"
    assert lrc.verified_state_file() == expected


# --------------------------------------------------------------------------
# Aplanado de hashes / resolución de claves pedidas
# --------------------------------------------------------------------------

MANIFEST_SAMPLE = {
    "version": "v0.0.2",
    "hashes": {
        "semgrep": {
            "custom": {"python": "sha256:h-py", "bash": "sha256:h-bash"},
            "third_party": {
                "trailofbits": {"rs": "sha256:h-rs"},
                "opengrep": {"generic": "sha256:h-generic"},
            },
        },
        "yara": {"webshells": "sha256:h-web", "antidebug_antivm": "sha256:h-anti"},
    },
}


def test_expected_hashes_by_key_flattens_the_full_tree():
    flat = lrc._expected_hashes_by_key(MANIFEST_SAMPLE)
    assert flat == {
        "semgrep.custom.python": "sha256:h-py",
        "semgrep.custom.bash": "sha256:h-bash",
        "semgrep.third_party.trailofbits.rs": "sha256:h-rs",
        "semgrep.third_party.opengrep.generic": "sha256:h-generic",
        "yara.webshells": "sha256:h-web",
        "yara.antidebug_antivm": "sha256:h-anti",
    }


def test_resolve_requests_yara_is_always_complete_when_included():
    langs, tp, yara = lrc._resolve_requests(MANIFEST_SAMPLE, ["python"], [], include_yara=True)
    assert langs == ["python"]
    assert tp == []
    # Todas las categorías publicadas, no solo "webshells" -- nunca
    # selección parcial (requisito (6)).
    assert yara == ["antidebug_antivm", "webshells"]


def test_resolve_requests_yara_is_empty_when_not_included():
    _langs, _tp, yara = lrc._resolve_requests(MANIFEST_SAMPLE, [], [], include_yara=False)
    assert yara == []


def test_resolve_requests_parses_and_dedupes_third_party():
    _langs, tp, _yara = lrc._resolve_requests(
        MANIFEST_SAMPLE, [], ["trailofbits/rs", "trailofbits/rs", "opengrep/generic"], False
    )
    assert tp == [("opengrep", "generic"), ("trailofbits", "rs")]


def test_resolve_requests_rejects_path_traversal_in_language():
    with pytest.raises(ValueError, match="Idioma inválido"):
        lrc._resolve_requests(MANIFEST_SAMPLE, ["../../etc"], [], False)


def test_resolve_requests_rejects_malformed_third_party_entry():
    with pytest.raises(ValueError, match="formato inesperado"):
        lrc._resolve_requests(MANIFEST_SAMPLE, [], ["sin-barra"], False)


def test_resolve_requests_include_all_custom_ignores_languages_argument():
    """Pensado para un llamador (static_layer.py) que no sabe de antemano
    qué lenguajes tienen carpeta custom/ propia -- pide el catálogo
    completo publicado en el manifest, ignorando `languages`."""
    langs, _tp, _yara = lrc._resolve_requests(
        MANIFEST_SAMPLE, ["esto-se-ignora"], [], False, include_all_custom=True
    )
    assert langs == ["bash", "python"]


def test_resolve_requests_include_all_third_party_ignores_third_party_argument():
    _langs, tp, _yara = lrc._resolve_requests(
        MANIFEST_SAMPLE, [], ["esto/se-ignora"], False, include_all_third_party=True
    )
    assert tp == [("opengrep", "generic"), ("trailofbits", "rs")]


# --------------------------------------------------------------------------
# Estado cacheado: carga/escritura acumulativa
# --------------------------------------------------------------------------


def test_load_state_returns_empty_keys_when_file_absent(tmp_dir):
    assert lrc._load_state(tmp_dir / "no-existe.json") == {"keys": {}}


def test_load_state_treats_corrupt_json_as_empty_cache(tmp_dir):
    state_file = tmp_dir / "corrupt.json"
    state_file.write_text("{esto no es json", encoding="utf-8")
    assert lrc._load_state(state_file) == {"keys": {}}


def test_write_state_accumulates_across_separate_calls(tmp_dir):
    state_file = tmp_dir / "state.json"
    lrc._write_state(state_file, "v0.0.2", {"semgrep.custom.python": "sha256:h-py"})
    lrc._write_state(state_file, "v0.0.2", {"yara.webshells": "sha256:h-web"})

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["keys"]["semgrep.custom.python"]["hash"] == "sha256:h-py"
    assert state["keys"]["yara.webshells"]["hash"] == "sha256:h-web"
    assert state["last_verified_version"] == "v0.0.2"


# --------------------------------------------------------------------------
# get_verified_rules() de punta a punta -- checkout sustituido por un doble
# de prueba (la mecánica real de git+LFS/sparse-checkout se prueba en
# test_local_rules_client_git_lfs.py).
# --------------------------------------------------------------------------


def _patch_ensure_repo_cache_creates_dir(monkeypatch) -> None:
    """Doble de `_ensure_repo_cache`: en vez de clonar de verdad, solo crea
    el directorio de caché (los tests de este fichero no ejercitan la
    mecánica real de Git -- ver test_local_rules_client_git_lfs.py)."""

    def _fake(cache_dir, token):  # noqa: ANN001 -- firma espejo de la real
        cache_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(lrc, "_ensure_repo_cache", _fake)


def _fake_sync_worktree_that_materializes(dest_contents: dict[str, str]):
    """Doble de `_sync_worktree`: en vez de tocar Git, escribe directamente
    los ficheros indicados bajo `cache_dir` (mismo patrón que
    `_fake_checkout_that_materializes` en test_sync_rules.py)."""

    def _fake(cache_dir, ref, token, new_patterns):  # noqa: ANN001 -- firma espejo de la real
        for relpath, content in dest_contents.items():
            _write(cache_dir, relpath, content)

    return _fake


def test_get_verified_rules_requires_token(monkeypatch, cache_paths):
    monkeypatch.delenv(lrc.ENV_TOKEN, raising=False)
    with pytest.raises(lrc.RulesClientError, match=lrc.ENV_TOKEN):
        lrc.get_verified_rules(languages=["python"])


def test_get_verified_rules_no_keys_requested_skips_git_entirely(monkeypatch, cache_paths):
    monkeypatch.setattr(
        lrc,
        "fetch_release_manifest",
        lambda repo, ref, token, asset: ("v0.0.2", b"{}", MANIFEST_SAMPLE),
    )
    monkeypatch.setattr(
        lrc, "_ensure_repo_cache", lambda *a, **k: pytest.fail("no debería tocar Git")
    )
    monkeypatch.setattr(
        lrc, "_sync_worktree", lambda *a, **k: pytest.fail("no debería tocar Git")
    )

    result = lrc.get_verified_rules(languages=[], third_party=[], include_yara=False)
    assert result.version == "v0.0.2"
    assert result.custom == {}
    assert result.third_party == {}
    assert result.yara == {}


def test_get_verified_rules_happy_path_verifies_and_caches(monkeypatch, cache_paths):
    python_content = "regla-python-real"

    def fake_manifest(repo, ref, token, asset):
        rel = f"{lrc.CUSTOM_PREFIX}/python"
        real_hash = _hash_of_single_file_dir(rel, python_content)
        manifest = {
            "version": "v0.0.2",
            "hashes": {"semgrep": {"custom": {"python": real_hash}, "third_party": {}}, "yara": {}},
        }
        return "v0.0.2", b"{}", manifest

    monkeypatch.setattr(lrc, "fetch_release_manifest", fake_manifest)
    python_rel = f"{lrc.CUSTOM_PREFIX}/python/r.yaml"
    monkeypatch.setattr(
        lrc, "_sync_worktree", _fake_sync_worktree_that_materializes({python_rel: python_content})
    )
    _patch_ensure_repo_cache_creates_dir(monkeypatch)

    result = lrc.get_verified_rules(languages=["python"], include_yara=False)

    assert result.version == "v0.0.2"
    verified_path = result.custom["python"]
    assert verified_path == cache_paths["repo_cache"] / lrc.CUSTOM_PREFIX / "python"
    assert (verified_path / "r.yaml").read_text(encoding="utf-8") == python_content

    state = json.loads(cache_paths["state_file"].read_text(encoding="utf-8"))
    assert "semgrep.custom.python" in state["keys"]


def _hash_of_single_file_dir(relpath: str, content: str) -> str:
    """Calcula por adelantado, en un directorio temporal aparte, el hash
    real de un contenido de prueba -- para poder fabricar un manifest cuyo
    hash esperado coincida de verdad con lo que el doble de
    `_sync_worktree` va a materializar en el test."""
    scratch = Path(tempfile.mkdtemp(prefix="hash_scratch_"))
    try:
        target = scratch / relpath
        target.mkdir(parents=True)
        (target / "r.yaml").write_text(content, encoding="utf-8")
        return compute_dir_hash(target)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_get_verified_rules_second_call_with_same_hash_is_a_cache_hit(monkeypatch, cache_paths):
    """Requisito (4): una vez verificada una clave, una llamada posterior
    con el MISMO hash esperado no debe volver a tocar Git en absoluto."""
    python_content = "regla-python-real"
    rel = f"{lrc.CUSTOM_PREFIX}/python"
    real_hash = _hash_of_single_file_dir(rel, python_content)
    manifest = {
        "version": "v0.0.2",
        "hashes": {"semgrep": {"custom": {"python": real_hash}, "third_party": {}}, "yara": {}},
    }
    monkeypatch.setattr(
        lrc, "fetch_release_manifest", lambda repo, ref, token, asset: ("v0.0.2", b"{}", manifest)
    )
    _patch_ensure_repo_cache_creates_dir(monkeypatch)
    materialize = _fake_sync_worktree_that_materializes({f"{rel}/r.yaml": python_content})
    monkeypatch.setattr(lrc, "_sync_worktree", materialize)

    first = lrc.get_verified_rules(languages=["python"], include_yara=False)
    assert first.custom["python"].is_dir()

    # Segunda llamada: si tocase Git, el test fallaría explícitamente.
    def _fail_if_called(*_args, **_kwargs):
        pytest.fail("no debería volver a tocar Git en un cache hit")

    monkeypatch.setattr(lrc, "_ensure_repo_cache", _fail_if_called)
    monkeypatch.setattr(lrc, "_sync_worktree", _fail_if_called)

    second = lrc.get_verified_rules(languages=["python"], include_yara=False)
    assert second.custom["python"] == first.custom["python"]


def test_get_verified_rules_fails_closed_when_a_key_is_tampered(monkeypatch, cache_paths):
    """Una clave manipulada (hash no coincide) no debe activar NADA -- ni
    siquiera las claves que sí verificaron en la misma llamada -- ni
    actualizar el estado cacheado."""
    python_content = "regla-python-real"
    python_rel = f"{lrc.CUSTOM_PREFIX}/python"
    real_python_hash = _hash_of_single_file_dir(python_rel, python_content)
    yara_rel = f"{lrc.YARA_PREFIX}/webshells"

    manifest = {
        "version": "v0.0.2",
        "hashes": {
            "semgrep": {"custom": {"python": real_python_hash}, "third_party": {}},
            # Este hash nunca va a coincidir con el contenido real materializado abajo.
            "yara": {"webshells": "sha256:" + "0" * 64},
        },
    }
    monkeypatch.setattr(
        lrc, "fetch_release_manifest", lambda repo, ref, token, asset: ("v0.0.2", b"{}", manifest)
    )
    _patch_ensure_repo_cache_creates_dir(monkeypatch)
    monkeypatch.setattr(
        lrc,
        "_sync_worktree",
        _fake_sync_worktree_that_materializes(
            {f"{python_rel}/r.yaml": python_content, f"{yara_rel}/w.yar": "rule webshell {}"}
        ),
    )

    with pytest.raises(lrc.RulesVerificationError) as excinfo:
        lrc.get_verified_rules(languages=["python"], include_yara=True)

    assert excinfo.value.failed_keys == ["yara.webshells"]
    assert not cache_paths["state_file"].exists(), "no debe escribirse estado si alguna clave falló"


def test_get_verified_rules_fails_closed_when_manifest_has_no_hash_for_key(
    monkeypatch, cache_paths
):
    manifest = {
        "version": "v0.0.2",
        "hashes": {"semgrep": {"custom": {}, "third_party": {}}, "yara": {}},
    }
    monkeypatch.setattr(
        lrc, "fetch_release_manifest", lambda repo, ref, token, asset: ("v0.0.2", b"{}", manifest)
    )
    _patch_ensure_repo_cache_creates_dir(monkeypatch)
    monkeypatch.setattr(
        lrc,
        "_sync_worktree",
        _fake_sync_worktree_that_materializes({f"{lrc.CUSTOM_PREFIX}/python/r.yaml": "algo"}),
    )

    with pytest.raises(lrc.RulesVerificationError, match="semgrep.custom.python"):
        lrc.get_verified_rules(languages=["python"], include_yara=False)


def test_get_verified_rules_rejects_inconsistent_manifest_version(monkeypatch, cache_paths):
    manifest = {
        "version": "v9.9.9",
        "hashes": {"semgrep": {"custom": {}, "third_party": {}}, "yara": {}},
    }
    monkeypatch.setattr(
        lrc, "fetch_release_manifest", lambda repo, ref, token, asset: ("v0.0.2", b"{}", manifest)
    )
    with pytest.raises(lrc.RulesClientError, match="Inconsistencia"):
        lrc.get_verified_rules(languages=[], include_yara=False, ref="v0.0.2")


def test_get_verified_rules_passes_through_ref_argument(monkeypatch, cache_paths):
    seen = {}

    def fake_manifest(repo, ref, token, asset):
        seen["ref"] = ref
        manifest = {
            "version": ref,
            "hashes": {"semgrep": {"custom": {}, "third_party": {}}, "yara": {}},
        }
        return ref, b"{}", manifest

    monkeypatch.setattr(lrc, "fetch_release_manifest", fake_manifest)
    lrc.get_verified_rules(include_yara=False, ref="v0.0.5")
    assert seen["ref"] == "v0.0.5"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_main_requires_at_least_one_key(capsys):
    exit_code = lrc.main([])
    assert exit_code == 2
    assert "no se pidió ninguna clave" in capsys.readouterr().err


def test_main_returns_zero_and_prints_paths_on_success(monkeypatch, capsys):
    fake_result = lrc.VerifiedRules(
        version="v0.0.2",
        custom={"python": Path("/cache/rules-repo/rules/semgrep/custom/python")},
        third_party={},
        yara={"webshells": Path("/cache/rules-repo/dist/yara_scored/webshells")},
    )
    monkeypatch.setattr(lrc, "get_verified_rules", lambda **kwargs: fake_result)

    exit_code = lrc.main(["--language", "python", "--all-yara"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "v0.0.2" in out
    assert "semgrep.custom.python" in out
    assert "yara.webshells" in out


def test_main_returns_nonzero_on_verification_failure(monkeypatch, capsys):
    def raise_verification_error(**kwargs):
        raise lrc.RulesVerificationError(["yara.webshells"], version="v0.0.2")

    monkeypatch.setattr(lrc, "get_verified_rules", raise_verification_error)

    exit_code = lrc.main(["--all-yara"])
    assert exit_code == 1
    assert "yara.webshells" in capsys.readouterr().err


def test_main_returns_nonzero_on_missing_token(monkeypatch, capsys):
    def raise_client_error(**kwargs):
        raise lrc.RulesClientError("falta RULES_REPO_TOKEN")

    monkeypatch.setattr(lrc, "get_verified_rules", raise_client_error)

    exit_code = lrc.main(["--language", "python"])
    assert exit_code == 2
    assert "RULES_REPO_TOKEN" in capsys.readouterr().err


def test_main_accepts_all_languages_and_all_third_party_alone(monkeypatch, capsys):
    """--all-languages / --all-third-party por sí solos ya cuentan como
    "se pidió algo" -- no hace falta combinarlos con --language."""
    fake_result = lrc.VerifiedRules(version="v0.0.2")
    seen_kwargs = {}

    def fake_get_verified_rules(**kwargs):
        seen_kwargs.update(kwargs)
        return fake_result

    monkeypatch.setattr(lrc, "get_verified_rules", fake_get_verified_rules)

    exit_code = lrc.main(["--all-languages", "--all-third-party"])

    assert exit_code == 0
    assert seen_kwargs["include_all_custom"] is True
    assert seen_kwargs["include_all_third_party"] is True
