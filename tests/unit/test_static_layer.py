"""Tests unitarios para StaticLayer (watchgate/core/layers/static_layer.py)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import watchgate.core.layers.static_layer as static_layer_module
from watchgate.core.layers.base import LAYER_REGISTRY
from watchgate.core.layers.static_layer import (
    SEVERITY_SCORE,
    THIRD_PARTY_LANGUAGE_MAP,
    StaticLayer,
)
from watchgate.core.models import (
    CommitAuthor,
    FileChange,
    FileStatus,
    NormalizedDiff,
    ThreatNature,
)


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
    assert "Semgrep" in res.skip_reason
    assert "YARA" in res.skip_reason


# --------------------------------------------------------------------------
# YARA: integrada en la MISMA capa que Semgrep (spec §4), combinada vía
# max() -- nunca sumar, mismo peso "static" en .watchgate.yml.
# --------------------------------------------------------------------------

_WEBSHELL_YAR_RULE = """
rule test_webshell_marker
{
    meta:
        risk_score = 83
        risk_justification = "Marcador de prueba de webshell -- no es una regla real."
    strings:
        $marker = "TOTALLY_A_WEBSHELL_MARKER_1234"
    condition:
        $marker
}
"""

_NO_META_YAR_RULE = """
rule test_rule_without_risk_score_meta
{
    strings:
        $marker = "SOME_OTHER_SUSPICIOUS_MARKER_5678"
    condition:
        $marker
}
"""


@pytest.fixture(autouse=True)
def _clear_yara_process_cache():
    """La caché de reglas compiladas vive a nivel de proceso (ver
    static_layer._yara_rules_cache) -- se limpia antes/después de cada
    test para que no haya contaminación entre tests con distintos
    `tmp_path` (que ya son únicos por test, pero esto lo deja explícito
    y hermético)."""
    static_layer_module._yara_rules_cache.clear()
    yield
    static_layer_module._yara_rules_cache.clear()


def _write_yara_rule(root: Path, relpath: str, content: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_get_compiled_yara_rules_compiles_all_categories(tmp_path) -> None:
    _write_yara_rule(tmp_path, "rules/yara/webshells/test.yar", _WEBSHELL_YAR_RULE)
    _write_yara_rule(tmp_path, "rules/yara/antidebug_antivm/test.yar", _NO_META_YAR_RULE)

    layer = StaticLayer()
    compiled = layer._get_compiled_yara_rules(tmp_path)

    assert compiled is not None
    # Ambas categorías presentes: una regla de cada fichero coincide con su marcador.
    assert len(compiled.match(data=b"TOTALLY_A_WEBSHELL_MARKER_1234")) == 1
    assert len(compiled.match(data=b"SOME_OTHER_SUSPICIOUS_MARKER_5678")) == 1


def test_get_compiled_yara_rules_caches_within_process(tmp_path) -> None:
    _write_yara_rule(tmp_path, "rules/yara/webshells/test.yar", _WEBSHELL_YAR_RULE)
    layer = StaticLayer()

    first = layer._get_compiled_yara_rules(tmp_path)
    second = layer._get_compiled_yara_rules(tmp_path)

    assert first is second  # misma instancia -- no se recompiló


def test_get_compiled_yara_rules_returns_none_when_yara_dir_missing(tmp_path) -> None:
    layer = StaticLayer()
    assert layer._get_compiled_yara_rules(tmp_path) is None


def test_run_yara_on_text_detects_match_and_reads_risk_score_from_rule_metadata(tmp_path) -> None:
    _write_yara_rule(tmp_path, "rules/yara/webshells/test.yar", _WEBSHELL_YAR_RULE)
    layer = StaticLayer()

    findings = layer._run_yara_on_text("prefix\nTOTALLY_A_WEBSHELL_MARKER_1234\nsuffix", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding["tool"] == "yara"
    assert finding["rule_id"] == "test_webshell_marker"
    assert finding["risk_score"] == 83  # leído de meta.risk_score, no inventado
    assert finding["threat_nature"] == ThreatNature.MALICIOUS
    assert "Marcador de prueba" in finding["message"]


def test_run_yara_on_text_no_match_on_benign_content(tmp_path) -> None:
    _write_yara_rule(tmp_path, "rules/yara/webshells/test.yar", _WEBSHELL_YAR_RULE)
    layer = StaticLayer()

    findings = layer._run_yara_on_text("def hello():\n    print('hola mundo')\n", tmp_path)

    assert findings == []


def test_run_yara_on_text_falls_back_to_default_score_when_meta_missing(tmp_path) -> None:
    _write_yara_rule(tmp_path, "rules/yara/webshells/test.yar", _NO_META_YAR_RULE)
    layer = StaticLayer()

    findings = layer._run_yara_on_text("SOME_OTHER_SUSPICIOUS_MARKER_5678", tmp_path)

    assert len(findings) == 1
    assert findings[0]["risk_score"] == static_layer_module._YARA_DEFAULT_RISK_SCORE


def test_analyze_runs_yara_even_on_extension_semgrep_does_not_recognize(tmp_path) -> None:
    """El caso clave del diseño: un webshell con extensión .asp (que
    _detect_language no reconoce, así que Semgrep nunca lo tocaría) debe
    seguir siendo detectado por YARA -- ver el comentario en analyze()."""
    _write_yara_rule(tmp_path, "rules/yara/webshells/test.yar", _WEBSHELL_YAR_RULE)
    layer = StaticLayer()

    assert layer._detect_language("shell.asp") is None  # confirma la premisa del test

    diff = _make_diff(
        [
            FileChange(
                path="shell.asp",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -0,0 +1,1 @@\n+TOTALLY_A_WEBSHELL_MARKER_1234",
                additions=1,
                deletions=0,
            )
        ]
    )

    with patch.object(layer, "_get_rules_dir", return_value=tmp_path):
        res = layer.analyze(diff, {})

    assert res.skipped is False
    assert res.risk_score == 83
    assert any(f.threat_nature == ThreatNature.MALICIOUS for f in res.findings)


def test_analyze_combines_semgrep_and_yara_via_max_never_sum(tmp_path) -> None:
    """Semgrep y YARA son la MISMA capa: sus hallazgos se combinan con
    max(), nunca se suman (spec §4, regla explícita)."""
    _write_yara_rule(tmp_path, "rules/yara/webshells/test.yar", _WEBSHELL_YAR_RULE)  # risk_score=83
    layer = StaticLayer()

    diff = _make_diff(
        [
            FileChange(
                path="src/app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -0,0 +1,1 @@\n+TOTALLY_A_WEBSHELL_MARKER_1234",
                additions=1,
                deletions=0,
            )
        ]
    )

    semgrep_findings = [{"tool": "semgrep", "rule_id": "some-rule", "message": "x", "risk_score": 30}]
    with (
        patch.object(layer, "_get_rules_dir", return_value=tmp_path),
        patch.object(layer, "_run_semgrep_on_file", return_value=semgrep_findings),
    ):
        res = layer.analyze(diff, {})

    # max(30, 83) = 83, NUNCA 30 + 83 = 113
    assert res.risk_score == 83
