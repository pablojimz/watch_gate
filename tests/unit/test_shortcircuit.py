"""Tests de shortcircuit.py (spec §11, A.3.4)."""

from __future__ import annotations

from watchgate.core.models import (
    Confidence,
    FileChange,
    FileStatus,
    LayerResult,
    NormalizedDiff,
    Semaforo,
    ThreatNature,
)
from watchgate.core.shortcircuit import (
    _has_new_dependencies,
    _has_new_network_calls,
    _matches_forcing_pattern,
    evaluate_shortcircuit,
)

_WEIGHTS = {"static": 0.25, "deps": 0.20, "reputation": 0.15, "semantic": 0.40}
_THRESHOLDS = {"yellow": 40, "red": 70}


def _lr(name: str, score: int, skipped: bool = False) -> LayerResult:
    return LayerResult(layer_name=name, risk_score=score, justification="x", skipped=skipped)


def _diff_with_paths(*paths_and_hunks: tuple[str, str]) -> NormalizedDiff:
    files = [
        FileChange(path=p, status=FileStatus.MODIFIED, diff_hunk=h, additions=1, deletions=0)
        for p, h in paths_and_hunks
    ]
    return NormalizedDiff(
        base_sha="a", head_sha="b", repo_path=".", files=files, commit_messages=[], authors=[]
    )


def test_high_partial_score_shortcircuits_to_rojo_when_min_possible_score_meets_red_threshold():
    """Si el score mínimo global posible (con semántica = 0) sigue siendo >= red threshold,
    sí se cortocircuita a ROJO."""
    heavy_partial_weights = {"static": 0.40, "deps": 0.30, "reputation": 0.20, "semantic": 0.10}
    partial = {
        "static": _lr("static", 90),
        "deps": _lr("deps", 90),
        "reputation": _lr("reputation", 90),
    }
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    result = evaluate_shortcircuit(
        partial,
        heavy_partial_weights,
        diff,
        _THRESHOLDS,
        rng=lambda: 0.99,
    )

    assert result == Semaforo.ROJO


def test_high_partial_score_does_not_shortcircuit_if_semantic_could_lower_to_yellow():
    """Con pesos por defecto (semántica 0.40), partial_score=100 da un score mínimo
    global de 60 si semántica fuera 0. Como 60 < red (70), NO debe cortocircuitar a ROJO."""
    partial = {
        "static": _lr("static", 100),
        "deps": _lr("deps", 100),
        "reputation": _lr("reputation", 100),
    }
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    result = evaluate_shortcircuit(
        partial,
        _WEIGHTS,  # semantic weight is 0.40
        diff,
        _THRESHOLDS,
        rng=lambda: 0.99,
    )

    assert result is None


def test_low_partial_score_and_no_forcing_shortcircuits_to_verde():
    partial = {
        "static": _lr("static", 5),
        "deps": _lr("deps", 5),
        "reputation": _lr("reputation", 5),
    }
    diff = _diff_with_paths(("normal_file.py", "+ print(1)"))

    # rng() >= 1/20 -> no cae en el muestreo de auditoría.
    result = evaluate_shortcircuit(partial, _WEIGHTS, diff, _THRESHOLDS, rng=lambda: 0.5)

    assert result == Semaforo.VERDE


def test_low_partial_score_but_audit_sample_forces_semantic():
    partial = {
        "static": _lr("static", 5),
        "deps": _lr("deps", 5),
        "reputation": _lr("reputation", 5),
    }
    diff = _diff_with_paths(("normal_file.py", "+ print(1)"))
    audit_calls: list[None] = []

    result = evaluate_shortcircuit(
        partial,
        _WEIGHTS,
        diff,
        _THRESHOLDS,
        rng=lambda: 0.01,  # < 1/20 -> cae en el muestreo
        on_audit_sample=lambda: audit_calls.append(None),
    )

    assert result is None  # fuerza semántica igualmente
    assert len(audit_calls) == 1


def test_forcing_pattern_prevents_verde_shortcircuit_even_with_low_score():
    partial = {
        "static": _lr("static", 5),
        "deps": _lr("deps", 5),
        "reputation": _lr("reputation", 5),
    }
    diff = _diff_with_paths(("PKGBUILD", "+ source=https://example.com"))

    result = evaluate_shortcircuit(partial, _WEIGHTS, diff, _THRESHOLDS, rng=lambda: 0.99)

    assert result is None  # no se cortocircuita, hay que llamar a semántica


def test_medium_partial_score_never_shortcircuits():
    """Ni >= red ni < yellow*0.5: siempre None (zona intermedia, se ejecuta
    la capa semántica sin excepción)."""
    partial = {
        "static": _lr("static", 45),
        "deps": _lr("deps", 45),
        "reputation": _lr("reputation", 45),
    }
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    result = evaluate_shortcircuit(partial, _WEIGHTS, diff, _THRESHOLDS, rng=lambda: 0.99)

    assert result is None


def test_semantic_layer_excluded_from_partial_score_even_if_present():
    """Si por lo que sea partial_results ya trajera una entrada 'semantic'
    (no debería, pero por robustez), no debe contar en el score parcial."""
    heavy_partial_weights = {"static": 0.40, "deps": 0.30, "reputation": 0.20, "semantic": 0.10}
    partial = {
        "static": _lr("static", 90),
        "deps": _lr("deps", 90),
        "reputation": _lr("reputation", 90),
        "semantic": _lr("semantic", 0),  # no debería influir
    }
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    result = evaluate_shortcircuit(
        partial, heavy_partial_weights, diff, _THRESHOLDS, rng=lambda: 0.99
    )

    assert result == Semaforo.ROJO


def test_matches_forcing_pattern_detects_dockerfile_and_workflow():
    diff = _diff_with_paths((".github/workflows/ci.yml", "+ run: echo hi"))
    assert _matches_forcing_pattern(diff) is True

    diff2 = _diff_with_paths(("src/app.py", "+ print(1)"))
    assert _matches_forcing_pattern(diff2) is False


def test_has_new_network_calls_detects_requests_get():
    diff = _diff_with_paths(("script.py", "+ requests.get('http://evil.com')"))
    assert _has_new_network_calls(diff) is True

    diff2 = _diff_with_paths(("script.py", "+ x = 1"))
    assert _has_new_network_calls(diff2) is False


def test_has_new_network_calls_ignores_binary_files():
    binary_file = FileChange(
        path="image.png",
        status=FileStatus.MODIFIED,
        diff_hunk="requests.get(",  # aunque "contenga" el patrón, es binario
        additions=0,
        deletions=0,
        is_binary=True,
    )
    diff = NormalizedDiff(
        base_sha="a",
        head_sha="b",
        repo_path=".",
        files=[binary_file],
        commit_messages=[],
        authors=[],
    )
    assert _has_new_network_calls(diff) is False


def test_has_new_dependencies_detects_package_json():
    diff = _diff_with_paths(("package.json", '+ "lodash": "1.0.0"'))
    assert _has_new_dependencies(diff) is True

    diff2 = _diff_with_paths(("src/index.js", "+ console.log(1)"))
    assert _has_new_dependencies(diff2) is False


def test_has_new_dependencies_detects_requirements_txt():
    diff = _diff_with_paths(("requirements.txt", "+ requests==2.31.0"))
    assert _has_new_dependencies(diff) is True


def test_has_new_dependencies_detects_pipfile():
    diff = _diff_with_paths(("Pipfile", '+ requests = "*"'))
    assert _has_new_dependencies(diff) is True


def test_has_new_dependencies_detects_pkgbuild():
    diff = _diff_with_paths(("PKGBUILD", "+ depends=('glibc')"))
    assert _has_new_dependencies(diff) is True


def test_has_new_dependencies_detects_cargo_toml():
    diff = _diff_with_paths(("Cargo.toml", '+ serde = "1.0"'))
    assert _has_new_dependencies(diff) is True


def test_has_new_dependencies_detects_go_mod():
    diff = _diff_with_paths(("go.mod", "+ require github.com/pkg/errors v0.9.1"))
    assert _has_new_dependencies(diff) is True


def test_has_new_dependencies_detects_composer_json():
    diff = _diff_with_paths(("composer.json", '+ "monolog/monolog": "^2.0"'))
    assert _has_new_dependencies(diff) is True


def test_has_new_dependencies_matches_by_exact_basename():
    """El nombre de fichero se compara tras el último '/' y debe coincidir
    exactamente con la lista -- un manifiesto en un subdirectorio se sigue
    detectando, pero un nombre parecido que no sea exacto no cuenta."""
    diff = _diff_with_paths(("vendor/Cargo.toml", '+ serde = "1.0"'))
    assert _has_new_dependencies(diff) is True

    diff2 = _diff_with_paths(("Cargo.toml.bak", '+ serde = "1.0"'))
    assert _has_new_dependencies(diff2) is False


def test_has_new_dependencies_ignores_unsupported_ecosystem_manifest():
    """Un manifiesto de un ecosistema no soportado (aquí, Ruby/Bundler) no
    debe contar, aunque el nombre también "suene" a fichero de dependencias
    -- la función es una intersección exacta contra
    DEPENDENCY_MANIFEST_FILENAMES, no una heurística por parecido."""
    diff = _diff_with_paths(("Gemfile", '+ gem "rails", "7.0.0"'))
    assert _has_new_dependencies(diff) is False


def test_shortcircuit_handles_skipped_partial_layers():
    """Capas parciales omitidas no influyen en la media ponderada."""
    weights = {"static": 0.50, "deps": 0.20, "reputation": 0.10, "semantic": 0.20}
    partial = {
        "static": _lr("static", 100),
        "deps": _lr("deps", 0, skipped=True),
        "reputation": _lr("reputation", 100),
    }
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    # Active partial weight = static (0.50) + reputation (0.10) = 0.60
    # Weighted sum = 0.50*100 + 0.10*100 = 60
    # Total weight = 0.60 + 0.20 (semantic) = 0.80
    # Min possible score = 60 / 0.80 = 75 >= 70 (ROJO)
    result = evaluate_shortcircuit(partial, weights, diff, _THRESHOLDS, rng=lambda: 0.99)
    assert result == Semaforo.ROJO


def test_shortcircuit_rounding_boundary():
    """Verifica que el redondeo de min_possible_score respete el umbral red exactamente."""
    weights = {"static": 0.694, "semantic": 0.306}
    partial = {"static": _lr("static", 100)}
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    # Min possible = 69.4 / 1.00 = 69.4 -> round(69.4) = 69 < 70 -> None
    result_under = evaluate_shortcircuit(partial, weights, diff, _THRESHOLDS, rng=lambda: 0.99)
    assert result_under is None

    weights_over = {"static": 0.696, "semantic": 0.304}
    # Min possible = 69.6 / 1.00 = 69.6 -> round(69.6) = 70 >= 70 -> ROJO
    result_over = evaluate_shortcircuit(partial, weights_over, diff, _THRESHOLDS, rng=lambda: 0.99)
    assert result_over == Semaforo.ROJO


def test_malicious_without_stated_confidence_does_not_shortcircuit_to_rojo():
    """Caso real encontrado en revisión: `deps_layer.py` nunca rellena
    `confidence` (siempre None) y puntúa 75-80 para patrones habituales y a
    menudo legítimos con `threat_nature=MALICIOUS`. Antes bastaba
    `risk_score >= red threshold` (sin mirar confidence) para cortocircuitar
    directo a ROJO, sin darle nunca a la capa semántica la oportunidad de
    matizarlo -- reproducido con una dependencia pinneada a una URL de git
    (patrón legítimo). Con `shortcircuit_enabled` (opt-in) esto bloqueaba un
    PR benigno antes incluso de llamar al LLM."""
    weights = {"static": 0.25, "deps": 0.20, "reputation": 0.15, "semantic": 0.40}
    partial = {
        "static": _lr("static", 0),
        "deps": LayerResult(
            layer_name="deps",
            risk_score=75,
            justification="Instalación directa desde URL/Git",
            threat_nature=ThreatNature.MALICIOUS,
            confidence=None,
        ),
        "reputation": _lr("reputation", 5),
    }
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    result = evaluate_shortcircuit(partial, weights, diff, _THRESHOLDS, rng=lambda: 0.99)

    assert result != Semaforo.ROJO


def test_malicious_with_high_confidence_still_shortcircuits_to_rojo():
    """Caso simétrico al anterior: una capa que SÍ declara `confidence=ALTA`
    de verdad debe seguir cortocircuitando a ROJO -- el fix no elimina la
    protección, solo exige que la confianza sea real."""
    weights = {"static": 0.25, "deps": 0.20, "reputation": 0.15, "semantic": 0.40}
    partial = {
        "static": _lr("static", 0),
        "deps": LayerResult(
            layer_name="deps",
            risk_score=75,
            justification="Script de instalación con exfiltración confirmada",
            threat_nature=ThreatNature.MALICIOUS,
            confidence=Confidence.ALTA,
        ),
        "reputation": _lr("reputation", 5),
    }
    diff = _diff_with_paths(("a.py", "+ x = 1"))

    result = evaluate_shortcircuit(partial, weights, diff, _THRESHOLDS, rng=lambda: 0.99)

    assert result == Semaforo.ROJO
