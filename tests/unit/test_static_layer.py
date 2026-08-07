"""Tests unitarios para StaticLayer (watchgate/core/layers/static_layer.py)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from watchgate.core.layers.base import LAYER_REGISTRY
from watchgate.core.layers.static_layer import (
    SEVERITY_SCORE,
    THIRD_PARTY_LANGUAGE_MAP,
    StaticLayer,
)
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


def test_static_layer_registered() -> None:
    assert "static" in LAYER_REGISTRY
    assert LAYER_REGISTRY["static"] is StaticLayer


def test_detect_language() -> None:
    layer = StaticLayer()
    assert layer._detect_language("src/main.py") == "python"
    assert layer._detect_language("web/app.js") == "javascript"
    assert layer._detect_language("web/app.tsx") == "typescript"
    assert layer._detect_language("config/ci.yml") == "yaml"
    assert layer._detect_language("README.md") is None


def test_detect_language_covers_all_17_custom_categories_and_third_party_only_ones() -> None:
    """Cubre los lenguajes que se añadieron al conectar la capa con las
    reglas de terceros (spec §4 + docs/integracion_repo_reglas.md) --
    antes de esto, ficheros de estos lenguajes nunca se analizaban aunque
    ya hubiera reglas verificadas y sincronizadas para ellos."""
    layer = StaticLayer()
    cases = {
        "app/Foo.cs": "csharp",
        "src/handler.clj": "clojure",
        "lib/parser.ml": "ocaml",
        "web/index.php": "php",
        "scripts/deploy.ps1": "powershell",
        "data/config.json": "json",
        "src/main.rs": "rust",
        "App/Main.swift": "swift",
        "src/Main.kt": "kotlin",  # solo third-party, sin carpeta custom/
        "src/Main.scala": "scala",  # solo third-party
        "contracts/Token.sol": "solidity",  # solo third-party
        "infra/main.tf": "terraform",  # solo third-party
        "infra/vars.hcl": "terraform",
    }
    for path, expected in cases.items():
        assert layer._detect_language(path) == expected, path


def test_detect_language_recognizes_dockerfile_by_name_not_extension() -> None:
    """Dockerfile no sigue convención de extensión -- se detecta por el
    nombre del fichero (literal, con sufijo tipo .prod, o *.dockerfile)."""
    layer = StaticLayer()
    assert layer._detect_language("Dockerfile") == "dockerfile"
    assert layer._detect_language("docker/Dockerfile.prod") == "dockerfile"
    assert layer._detect_language("build/base.dockerfile") == "dockerfile"
    assert layer._detect_language("notadockerfile.txt") is None


def test_third_party_language_map_uses_explicit_curation_not_name_guessing() -> None:
    """El repo de reglas deja claro que <carpeta> de third-party es un
    namespace independiente (p. ej. trailofbits/rs son reglas de Rust,
    no de un lenguaje llamado 'rs') -- este test fija ese ejemplo
    concreto y confirma que los paquetes no específicos de un lenguaje
    (generic, noisy, problem-based-packs) no se auto-incluyen en ningún
    lenguaje."""
    assert ("trailofbits", "rs") in THIRD_PARTY_LANGUAGE_MAP["rust"]
    all_mapped_pairs = [pair for pairs in THIRD_PARTY_LANGUAGE_MAP.values() for pair in pairs]
    assert ("opengrep", "generic") not in all_mapped_pairs
    assert ("opengrep", "problem-based-packs") not in all_mapped_pairs
    assert ("trailofbits", "generic") not in all_mapped_pairs
    assert ("0xdea", "noisy") not in all_mapped_pairs


def test_run_semgrep_on_file_includes_custom_regex_and_relevant_third_party(tmp_path) -> None:
    """Ejercita _run_semgrep_on_file de verdad (no mockeada) contra un
    árbol de reglas real en disco: para un fichero Rust, el --config
    generado debe incluir custom/rust, custom/regex (siempre-on, con
    independencia del lenguaje) y third-party/trailofbits/rs (la única
    carpeta third-party mapeada a rust) -- y NADA de opengrep, que no
    tiene carpeta 'rust'."""
    semgrep_root = tmp_path / "rules" / "semgrep"
    (semgrep_root / "custom" / "rust").mkdir(parents=True)
    (semgrep_root / "custom" / "regex").mkdir(parents=True)
    (semgrep_root / "third-party" / "trailofbits" / "rs").mkdir(parents=True)

    layer = StaticLayer()
    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(command)
        result = MagicMock()
        result.returncode = 0
        result.stdout = "{}"
        result.stderr = ""
        return result

    with patch("watchgate.core.layers.static_layer.subprocess.run", side_effect=fake_run):
        layer._run_semgrep_on_file("dummy.rs", "rust", tmp_path)

    assert len(captured) == 1
    config_args = [a for a in captured[0] if a.startswith("--config=")]
    assert any(str(semgrep_root / "custom" / "rust") in c for c in config_args)
    assert any(str(semgrep_root / "custom" / "regex") in c for c in config_args)
    assert any(str(semgrep_root / "third-party" / "trailofbits" / "rs") in c for c in config_args)
    assert not any("opengrep" in c for c in config_args)


def test_run_semgrep_on_file_regex_category_does_not_duplicate_itself() -> None:
    """Si el 'lenguaje' detectado fuera justo 'regex', no debe añadirse
    dos veces el mismo --config=.../custom/regex."""
    tmp_root = Path(tempfile.mkdtemp())
    try:
        semgrep_root = tmp_root / "rules" / "semgrep"
        (semgrep_root / "custom" / "regex").mkdir(parents=True)

        layer = StaticLayer()
        captured: list[list[str]] = []

        def fake_run(command, **kwargs):
            captured.append(command)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "{}"
            result.stderr = ""
            return result

        with patch("watchgate.core.layers.static_layer.subprocess.run", side_effect=fake_run):
            layer._run_semgrep_on_file("dummy.sh", "regex", tmp_root)

        config_args = [a for a in captured[0] if a.startswith("--config=")]
        assert config_args.count(f"--config={semgrep_root / 'custom' / 'regex'}") == 1
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_severity_score_mapping() -> None:
    assert SEVERITY_SCORE["INFO"] == 10
    assert SEVERITY_SCORE["WARNING"] == 30
    assert SEVERITY_SCORE["ERROR"] == 60


def test_static_layer_clean_diff() -> None:
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,1 +1,1 @@\n-print('hello')\n+print('hello world')",
                additions=1,
                deletions=1,
            )
        ]
    )

    with patch.object(layer, "_run_semgrep_on_file", return_value=[]):
        with patch.object(layer, "_get_rules_dir", return_value=Path(tempfile.gettempdir())):
            res = layer.analyze(diff, {})

    assert res.risk_score == 0
    assert "No se encontraron hallazgos estáticos" in res.justification
    assert res.skipped is False


def test_static_layer_with_findings_takes_max_score() -> None:
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/eval_test.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,0 +1,1 @@\n+eval(user_input)",
                additions=1,
                deletions=0,
            )
        ]
    )

    mock_findings = [
        {
            "tool": "semgrep",
            "rule_id": "rules.eval-exec-dynamic",
            "message": "eval()",
            "risk_score": 60,
        },
        {"tool": "semgrep", "rule_id": "rules.network-call", "message": "curl", "risk_score": 30},
    ]

    with patch.object(layer, "_run_semgrep_on_file", return_value=mock_findings):
        with patch.object(layer, "_get_rules_dir", return_value=Path(tempfile.gettempdir())):
            res = layer.analyze(diff, {})

    # Debe tomar el MAX (60), NUNCA SUMAR (90)
    assert res.risk_score == 60
    assert "eval-exec-dynamic" in res.justification
    assert "2 hallazgos estáticos" in res.justification


def test_static_layer_skips_when_rules_unavailable() -> None:
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,1 +1,1 @@\n+x = 1",
                additions=1,
                deletions=0,
            )
        ]
    )

    with patch.object(layer, "_get_rules_dir", return_value=None):
        res = layer.analyze(diff, {})

    assert res.risk_score == 0
    assert res.skipped is True
    assert "Reglas Semgrep no disponibles" in res.skip_reason
