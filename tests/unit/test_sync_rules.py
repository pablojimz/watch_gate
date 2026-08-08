"""Tests de `scripts/sync_rules.py`: la lógica de sincronización y
verificación de reglas Semgrep/YARA, sin tocar red ni Git real (para eso
ver `tests/unit/test_sync_rules_git_lfs.py`).

Cubre, con datos en memoria/disco temporal:
  - resolución de qué claves sincronizar según el scope (changed vs full)
  - verificación de hash por clave, todo-o-nada (éxito, manipulación,
    hash/carpeta ausente)
  - aplicación del contenido verificado al árbol de watch_gate (incluido
    el remapeo de YARA)
  - acumulación del estado activo (`.rules-state.json`) entre ejecuciones
    parciales
  - comparación manifest remoto vs. estado activo (`cmd_check`)
  - la Releases API (mockeada, sin red real): tag exacto, "latest", tag
    inexistente, asset con nombre erróneo
  - `cmd_sync` de punta a punta con el checkout de Git sustituido por un
    doble de prueba, tanto en el camino feliz como en el de manipulación
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# scripts/ no es un paquete instalado -- se añade su directorio a sys.path
# para poder importar sync_rules directamente (mismo patrón que
# test_rules_hash.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import sync_rules as sr  # noqa: E402
from rules_hash import compute_dir_hash  # noqa: E402


@pytest.fixture
def tmp_dir():
    path = Path(tempfile.mkdtemp(prefix="sync_rules_test_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _write(base: Path, relpath: str, content: str) -> None:
    file_path = base / relpath
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------
# Parseo de third_party_changed y resolución de scope
# --------------------------------------------------------------------------


def test_parse_third_party_entries_splits_vendor_and_carpeta():
    assert sr._parse_third_party_entries(["trailofbits/rs", "opengrep/generic"]) == [
        ("trailofbits", "rs"),
        ("opengrep", "generic"),
    ]


def test_parse_third_party_entries_rejects_malformed_entry():
    with pytest.raises(ValueError, match="formato inesperado"):
        sr._parse_third_party_entries(["sin-barra"])


def test_flatten_third_party_produces_vendor_carpeta_pairs():
    nested = {"trailofbits": {"rs": "h1", "python": "h2"}, "opengrep": {"generic": "h3"}}
    assert sorted(sr._flatten_third_party(nested)) == [
        ("opengrep", "generic"),
        ("trailofbits", "python"),
        ("trailofbits", "rs"),
    ]


MANIFEST_SAMPLE = {
    "version": "v0.0.2",
    "hashes": {
        "semgrep": {
            "custom": {"python": "h-py", "bash": "h-bash"},
            "third_party": {"trailofbits": {"rs": "h-rs"}, "opengrep": {"generic": "h-generic"}},
        },
        "yara": {"webshells": "h-web", "antidebug_antivm": "h-anti"},
    },
}


def test_resolve_scope_keys_changed_uses_only_payload_lists():
    languages, third_party, yara = sr._resolve_scope_keys(
        MANIFEST_SAMPLE, "changed", ["python"], ["trailofbits/rs"]
    )
    assert languages == ["python"]
    assert third_party == [("trailofbits", "rs")]
    # YARA siempre completo, en cualquier scope -- nunca selección parcial.
    assert yara == ["antidebug_antivm", "webshells"]


def test_resolve_scope_keys_full_uses_everything_in_manifest():
    languages, third_party, yara = sr._resolve_scope_keys(MANIFEST_SAMPLE, "full", [], [])
    assert languages == ["bash", "python"]
    assert third_party == [("opengrep", "generic"), ("trailofbits", "rs")]
    assert yara == ["antidebug_antivm", "webshells"]


def test_resolve_scope_keys_rejects_unknown_scope():
    with pytest.raises(ValueError, match="scope desconocido"):
        sr._resolve_scope_keys(MANIFEST_SAMPLE, "parcial", [], [])


def test_build_sparse_patterns_maps_each_key_to_its_repo_path():
    patterns = sr._build_sparse_patterns(["python"], [("trailofbits", "rs")], ["webshells"])
    assert patterns == [
        "rules/semgrep/custom/python",
        "rules/semgrep/third-party/trailofbits/rs",
        "dist/yara_scored/webshells",
    ]


# --------------------------------------------------------------------------
# Verificación por clave (todo-o-nada, nunca un booleano global)
# --------------------------------------------------------------------------


def test_verify_keys_all_pass_when_hashes_match(tmp_dir):
    _write(tmp_dir, "rules/semgrep/custom/python/r.yaml", "regla-python")
    _write(tmp_dir, "dist/yara_scored/webshells/w.yar", "rule w {}")
    manifest = {
        "hashes": {
            "semgrep": {
                "custom": {"python": compute_dir_hash(tmp_dir / "rules/semgrep/custom/python")},
                "third_party": {},
            },
            "yara": {"webshells": compute_dir_hash(tmp_dir / "dist/yara_scored/webshells")},
        }
    }
    verified, failed = sr._verify_keys(tmp_dir, manifest, ["python"], [], ["webshells"])
    assert failed == []
    assert set(verified) == {"semgrep.custom.python", "yara.webshells"}


def test_verify_keys_detects_tampered_content(tmp_dir):
    """Escenario de manipulación real: el contenido descargado no coincide
    con el hash publicado -- debe fallar SOLO esa clave, con mensaje claro."""
    _write(tmp_dir, "rules/semgrep/custom/python/r.yaml", "original")
    original_hash = compute_dir_hash(tmp_dir / "rules/semgrep/custom/python")
    _write(tmp_dir, "rules/semgrep/custom/python/r.yaml", "MANIPULADO")

    manifest = {"hashes": {"semgrep": {"custom": {"python": original_hash}, "third_party": {}}, "yara": {}}}
    verified, failed = sr._verify_keys(tmp_dir, manifest, ["python"], [], [])
    assert failed == ["semgrep.custom.python"]
    assert verified == {}


def test_verify_keys_fails_independently_per_key_not_globally(tmp_dir):
    """Una clave OK y otra manipulada a la vez: cada una se reporta por
    separado (nunca un resultado binario global)."""
    _write(tmp_dir, "rules/semgrep/custom/python/r.yaml", "ok")
    _write(tmp_dir, "rules/semgrep/custom/bash/r.yaml", "original")
    python_hash = compute_dir_hash(tmp_dir / "rules/semgrep/custom/python")
    bash_hash = compute_dir_hash(tmp_dir / "rules/semgrep/custom/bash")
    _write(tmp_dir, "rules/semgrep/custom/bash/r.yaml", "MANIPULADO")

    manifest = {
        "hashes": {
            "semgrep": {"custom": {"python": python_hash, "bash": bash_hash}, "third_party": {}},
            "yara": {},
        }
    }
    verified, failed = sr._verify_keys(tmp_dir, manifest, ["python", "bash"], [], [])
    assert failed == ["semgrep.custom.bash"]
    assert list(verified) == ["semgrep.custom.python"]


def test_verify_keys_fails_when_manifest_has_no_hash_for_key(tmp_dir):
    _write(tmp_dir, "rules/semgrep/custom/python/r.yaml", "x")
    manifest = {"hashes": {"semgrep": {"custom": {}, "third_party": {}}, "yara": {}}}
    verified, failed = sr._verify_keys(tmp_dir, manifest, ["python"], [], [])
    assert failed == ["semgrep.custom.python"]


def test_verify_keys_fails_when_local_folder_missing(tmp_dir):
    manifest = {"hashes": {"semgrep": {"custom": {"python": "sha256:" + "a" * 64}, "third_party": {}}, "yara": {}}}
    verified, failed = sr._verify_keys(tmp_dir, manifest, ["python"], [], [])
    assert failed == ["semgrep.custom.python"]


# --------------------------------------------------------------------------
# Aplicación del contenido verificado (todo-o-nada, remapeo de YARA)
# --------------------------------------------------------------------------


def test_apply_verified_content_copies_and_remaps_yara(tmp_dir):
    dest = tmp_dir / "dest"
    target = tmp_dir / "target"
    _write(dest, "rules/semgrep/custom/python/r.yaml", "regla")
    _write(dest, "rules/semgrep/third-party/trailofbits/rs/r.yaml", "regla-rs")
    _write(dest, "dist/yara_scored/webshells/w.yar", "rule w {}")

    sr._apply_verified_content(
        dest, target, b'{"version": "v0.0.2"}', ["python"], [("trailofbits", "rs")], ["webshells"]
    )

    assert (target / "rules/semgrep/custom/python/r.yaml").read_text(encoding="utf-8") == "regla"
    assert (target / "rules/semgrep/third-party/trailofbits/rs/r.yaml").read_text(encoding="utf-8") == "regla-rs"
    # dist/yara_scored/<cat> del repo de reglas -> rules/yara/<cat> aquí.
    assert (target / "rules/yara/webshells/w.yar").read_text(encoding="utf-8") == "rule w {}"
    assert not (target / "dist").exists()
    assert json.loads((target / "rules/manifest.json").read_text(encoding="utf-8")) == {"version": "v0.0.2"}


def test_apply_verified_content_overwrites_stale_previous_content(tmp_dir):
    """Una segunda sincronización debe reemplazar, no acumular, el
    contenido anterior de una misma clave."""
    dest = tmp_dir / "dest"
    target = tmp_dir / "target"
    _write(target / sr.CUSTOM_PREFIX, "python/regla-vieja.yaml", "vieja")
    _write(dest, "rules/semgrep/custom/python/regla-nueva.yaml", "nueva")

    sr._apply_verified_content(dest, target, b"{}", ["python"], [], [])

    assert not (target / "rules/semgrep/custom/python/regla-vieja.yaml").exists()
    assert (target / "rules/semgrep/custom/python/regla-nueva.yaml").exists()


# --------------------------------------------------------------------------
# Estado activo acumulativo
# --------------------------------------------------------------------------


def test_load_state_defaults_to_empty_skeleton_when_missing(tmp_dir):
    state = sr._load_state(tmp_dir / "no-existe.json")
    assert state["version"] is None
    assert state["hashes"]["semgrep"]["custom"] == {}


def test_write_state_accumulates_keys_across_separate_runs(tmp_dir):
    """Cada sincronización solo trae un subconjunto de claves (las que
    cambiaron); las no tocadas deben conservar su hash de una ejecución
    anterior -- el 'punto global' que sí avanza siempre es la versión."""
    state_file = tmp_dir / "rules/.rules-state.json"

    manifest_v1 = {"version": "v0.0.1", "generated_at": "2026-01-01T00:00:00Z"}
    sr._write_state(state_file, manifest_v1, {"semgrep.custom.python": "hash-py-v1"}, "test")

    manifest_v2 = {"version": "v0.0.2", "generated_at": "2026-02-01T00:00:00Z"}
    sr._write_state(state_file, manifest_v2, {"semgrep.custom.bash": "hash-bash-v2"}, "test")

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["version"] == "v0.0.2"
    # python no cambió en la v2, pero su hash de la v1 debe seguir ahí.
    assert state["hashes"]["semgrep"]["custom"]["python"] == "hash-py-v1"
    assert state["hashes"]["semgrep"]["custom"]["bash"] == "hash-bash-v2"


def test_write_state_also_writes_plaintext_version_file(tmp_dir):
    state_file = tmp_dir / "rules/.rules-state.json"
    sr._write_state(state_file, {"version": "v0.0.2"}, {}, "test")
    assert (tmp_dir / "rules/.rules-version").read_text(encoding="utf-8") == "v0.0.2\n"


def test_write_state_accumulates_nested_third_party_and_full_yara(tmp_dir):
    state_file = tmp_dir / "rules/.rules-state.json"
    sr._write_state(
        state_file,
        {"version": "v0.0.1"},
        {"semgrep.third_party.trailofbits.rs": "h1", "yara.webshells": "h2"},
        "test",
    )
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["hashes"]["semgrep"]["third_party"]["trailofbits"]["rs"] == "h1"
    assert state["hashes"]["yara"]["webshells"] == "h2"


# --------------------------------------------------------------------------
# Comparación de árboles de hashes y cmd_check
# --------------------------------------------------------------------------


def test_diff_hash_trees_empty_when_identical():
    tree = {"hashes": {"semgrep": {"custom": {"python": "h1"}}}}
    assert sr._diff_hash_trees(tree, tree) == []


def test_diff_hash_trees_reports_changed_and_missing_keys():
    remote = {"hashes": {"semgrep": {"custom": {"python": "h1", "bash": "h2"}}}}
    local = {"hashes": {"semgrep": {"custom": {"python": "h1-distinto"}}}}
    diffs = sr._diff_hash_trees(remote, local)
    assert set(diffs) == {"semgrep.custom.python", "semgrep.custom.bash"}


def test_diff_hash_trees_ignores_sha256_prefix_differences():
    remote = {"hashes": {"yara": {"webshells": "sha256:" + "a" * 64}}}
    local = {"hashes": {"yara": {"webshells": "a" * 64}}}
    assert sr._diff_hash_trees(remote, local) == []


def test_cmd_check_reports_in_sync(tmp_dir, monkeypatch, capsys):
    manifest_file = tmp_dir / "remote-manifest.json"
    manifest_file.write_text(json.dumps(MANIFEST_SAMPLE), encoding="utf-8")
    state_file = tmp_dir / "rules/.rules-state.json"
    sr._write_state(
        state_file,
        MANIFEST_SAMPLE,
        {
            "semgrep.custom.python": MANIFEST_SAMPLE["hashes"]["semgrep"]["custom"]["python"],
            "semgrep.custom.bash": MANIFEST_SAMPLE["hashes"]["semgrep"]["custom"]["bash"],
            "semgrep.third_party.trailofbits.rs": MANIFEST_SAMPLE["hashes"]["semgrep"]["third_party"]["trailofbits"]["rs"],
            "semgrep.third_party.opengrep.generic": MANIFEST_SAMPLE["hashes"]["semgrep"]["third_party"]["opengrep"]["generic"],
            "yara.webshells": MANIFEST_SAMPLE["hashes"]["yara"]["webshells"],
            "yara.antidebug_antivm": MANIFEST_SAMPLE["hashes"]["yara"]["antidebug_antivm"],
        },
        "test",
    )
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    args = argparse.Namespace(
        manifest_file=str(manifest_file), state_file=str(state_file), fail_if_out_of_sync=False
    )
    assert sr.cmd_check(args) == 0
    assert "IN_SYNC" in capsys.readouterr().out


def test_cmd_check_reports_out_of_sync_on_version_mismatch(tmp_dir, monkeypatch, capsys):
    manifest_file = tmp_dir / "remote-manifest.json"
    manifest_file.write_text(json.dumps({**MANIFEST_SAMPLE, "version": "v0.0.3"}), encoding="utf-8")
    state_file = tmp_dir / "rules/.rules-state.json"
    sr._write_state(state_file, MANIFEST_SAMPLE, {}, "test")

    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    args = argparse.Namespace(
        manifest_file=str(manifest_file), state_file=str(state_file), fail_if_out_of_sync=False
    )
    assert sr.cmd_check(args) == 0  # sin --fail-if-out-of-sync, informa pero no falla
    assert "OUT_OF_SYNC" in capsys.readouterr().out


def test_cmd_check_fail_if_out_of_sync_returns_nonzero(tmp_dir, monkeypatch):
    manifest_file = tmp_dir / "remote-manifest.json"
    manifest_file.write_text(json.dumps({**MANIFEST_SAMPLE, "version": "v0.0.3"}), encoding="utf-8")
    state_file = tmp_dir / "rules/.rules-state.json"
    sr._write_state(state_file, MANIFEST_SAMPLE, {}, "test")

    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    args = argparse.Namespace(
        manifest_file=str(manifest_file), state_file=str(state_file), fail_if_out_of_sync=True
    )
    assert sr.cmd_check(args) == 1


def test_cmd_check_writes_github_output_when_env_present(tmp_dir, monkeypatch):
    manifest_file = tmp_dir / "remote-manifest.json"
    manifest_file.write_text(json.dumps(MANIFEST_SAMPLE), encoding="utf-8")
    state_file = tmp_dir / "rules/.rules-state.json"
    output_file = tmp_dir / "gh_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    args = argparse.Namespace(
        manifest_file=str(manifest_file), state_file=str(state_file), fail_if_out_of_sync=False
    )
    sr.cmd_check(args)

    content = output_file.read_text(encoding="utf-8")
    # Formato multilínea real de $GITHUB_OUTPUT (key<<DELIM / valor / DELIM),
    # no "key=value" a secas -- ver el comentario de seguridad en
    # _write_github_output (un salto de línea en el valor permitiría
    # inyectar pares clave=valor arbitrarios con el formato simple).
    assert re.search(r"status<<\w+\nout_of_sync\n\w+\n", content)
    assert re.search(r"remote_version<<\w+\nv0\.0\.2\n\w+\n", content)


# --------------------------------------------------------------------------
# Releases API (mockeada -- sin red real)
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        json_body: object = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self._json = json_body
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def fake_releases_api(monkeypatch):
    """Simula la Releases API real de GitHub para pablojimz/Repo-reglas-SEMGREP-y-YARA,
    con un asset manifest.json y un tag v0.0.2, sin tocar la red."""
    repo = "pablojimz/Repo-reglas-SEMGREP-y-YARA"
    release = {
        "tag_name": "v0.0.2",
        "assets": [
            {"name": "manifest.json", "url": f"https://api.github.com/repos/{repo}/releases/assets/111"},
            {"name": "otro.txt", "url": f"https://api.github.com/repos/{repo}/releases/assets/222"},
        ],
    }
    manifest_bytes = json.dumps(MANIFEST_SAMPLE).encode("utf-8")
    calls: list[str] = []

    def fake_get(url, headers=None, timeout=None, params=None, follow_redirects=False):
        calls.append(url)
        if url == f"https://api.github.com/repos/{repo}/releases/tags/v0.0.2":
            return _FakeResponse(200, json_body=release)
        if url == f"https://api.github.com/repos/{repo}/releases/latest":
            return _FakeResponse(200, json_body=release)
        if url == f"https://api.github.com/repos/{repo}/releases/tags/v9.9.9":
            return _FakeResponse(404)
        if url == f"https://api.github.com/repos/{repo}/releases/assets/111":
            return _FakeResponse(200, content=manifest_bytes)
        raise AssertionError(f"URL inesperada en el test: {url}")

    monkeypatch.setattr(sr.httpx, "get", fake_get)
    return {"repo": repo, "release": release, "manifest_bytes": manifest_bytes, "calls": calls}


def test_fetch_release_manifest_by_exact_tag(fake_releases_api):
    tag, raw, manifest = sr.fetch_release_manifest(
        fake_releases_api["repo"], "v0.0.2", "fake-token", "manifest.json"
    )
    assert tag == "v0.0.2"
    assert raw == fake_releases_api["manifest_bytes"]
    assert manifest["version"] == "v0.0.2"


def test_fetch_release_manifest_latest_resolves_to_real_tag(fake_releases_api):
    tag, _raw, _manifest = sr.fetch_release_manifest(
        fake_releases_api["repo"], "latest", "fake-token", "manifest.json"
    )
    assert tag == "v0.0.2"


def test_fetch_release_manifest_missing_tag_raises_clear_error(fake_releases_api):
    with pytest.raises(RuntimeError, match="No existe una Release"):
        sr.fetch_release_manifest(fake_releases_api["repo"], "v9.9.9", "fake-token", "manifest.json")


def test_fetch_release_manifest_missing_asset_lists_available_ones(fake_releases_api):
    with pytest.raises(RuntimeError, match="no tiene un asset llamado"):
        sr._download_release_asset(
            fake_releases_api["repo"], fake_releases_api["release"], "no-existe.json", "fake-token"
        )


# --------------------------------------------------------------------------
# cmd_sync de punta a punta (checkout de Git sustituido por un doble de
# prueba -- la mecánica real de git+LFS se prueba aparte, sin red, en
# tests/unit/test_sync_rules_git_lfs.py)
# --------------------------------------------------------------------------


def _fake_checkout_that_materializes(dest_contents: dict[str, str]):
    """Devuelve un doble de `_checkout_rule_folders` que, en vez de clonar
    de verdad, escribe directamente los ficheros indicados bajo `dest`."""

    def _fake(repo, ref, token, dest, patterns):  # noqa: ANN001 -- firma espejo de la real
        for relpath, content in dest_contents.items():
            _write(dest, relpath, content)

    return _fake


def test_cmd_sync_happy_path_verifies_applies_and_writes_state(tmp_dir, monkeypatch, fake_releases_api):
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    python_dir = tmp_dir / "checkout-content" / "rules/semgrep/custom/python"
    python_dir.mkdir(parents=True)
    (python_dir / "r.yaml").write_text("regla-python", encoding="utf-8")
    real_hash = compute_dir_hash(python_dir)

    # El manifest fake ya trae un hash fijo para "python" (MANIFEST_SAMPLE);
    # lo sustituimos por el hash real del contenido que el doble de checkout
    # va a materializar, para que la verificación pase de verdad.
    fake_releases_api["release"]  # noqa: B018 -- solo para dejar constancia del fixture usado
    monkeypatch.setattr(
        sr,
        "fetch_release_manifest",
        lambda repo, ref, token, asset: (
            "v0.0.2",
            b'{"version": "v0.0.2"}',
            {
                "version": "v0.0.2",
                "hashes": {"semgrep": {"custom": {"python": real_hash}, "third_party": {}}, "yara": {}},
            },
        ),
    )
    monkeypatch.setattr(
        sr,
        "_checkout_rule_folders",
        _fake_checkout_that_materializes({"rules/semgrep/custom/python/r.yaml": "regla-python"}),
    )

    target_root = tmp_dir / "watch_gate"
    target_root.mkdir()
    args = argparse.Namespace(
        rules_repo="pablojimz/Repo-reglas-SEMGREP-y-YARA",
        ref="v0.0.2",
        scope="changed",
        languages_changed=json.dumps(["python"]),
        third_party_changed="[]",
        manifest_asset="manifest.json",
        target_root=str(target_root),
        state_file="rules/.rules-state.json",
        triggered_by="test",
    )

    assert sr.cmd_sync(args) == 0
    assert (target_root / "rules/semgrep/custom/python/r.yaml").read_text(encoding="utf-8") == "regla-python"
    state = json.loads((target_root / "rules/.rules-state.json").read_text(encoding="utf-8"))
    assert state["version"] == "v0.0.2"
    assert state["hashes"]["semgrep"]["custom"]["python"] == real_hash


def test_cmd_sync_does_not_activate_anything_when_a_key_is_tampered(tmp_dir, monkeypatch):
    """Núcleo de la garantía de seguridad: si el contenido descargado no
    coincide con el hash publicado, NO se debe escribir nada en
    target_root -- ni el contenido, ni el estado -- aunque otras claves
    de la misma ejecución sí hubieran verificado."""
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    monkeypatch.setattr(
        sr,
        "fetch_release_manifest",
        lambda repo, ref, token, asset: (
            "v0.0.2",
            b'{"version": "v0.0.2"}',
            {
                "version": "v0.0.2",
                "hashes": {
                    "semgrep": {"custom": {"python": "sha256:" + "0" * 64}, "third_party": {}},
                    "yara": {},
                },
            },
        ),
    )
    # El doble de checkout materializa contenido que NO coincide con el
    # hash que acabamos de declarar en el manifest fake (simula manipulación
    # o corrupción del contenido descargado).
    monkeypatch.setattr(
        sr,
        "_checkout_rule_folders",
        _fake_checkout_that_materializes({"rules/semgrep/custom/python/r.yaml": "contenido-no-esperado"}),
    )

    target_root = tmp_dir / "watch_gate"
    target_root.mkdir()
    args = argparse.Namespace(
        rules_repo="pablojimz/Repo-reglas-SEMGREP-y-YARA",
        ref="v0.0.2",
        scope="changed",
        languages_changed=json.dumps(["python"]),
        third_party_changed="[]",
        manifest_asset="manifest.json",
        target_root=str(target_root),
        state_file="rules/.rules-state.json",
        triggered_by="test",
    )

    assert sr.cmd_sync(args) == 1
    assert not (target_root / "rules").exists()  # nada se activó


def test_cmd_sync_requires_rules_repo_token(monkeypatch, tmp_dir):
    monkeypatch.delenv("RULES_REPO_TOKEN", raising=False)
    args = argparse.Namespace(
        rules_repo="x/y",
        ref="v1",
        scope="changed",
        languages_changed="[]",
        third_party_changed="[]",
        manifest_asset="manifest.json",
        target_root=str(tmp_dir),
        state_file="rules/.rules-state.json",
        triggered_by="test",
    )
    assert sr.cmd_sync(args) == 2
