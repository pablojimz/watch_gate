"""Tests unitarios para StaticLayer (watchgate/core/layers/static_layer.py)."""

from __future__ import annotations

import json
import shutil
import tempfile
import types
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


def test_run_semgrep_on_file_fallback_scopes_to_semgrep_root_not_whole_rules_dir(
    tmp_path,
) -> None:
    """Si `rules/semgrep` existe pero ninguna subcarpeta concreta aplicó
    para el lenguaje (checkout a medio sincronizar), el último recurso debe
    acotarse a `rules/semgrep`, nunca a `rules_dir` completo -- en el caso 3
    de `_get_rules_dir`, `rules_dir` es `Path(".")` (la raíz del repo), y
    `--config=.` escanearía con Semgrep cualquier YAML con forma de regla
    en todo el proyecto, no solo las reglas de WatchGate."""
    semgrep_root = tmp_path / "rules" / "semgrep"
    semgrep_root.mkdir(parents=True)  # existe, pero vacío: nada que matchee

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
        layer._run_semgrep_on_file("dummy.cpp", "cpp", tmp_path)

    config_args = [a for a in captured[0] if a.startswith("--config=")]
    assert config_args == [f"--config={semgrep_root}"]


def test_run_semgrep_on_file_fallback_uses_rules_dir_when_no_semgrep_root(tmp_path) -> None:
    """Si ni siquiera existe `rules/semgrep` bajo `rules_dir` (p. ej. un
    clon del repo externo de reglas con otra convención de carpetas), el
    último recurso sigue siendo `rules_dir` a secas -- sin regresión
    respecto al comportamiento anterior para ese caso."""
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
        layer._run_semgrep_on_file("dummy.cpp", "cpp", tmp_path)

    config_args = [a for a in captured[0] if a.startswith("--config=")]
    assert config_args == [f"--config={tmp_path}"]


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


def _write_rule_yaml(path: Path, rule_id: str, *, finding_type_in: str | None, block: str) -> None:
    """Escribe un YAML de una sola regla con `finding_type` (si se pide)
    bajo `metadata:` u `options:`, según `block` -- ver los dos convenios
    reales encontrados en rules/semgrep (775 reglas bajo metadata, 3
    heredadas bajo options)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    finding_type_line = f"\n      finding_type: {finding_type_in}" if finding_type_in else ""
    if block == "metadata":
        options_block = ""
        metadata_extra = finding_type_line
    else:
        options_block = f"\n    options:{finding_type_line}" if finding_type_in else ""
        metadata_extra = ""
    path.write_text(
        f"""rules:
  - id: {rule_id}
    languages: [generic]
    severity: ERROR
    message: "regla de test"
    metadata:
      category: security{metadata_extra}{options_block}
    patterns:
      - pattern: dummy
""",
        encoding="utf-8",
    )


def test_get_semgrep_finding_types_reads_metadata_and_options_blocks(tmp_path) -> None:
    """`finding_type` declarado bajo `metadata:` (convenio mayoritario) y
    bajo `options:` (3 reglas heredadas, ver docstring del método) deben
    resolverse igual -- el resultado no debe depender de en qué bloque
    haya elegido declararlo el autor de la regla."""
    semgrep_root = tmp_path / "rules" / "semgrep"
    _write_rule_yaml(
        semgrep_root / "custom" / "csharp" / "rule-a.yaml",
        "rule-a",
        finding_type_in="vulnerability",
        block="metadata",
    )
    _write_rule_yaml(
        semgrep_root / "custom" / "powershell" / "rule-b.yaml",
        "rule-b",
        finding_type_in="malicious",
        block="options",
    )
    _write_rule_yaml(
        semgrep_root / "custom" / "python" / "rule-c.yaml",
        "rule-c",
        finding_type_in=None,
        block="metadata",
    )

    layer = StaticLayer()
    finding_types = layer._get_semgrep_finding_types(tmp_path)

    assert finding_types["rule-a"] == "vulnerability"
    assert finding_types["rule-b"] == "malicious"
    assert "rule-c" not in finding_types


def test_get_semgrep_finding_types_caches_within_process(tmp_path) -> None:
    semgrep_root = tmp_path / "rules" / "semgrep"
    _write_rule_yaml(
        semgrep_root / "custom" / "csharp" / "rule-a.yaml",
        "rule-a",
        finding_type_in="vulnerability",
        block="metadata",
    )

    layer = StaticLayer()
    first = layer._get_semgrep_finding_types(tmp_path)
    # Añadir una regla nueva en disco NO debe cambiar el resultado de una
    # segunda llamada dentro del mismo proceso: se sirve de la caché.
    _write_rule_yaml(
        semgrep_root / "custom" / "csharp" / "rule-new.yaml",
        "rule-new",
        finding_type_in="malicious",
        block="metadata",
    )
    second = layer._get_semgrep_finding_types(tmp_path)

    assert first == second
    assert "rule-new" not in second


def test_run_semgrep_on_file_uses_declared_finding_type_over_keyword_heuristic(tmp_path) -> None:
    """Caso real que motivó este cambio: una regla cuyo `category` es
    "security" (no matchea ningún keyword de la heurística de
    _infer_threat_nature_from_semgrep) pero que el propio autor clasificó
    como `finding_type: malicious` -- el hallazgo debe salir MALICIOUS, no
    VULNERABILITY por defecto de la heurística (ver
    powershell-download-and-execute.yaml, que motivó este test)."""
    semgrep_root = tmp_path / "rules" / "semgrep"
    _write_rule_yaml(
        semgrep_root / "custom" / "powershell" / "download-and-execute.yaml",
        "download-and-execute",
        finding_type_in="malicious",
        block="options",
    )

    layer = StaticLayer()
    fake_stdout = json.dumps(
        {
            "results": [
                {
                    "check_id": "rules.semgrep.custom.powershell.download-and-execute",
                    "path": "dummy.ps1",
                    "start": {"line": 1},
                    "extra": {
                        "severity": "ERROR",
                        "message": "regla de test",
                        # `metadata` a propósito SIN `finding_type` ni ningún
                        # keyword malicioso -- solo lo tiene `options`, que
                        # Semgrep no reenvía en su JSON de salida.
                        "metadata": {"category": "security"},
                    },
                }
            ]
        }
    )

    def fake_run(command, **kwargs):
        result = MagicMock()
        result.returncode = 1
        result.stdout = fake_stdout
        result.stderr = ""
        return result

    with patch("watchgate.core.layers.static_layer.subprocess.run", side_effect=fake_run):
        findings = layer._run_semgrep_on_file("dummy.ps1", "powershell", tmp_path)

    assert len(findings) == 1
    assert findings[0]["threat_nature"] == ThreatNature.MALICIOUS


def test_run_semgrep_on_file_falls_back_to_heuristic_when_no_finding_type_declared(
    tmp_path,
) -> None:
    """Sin ninguna regla en disco que declare `finding_type` para ese
    rule_id (p. ej. una regla de terceros no clasificada, o un checkout
    parcial de la caché de reglas), debe seguir cayendo a la heurística
    de palabras clave existente -- sin regresión respecto al
    comportamiento anterior a este cambio."""
    layer = StaticLayer()
    fake_stdout = json.dumps(
        {
            "results": [
                {
                    "check_id": "some.vendor.rules.malware-backdoor-check",
                    "path": "dummy.py",
                    "start": {"line": 3},
                    "extra": {
                        "severity": "ERROR",
                        "message": "hallazgo de terceros sin finding_type",
                        "metadata": {"category": "malware"},
                    },
                }
            ]
        }
    )

    def fake_run(command, **kwargs):
        result = MagicMock()
        result.returncode = 1
        result.stdout = fake_stdout
        result.stderr = ""
        return result

    with patch("watchgate.core.layers.static_layer.subprocess.run", side_effect=fake_run):
        findings = layer._run_semgrep_on_file("dummy.py", "python", tmp_path)

    assert len(findings) == 1
    assert findings[0]["threat_nature"] == ThreatNature.MALICIOUS


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

    with patch.object(layer, "_run_semgrep_on_files", return_value={}):
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

    def _fake_run_semgrep_on_files(temp_paths, language, rules_dir):
        # `analyze()` agrupa por lenguaje y llama a esto con las rutas
        # temporales que ÉL genera -- se devuelven los mismos hallazgos
        # mockeados para cada una, tal como haría Semgrep de verdad.
        return {p: list(mock_findings) for p in temp_paths}

    with patch.object(layer, "_run_semgrep_on_files", side_effect=_fake_run_semgrep_on_files):
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


@pytest.mark.parametrize(
    "diff_hunk",
    [
        "@@ -1,1 +1,1 @@\n+# NOTE: ignore the previous config file, use settings.yaml instead",
        "@@ -1,1 +1,1 @@\n+// TODO: don't flag this edge case in the linter, it's intentional",
    ],
)
def test_static_layer_does_not_flag_ordinary_code_comments_as_malicious(diff_hunk: str) -> None:
    """Bug real, reproducido en vivo: la capa estática llegó a escanear el
    diff en busca de frases tipo "ignora las instrucciones anteriores" /
    "no marques esto" (pensadas para detectar inyección de prompt contra el
    LLM) y, ante cualquier coincidencia, forzaba risk_score=100 y
    threat_nature=MALICIOSO sin ningún contexto -- un comentario de código
    de lo más normal bastaba para tumbar un PR benigno a rojo. Revertido:
    esta capa ya no hace ese escaneo (ver el comentario en `analyze()`)."""
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="src/app.py",
                status=FileStatus.MODIFIED,
                diff_hunk=diff_hunk,
                additions=1,
                deletions=0,
            )
        ]
    )

    with patch.object(layer, "_get_rules_dir", return_value=None):
        res = layer.analyze(diff, {})

    assert res.risk_score == 0
    assert res.threat_nature != ThreatNature.MALICIOUS
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
    """Las cachés de proceso de static_layer (_yara_rules_cache y
    _verified_rules_view_cache) se limpian antes/después de cada test para
    que no haya contaminación entre tests con distintos `tmp_path` (que ya
    son únicos por test, pero esto lo deja explícito y hermético) -- sin
    esto, una vista verificada cacheada por un test se serviría tal cual
    al siguiente mientras su tmp_path siga existiendo."""
    static_layer_module._yara_rules_cache.clear()
    static_layer_module._verified_rules_view_cache.clear()
    yield
    static_layer_module._yara_rules_cache.clear()
    static_layer_module._verified_rules_view_cache.clear()


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


def test_analyze_runs_yara_and_full_semgrep_catalog_on_unrecognized_extension(tmp_path) -> None:
    """Un webshell con extensión .asp (que _detect_language no reconoce)
    debe seguir siendo detectado por YARA -- ver el comentario en
    analyze() -- Y además Semgrep debe recibir ese fichero agrupado bajo
    _UNRECOGNIZED_LANGUAGE_KEY (catálogo completo), no saltárselo."""
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

    languages_seen: list[str] = []

    def _fake_run_semgrep_on_files(temp_paths, language, rules_dir):
        languages_seen.append(language)
        return {p: [] for p in temp_paths}

    with (
        patch.object(layer, "_get_rules_dir", return_value=tmp_path),
        patch.object(layer, "_run_semgrep_on_files", side_effect=_fake_run_semgrep_on_files),
    ):
        res = layer.analyze(diff, {})

    # Semgrep SÍ se invocó para este fichero -- ya no se salta por no
    # reconocer la extensión, se agrupa bajo la clave "catch-all".
    assert languages_seen == [static_layer_module._UNRECOGNIZED_LANGUAGE_KEY]

    assert res.skipped is False
    assert res.risk_score == 83
    assert any(f.threat_nature == ThreatNature.MALICIOUS for f in res.findings)


def test_build_semgrep_config_paths_unrecognized_language_scans_full_catalog(tmp_path) -> None:
    """Estrategia 0 de _build_semgrep_config_paths: un lenguaje no
    reconocido no produce una lista vacía de --config (lo que equivaldría
    a "no pasar ninguna regla") -- apunta a la raíz de rules/semgrep
    entero, que Semgrep recorre recursivamente (todos los lenguajes,
    third-party, regex, watchgate.yml)."""
    layer = StaticLayer()
    semgrep_root = tmp_path / "rules" / "semgrep"
    (semgrep_root / "custom" / "python").mkdir(parents=True)

    config_paths = layer._build_semgrep_config_paths(
        static_layer_module._UNRECOGNIZED_LANGUAGE_KEY, tmp_path
    )

    assert config_paths == [f"--config={semgrep_root}"]


def _write_manifest(tmp_path: Path, official_registry_configs) -> None:
    manifest_path = tmp_path / "rules" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"version": "v0.0.1", "official_registry_configs": official_registry_configs}),
        encoding="utf-8",
    )


def test_get_official_registry_configs_no_manifest_returns_empty(tmp_path) -> None:
    """Sin rules/manifest.json (p. ej. pasos 1/2/4 de _get_rules_dir, que
    nunca traen manifest), la ausencia se degrada a lista vacía -- nunca
    lanza ni aborta el análisis."""
    layer = StaticLayer()
    assert layer._get_official_registry_configs(tmp_path) == []


def test_get_official_registry_configs_filters_invalid_entries(tmp_path) -> None:
    """Solo se aceptan IDs con el charset seguro del registro oficial
    (prefijo p/ o r/); cualquier otra cosa -- flag injection, ruta, tipo
    equivocado -- se descarta en vez de colarse como argumento de Semgrep."""
    _write_manifest(
        tmp_path,
        [
            "p/security-audit",
            "r/python.lang.security.audit",
            "--dangerously-allow-arbitrary-code-execution",
            "/etc/passwd",
            "q/not-a-real-prefix",
            123,
        ],
    )
    layer = StaticLayer()

    configs = layer._get_official_registry_configs(tmp_path)

    assert configs == ["p/security-audit", "r/python.lang.security.audit"]


def test_get_official_registry_configs_missing_field_returns_empty(tmp_path) -> None:
    """Un manifest.json válido pero sin el campo (p. ej. una versión
    publicada antes de que existiera) se degrada a lista vacía."""
    manifest_path = tmp_path / "rules" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({"version": "v0.0.1"}), encoding="utf-8")
    layer = StaticLayer()

    assert layer._get_official_registry_configs(tmp_path) == []


def test_build_semgrep_config_paths_appends_official_registry_configs(tmp_path) -> None:
    """_build_semgrep_config_paths añade un --config=<id> por cada entrada
    válida de official_registry_configs, DESPUÉS de las rutas locales."""
    semgrep_root = tmp_path / "rules" / "semgrep"
    (semgrep_root / "custom" / "python").mkdir(parents=True)
    _write_manifest(tmp_path, ["p/security-audit"])
    layer = StaticLayer()

    config_paths = layer._build_semgrep_config_paths("python", tmp_path)

    assert config_paths[-1] == "--config=p/security-audit"
    assert f"--config={semgrep_root / 'custom' / 'python'}" in config_paths


def test_build_semgrep_config_paths_unrecognized_language_appends_official_registry_configs(
    tmp_path,
) -> None:
    """La estrategia 0 (catch-all) también pide el registro oficial, no
    solo el catálogo local completo."""
    semgrep_root = tmp_path / "rules" / "semgrep"
    (semgrep_root / "custom" / "python").mkdir(parents=True)
    _write_manifest(tmp_path, ["p/security-audit"])
    layer = StaticLayer()

    config_paths = layer._build_semgrep_config_paths(
        static_layer_module._UNRECOGNIZED_LANGUAGE_KEY, tmp_path
    )

    assert config_paths == [f"--config={semgrep_root}", "--config=p/security-audit"]


def test_prepare_files_for_scanning_groups_unrecognized_extension_as_catch_all(tmp_path) -> None:
    """_prepare_files_for_scanning ya no descarta los ficheros de extensión
    no reconocida antes de llegar a Semgrep -- los mete en
    language_groups[_UNRECOGNIZED_LANGUAGE_KEY]."""
    layer = StaticLayer()
    diff = _make_diff(
        [
            FileChange(
                path="shell.asp",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -0,0 +1,1 @@\n+x",
                additions=1,
                deletions=0,
            )
        ]
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        _ordered, _yara, language_groups = layer._prepare_files_for_scanning(
            diff, tmp_path, temp_dir
        )

    assert list(language_groups.keys()) == [static_layer_module._UNRECOGNIZED_LANGUAGE_KEY]
    ((_temp_path, file_change),) = language_groups[static_layer_module._UNRECOGNIZED_LANGUAGE_KEY]
    assert file_change.path == "shell.asp"


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

    semgrep_findings = [
        {"tool": "semgrep", "rule_id": "some-rule", "message": "x", "risk_score": 30}
    ]

    def _fake_run_semgrep_on_files(temp_paths, language, rules_dir):
        return {p: list(semgrep_findings) for p in temp_paths}

    with (
        patch.object(layer, "_get_rules_dir", return_value=tmp_path),
        patch.object(layer, "_run_semgrep_on_files", side_effect=_fake_run_semgrep_on_files),
    ):
        res = layer.analyze(diff, {})

    # max(30, 83) = 83, NUNCA 30 + 83 = 113
    assert res.risk_score == 83


def test_infer_threat_nature_from_semgrep_metadata_variations() -> None:
    fn = static_layer_module._infer_threat_nature_from_semgrep

    # 1. Metadata explícita
    assert fn({"metadata": {"threat_nature": "malicioso"}}, "r1") == ThreatNature.MALICIOUS
    assert fn({"metadata": {"threat_nature": "vulnerabilidad"}}, "r1") == ThreatNature.VULNERABILITY

    # 2. Keywords en categoría o id de regla
    assert fn({"metadata": {"category": "backdoor"}}, "rule1") == ThreatNature.MALICIOUS
    assert fn({"metadata": {"subcategory": "trojan"}}, "rule1") == ThreatNature.MALICIOUS
    assert fn({}, "custom.malware.detector") == ThreatNature.MALICIOUS

    # 3. Defectos / Vulnerabilidades normales
    assert fn({"metadata": {"category": "security"}}, "owasp.sqli") == ThreatNature.VULNERABILITY
    assert fn(None, "custom.rule") == ThreatNature.VULNERABILITY


def test_get_rules_dir_env_var_override(monkeypatch, tmp_path) -> None:
    layer = StaticLayer()
    monkeypatch.setenv("WATCHGATE_SEMGREP_RULES_DIR", str(tmp_path))
    assert layer._get_rules_dir() == tmp_path


def test_get_rules_dir_persistent_cache_valid_and_expired(monkeypatch, tmp_path) -> None:
    layer = StaticLayer()
    monkeypatch.delenv("WATCHGATE_SEMGREP_RULES_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cache_base = tmp_path / ".watchgate" / "rules_cache"
    cached_repo_dir = cache_base / "Repo-reglas-SEMGREP-y-YARA"
    cached_repo_dir.mkdir(parents=True)
    timestamp_file = cache_base / ".last_updated"

    # Evitar que las comprobaciones de reglas locales (prioridades 3 y 4) coincidan
    with patch("watchgate.core.layers.static_layer.any", return_value=False):
        # 1. Caché válida reciente
        timestamp_file.write_text(str(static_layer_module.time.time()), encoding="utf-8")
        res = layer._get_rules_dir()
        assert res == cached_repo_dir

        # 2. Caché expirada (> 24h)
        timestamp_file.write_text("0.0", encoding="utf-8")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            res_expired = layer._get_rules_dir()
            assert res_expired == cached_repo_dir
            mock_run.assert_called()


def test_get_rules_dir_clones_when_no_cache_and_handles_error(monkeypatch, tmp_path) -> None:
    layer = StaticLayer()
    monkeypatch.delenv("WATCHGATE_SEMGREP_RULES_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cache_base = tmp_path / ".watchgate" / "rules_cache"
    cached_repo_dir = cache_base / "Repo-reglas-SEMGREP-y-YARA"

    with patch("watchgate.core.layers.static_layer.any", return_value=False):
        # Simular clonación fallida
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Failed to clone")
            res_failed = layer._get_rules_dir()
            assert res_failed is None

        # Simular clonación exitosa
        def fake_clone(*args, **kwargs):
            cached_repo_dir.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_clone):
            res_success = layer._get_rules_dir()
            assert res_success == cached_repo_dir


# --------------------------------------------------------------------------
# Paso 0 de _get_rules_dir: verificación bajo demanda contra la última
# versión publicada, vía local_rules_client.get_verified_rules (ver
# docs/integracion_repo_reglas.md §9). `_import_local_rules_client` se
# sustituye por un doble en todos estos tests -- la mecánica real de
# local_rules_client.py ya se prueba aparte en
# tests/unit/test_local_rules_client*.py.
# --------------------------------------------------------------------------


class _FakeRulesClientError(RuntimeError):
    pass


class _FakeRulesVerificationError(RuntimeError):
    pass


def _make_fake_local_rules_client(get_verified_rules=None, repo_cache_dir_path: Path | None = None):
    """Doble mínimo de scripts/local_rules_client.py: mismas dos
    excepciones (con los mismos nombres, para que `except
    local_rules_client.RulesClientError` del código real las reconozca) y
    `repo_cache_dir()` / `get_verified_rules()`."""
    module = types.SimpleNamespace()
    module.RulesClientError = _FakeRulesClientError
    module.RulesVerificationError = _FakeRulesVerificationError
    module.get_verified_rules = get_verified_rules or (lambda **kwargs: None)
    module.repo_cache_dir = lambda: repo_cache_dir_path
    return module


def test_get_verified_rules_dir_returns_none_without_token(monkeypatch) -> None:
    monkeypatch.delenv("RULES_REPO_TOKEN", raising=False)
    layer = StaticLayer()

    def _fail_if_called():
        pytest.fail("no debería importar local_rules_client sin RULES_REPO_TOKEN")

    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", _fail_if_called)

    assert layer._get_verified_rules_dir() is None


def test_get_verified_rules_dir_returns_none_when_scripts_module_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: None)
    layer = StaticLayer()

    assert layer._get_verified_rules_dir() is None


def test_get_verified_rules_dir_falls_back_on_client_error(monkeypatch) -> None:
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")

    def raise_client_error(**kwargs):
        raise _FakeRulesClientError("falta red")

    fake_module = _make_fake_local_rules_client(get_verified_rules=raise_client_error)
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: fake_module)

    layer = StaticLayer()
    assert layer._get_verified_rules_dir() is None


def test_get_verified_rules_dir_falls_back_on_verification_error(monkeypatch) -> None:
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")

    def raise_verification_error(**kwargs):
        raise _FakeRulesVerificationError("clave manipulada")

    fake_module = _make_fake_local_rules_client(get_verified_rules=raise_verification_error)
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: fake_module)

    layer = StaticLayer()
    assert layer._get_verified_rules_dir() is None


def test_get_verified_rules_dir_falls_back_on_unexpected_exception(monkeypatch) -> None:
    """Ningún fallo de este paso debe propagar ni abortar el análisis --
    ni siquiera uno inesperado (p. ej. un error de red sin envolver)."""
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")

    def raise_unexpected(**kwargs):
        raise ConnectionError("sin red")

    fake_module = _make_fake_local_rules_client(get_verified_rules=raise_unexpected)
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: fake_module)

    layer = StaticLayer()
    assert layer._get_verified_rules_dir() is None


def test_get_verified_rules_dir_requests_the_full_catalog(monkeypatch, tmp_path) -> None:
    """Pide TODO el catálogo (no solo los lenguajes del diff actual):
    _get_rules_dir() se resuelve UNA vez por analyze(), antes de saber qué
    lenguajes trae el diff -- ver docstring de _get_verified_rules_dir."""
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")
    seen_kwargs = {}

    def fake_get_verified_rules(**kwargs):
        seen_kwargs.update(kwargs)
        return types.SimpleNamespace(version="v0.0.5", custom={}, third_party={}, yara={})

    fake_module = _make_fake_local_rules_client(
        get_verified_rules=fake_get_verified_rules, repo_cache_dir_path=tmp_path / "rules-repo"
    )
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: fake_module)

    StaticLayer()._get_verified_rules_dir()

    assert seen_kwargs == {
        "include_all_custom": True,
        "include_all_third_party": True,
        "include_yara": True,
    }


def test_get_verified_rules_dir_materializes_expected_layout(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")

    src_python = tmp_path / "source" / "custom-python"
    (src_python).mkdir(parents=True)
    (src_python / "r.yaml").write_text("regla-python", encoding="utf-8")

    src_third_party = tmp_path / "source" / "trailofbits-rs"
    src_third_party.mkdir(parents=True)
    (src_third_party / "r.yaml").write_text("regla-rust-third-party", encoding="utf-8")

    src_yara = tmp_path / "source" / "webshells"
    src_yara.mkdir(parents=True)
    (src_yara / "w.yar").write_text("rule w {}", encoding="utf-8")

    fake_rules = types.SimpleNamespace(
        version="v0.0.5",
        custom={"python": src_python},
        third_party={"trailofbits/rs": src_third_party},
        yara={"webshells": src_yara},
    )
    fake_module = _make_fake_local_rules_client(
        get_verified_rules=lambda **kwargs: fake_rules,
        repo_cache_dir_path=tmp_path / "cache" / "rules-repo",
    )
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: fake_module)

    layer = StaticLayer()
    view_root = layer._get_verified_rules_dir()

    assert view_root == tmp_path / "cache" / "rules-view" / "v0.0.5"
    python_rule = view_root / "rules" / "semgrep" / "custom" / "python" / "r.yaml"
    third_party_rule = (
        view_root / "rules" / "semgrep" / "third-party" / "trailofbits" / "rs" / "r.yaml"
    )
    yara_rule = view_root / "rules" / "yara" / "webshells" / "w.yar"
    assert python_rule.read_text(encoding="utf-8") == "regla-python"
    assert third_party_rule.read_text(encoding="utf-8") == "regla-rust-third-party"
    assert yara_rule.read_text(encoding="utf-8") == "rule w {}"


def test_get_verified_rules_dir_materializes_manifest_for_official_registry_configs(
    monkeypatch, tmp_path
) -> None:
    """`_sync_rules_view` también escribe rules/manifest.json en la vista
    local -- es lo que luego lee `_get_official_registry_configs` (paso 0
    de _get_rules_dir, igual que el checkout de CI vía sync_rules.py)."""
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")

    fake_rules = types.SimpleNamespace(
        version="v0.0.5",
        custom={},
        third_party={},
        yara={},
        manifest={"version": "v0.0.5", "official_registry_configs": ["p/security-audit"]},
    )
    fake_module = _make_fake_local_rules_client(
        get_verified_rules=lambda **kwargs: fake_rules,
        repo_cache_dir_path=tmp_path / "cache" / "rules-repo",
    )
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: fake_module)

    layer = StaticLayer()
    view_root = layer._get_verified_rules_dir()

    assert layer._get_official_registry_configs(view_root) == ["p/security-audit"]


def test_get_verified_rules_dir_view_path_changes_with_active_version(
    monkeypatch, tmp_path
) -> None:
    """Requisito clave para un proceso de larga duración (Engine API,
    dashboard backend): si la versión activa cambia entre dos llamadas, la
    ruta devuelta cambia con ella -- así las cachés de proceso existentes
    (_yara_rules_cache, _semgrep_finding_type_cache), indexadas por esa
    ruta, dejan de servir contenido de la versión anterior.

    Desde la caché TTL de _get_verified_rules_dir, este contrato es "el
    cambio de versión se propaga al expirar el TTL" (1h por defecto), no
    "inmediatamente" -- TTL=0 fuerza el modo verificar-siempre, que es
    donde el mecanismo de ruta-por-versión que valida este test actúa en
    cada llamada."""
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")
    monkeypatch.setenv("WATCHGATE_RULES_VERIFY_TTL_SECONDS", "0")
    current_version = {"value": "v0.0.5"}

    def fake_get_verified_rules(**kwargs):
        return types.SimpleNamespace(
            version=current_version["value"], custom={}, third_party={}, yara={}
        )

    fake_module = _make_fake_local_rules_client(
        get_verified_rules=fake_get_verified_rules, repo_cache_dir_path=tmp_path / "rules-repo"
    )
    monkeypatch.setattr(static_layer_module, "_import_local_rules_client", lambda: fake_module)

    layer = StaticLayer()
    first = layer._get_verified_rules_dir()
    current_version["value"] = "v0.0.6"
    second = layer._get_verified_rules_dir()

    assert first != second
    assert first.name == "v0.0.5"
    assert second.name == "v0.0.6"


def test_get_rules_dir_prefers_verified_rules_when_available(tmp_path) -> None:
    layer = StaticLayer()
    with patch.object(layer, "_get_verified_rules_dir", return_value=tmp_path / "verified-view"):
        assert layer._get_rules_dir() == tmp_path / "verified-view"


def test_get_rules_dir_falls_back_to_existing_steps_when_verified_unavailable(tmp_path) -> None:
    layer = StaticLayer(rules_dir_override=tmp_path)
    with patch.object(layer, "_get_verified_rules_dir", return_value=None):
        assert layer._get_rules_dir() == tmp_path


def test_sanitize_version_for_path_leaves_normal_versions_untouched() -> None:
    assert static_layer_module._sanitize_version_for_path("v0.0.5") == "v0.0.5"


def test_sanitize_version_for_path_replaces_unsafe_characters() -> None:
    assert static_layer_module._sanitize_version_for_path("../../etc") == ".._.._etc"


def test_sanitize_version_for_path_falls_back_to_unknown_when_empty() -> None:
    assert static_layer_module._sanitize_version_for_path("   ") == "unknown"


def test_import_local_rules_client_resolves_the_real_module() -> None:
    """Sanity check contra el fichero real (sin red: solo comprueba que el
    mecanismo de import bajo demanda funciona y expone lo que
    _get_verified_rules_dir necesita)."""
    module = static_layer_module._import_local_rules_client()
    assert module is not None
    assert callable(module.get_verified_rules)
    assert callable(module.repo_cache_dir)
    assert issubclass(module.RulesVerificationError, module.RulesClientError)


def test_get_verified_rules_dir_caches_successful_resolution_across_instances(
    monkeypatch, tmp_path
) -> None:
    """Regresión de eficiencia: `get_verified_rules()` pide SIEMPRE el
    manifest.json remoto, y el orquestador crea una StaticLayer nueva por
    análisis -- sin la caché de módulo, cada PR pagaba una llamada de red
    + verificación de hashes. Una resolución con éxito debe reutilizarse
    dentro del TTL, incluso desde una instancia distinta."""
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")
    static_layer_module._verified_rules_view_cache.clear()
    view = tmp_path / "rules-view" / "v9"
    view.mkdir(parents=True)
    calls: list[int] = []
    monkeypatch.setattr(
        StaticLayer,
        "_resolve_verified_rules_dir",
        lambda self: calls.append(1) or view,
    )
    try:
        assert StaticLayer()._get_verified_rules_dir() == view
        assert StaticLayer()._get_verified_rules_dir() == view
        assert len(calls) == 1, "la segunda instancia debe servirse de la caché"
    finally:
        static_layer_module._verified_rules_view_cache.clear()


def test_get_verified_rules_dir_does_not_cache_failures(monkeypatch) -> None:
    """Un fallo (sin red, verificación fallida) no debe quedarse cacheado:
    el siguiente análisis reintenta -- una regla nueva no puede quedarse
    fuera una hora por un error transitorio."""
    monkeypatch.setenv("RULES_REPO_TOKEN", "fake-token")
    static_layer_module._verified_rules_view_cache.clear()
    calls: list[int] = []
    monkeypatch.setattr(
        StaticLayer,
        "_resolve_verified_rules_dir",
        lambda self: calls.append(1),  # devuelve None
    )
    try:
        layer = StaticLayer()
        assert layer._get_verified_rules_dir() is None
        assert layer._get_verified_rules_dir() is None
        assert len(calls) == 2
        assert static_layer_module._verified_rules_view_cache == {}
    finally:
        static_layer_module._verified_rules_view_cache.clear()


def test_rules_verify_ttl_seconds_parsing(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_RULES_VERIFY_TTL_SECONDS", raising=False)
    assert static_layer_module._rules_verify_ttl_seconds() == 3600.0
    monkeypatch.setenv("WATCHGATE_RULES_VERIFY_TTL_SECONDS", "abc")
    assert static_layer_module._rules_verify_ttl_seconds() == 3600.0
    monkeypatch.setenv("WATCHGATE_RULES_VERIFY_TTL_SECONDS", "0")
    assert static_layer_module._rules_verify_ttl_seconds() == 0.0
