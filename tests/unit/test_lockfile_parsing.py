"""Tests de los parsers de LOCKFILE en watchgate/core/layers/_shared.py --
package-lock.json, yarn.lock, poetry.lock, Cargo.lock, go.sum. Un
`npm update`/`poetry update`/`cargo update`/`go mod tidy` que solo toca el
lockfile (sin tocar el manifiesto, que declara un rango suelto, no la
versión exacta) se colaba totalmente desapercibido -- hallazgo real
reportado por el usuario, ver DEPENDENCY_MANIFEST_FILENAMES.
"""

from __future__ import annotations

from watchgate.core.layers._shared import (
    DEPENDENCY_MANIFEST_FILENAMES,
    parse_cargo_lock,
    parse_go_sum,
    parse_manifest_file_change,
    parse_package_lock_json,
    parse_poetry_lock,
    parse_yarn_lock,
)
from watchgate.core.models import FileChange, FileStatus


def test_all_lockfile_names_are_recognized_as_dependency_manifests() -> None:
    for fname in ("package-lock.json", "yarn.lock", "poetry.lock", "Cargo.lock", "go.sum"):
        assert fname in DEPENDENCY_MANIFEST_FILENAMES


def test_parse_package_lock_json_pairs_node_modules_key_with_its_version() -> None:
    hunk = (
        '+    "node_modules/lodash": {\n'
        '+      "version": "4.17.21",\n'
        '+      "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz"\n'
        "+    },"
    )
    changes = parse_package_lock_json(hunk)
    assert len(changes) == 1
    assert changes[0].ecosystem == "npm"
    assert changes[0].name == "lodash"
    assert changes[0].new_version == "4.17.21"


def test_parse_package_lock_json_resolves_nested_transitive_dependency_to_its_own_name() -> None:
    """Un paquete transitivo duplicado (dos versiones distintas requeridas
    por dos padres distintos) aparece anidado -- el nombre resuelto es el
    último segmento tras el `node_modules/` final, no la ruta completa."""
    hunk = '+    "node_modules/foo/node_modules/bar": {\n+      "version": "2.0.0"\n+    },'
    changes = parse_package_lock_json(hunk)
    assert len(changes) == 1
    assert changes[0].name == "bar"
    assert changes[0].new_version == "2.0.0"


def test_parse_package_lock_json_scoped_package() -> None:
    hunk = '+    "node_modules/@babel/core": {\n+      "version": "7.24.0"\n+    },'
    changes = parse_package_lock_json(hunk)
    assert len(changes) == 1
    assert changes[0].name == "@babel/core"


def test_parse_yarn_lock_pairs_specifier_line_with_indented_version() -> None:
    hunk = (
        "+lodash@^4.17.15, lodash@^4.17.21:\n"
        '+  version "4.17.21"\n'
        '+  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz"\n'
    )
    changes = parse_yarn_lock(hunk)
    assert len(changes) == 1
    assert changes[0].ecosystem == "npm"
    assert changes[0].name == "lodash"
    assert changes[0].new_version == "4.17.21"


def test_parse_yarn_lock_scoped_package_uses_second_at_as_version_separator() -> None:
    hunk = '+"@babel/core@^7.20.0":\n+  version "7.24.0"\n'
    changes = parse_yarn_lock(hunk)
    assert len(changes) == 1
    assert changes[0].name == "@babel/core"
    assert changes[0].new_version == "7.24.0"


def test_parse_poetry_lock_pairs_name_and_version_within_a_package_block() -> None:
    hunk = (
        '+[[package]]\n+name = "flask"\n+version = "0.12.2"\n+description = "A simple framework"\n'
    )
    changes = parse_poetry_lock(hunk)
    assert len(changes) == 1
    assert changes[0].ecosystem == "PyPI"
    assert changes[0].name == "flask"
    assert changes[0].new_version == "0.12.2"


def test_parse_poetry_lock_does_not_leak_name_across_package_blocks() -> None:
    """Un hunk con un `[[package]]` a medias (solo el name, sin su version
    todavía dentro del fragmento visible) no debe emparejar ese name con
    el version de OTRO bloque que venga después en el mismo hunk."""
    hunk = '+[[package]]\n+name = "flask"\n+[[package]]\n+name = "requests"\n+version = "2.5.0"\n'
    changes = parse_poetry_lock(hunk)
    assert len(changes) == 1
    assert changes[0].name == "requests"
    assert changes[0].new_version == "2.5.0"


def test_parse_cargo_lock_reuses_the_same_toml_block_parser_with_crates_io() -> None:
    hunk = '+[[package]]\n+name = "serde"\n+version = "1.0.197"\n'
    changes = parse_cargo_lock(hunk)
    assert len(changes) == 1
    assert changes[0].ecosystem == "crates.io"
    assert changes[0].name == "serde"
    assert changes[0].new_version == "1.0.197"


def test_parse_go_sum_dedupes_the_module_and_go_mod_hash_lines() -> None:
    hunk = (
        "+github.com/stretchr/testify v1.8.4 h1:CcVdcJQpm0/6vDMhBerv12dtejxOL+ejFHfp8mePFlU=\n"
        "+github.com/stretchr/testify v1.8.4/go.mod h1:szlmYIOXD1dqDmKjjqLyZ2RngseejIcXlSw2iwfAo=\n"
    )
    changes = parse_go_sum(hunk)
    assert len(changes) == 1
    assert changes[0].ecosystem == "Go"
    assert changes[0].name == "github.com/stretchr/testify"
    assert changes[0].new_version == "v1.8.4"


def test_parse_manifest_file_change_dispatches_lockfiles_by_filename() -> None:
    fc = FileChange(
        path="poetry.lock",
        status=FileStatus.MODIFIED,
        diff_hunk='+[[package]]\n+name = "flask"\n+version = "0.12.2"\n',
        additions=3,
        deletions=0,
    )
    changes = parse_manifest_file_change(fc)
    assert len(changes) == 1
    assert changes[0].manifest_path == "poetry.lock"
    assert changes[0].name == "flask"
