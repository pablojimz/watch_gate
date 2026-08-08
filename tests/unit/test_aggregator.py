"""Tests de aggregator.py (spec §10)."""

from __future__ import annotations

from watchgate.core.aggregator import aggregate
from watchgate.core.comment_template import render_comment
from watchgate.core.models import (
    Confidence,
    Finding,
    LayerResult,
    RiskCategory,
    Semaforo,
    ThreatNature,
)


def _result(
    name: str,
    score: int,
    skipped: bool = False,
    skip_reason: str | None = None,
    category: RiskCategory | None = None,
    confidence: Confidence | None = None,
) -> LayerResult:
    return LayerResult(
        layer_name=name,
        risk_score=score,
        justification=f"justificación de {name}",
        skipped=skipped,
        skip_reason=skip_reason,
        category=category,
        confidence=confidence,
    )


def test_regresion_literal_memoria_score_47_amarillo():
    """Test de regresión que no debe fallar nunca (spec §10): con estática 20,
    deps 10, reputación 40, semántica 85 y pesos 0.25/0.20/0.15/0.40, el
    resultado exacto de la memoria es score == 47, semaforo == AMARILLO."""
    results = {
        "static": _result("static", 20),
        "deps": _result("deps", 10),
        "reputation": _result("reputation", 40),
        "semantic": _result("semantic", 85),
    }
    weights = {"static": 0.25, "deps": 0.20, "reputation": 0.15, "semantic": 0.40}

    out = aggregate(results, weights, diff=None, pr_id="42", repo="org/repo")

    assert out.score == 47
    assert out.semaforo == Semaforo.AMARILLO


def test_skipped_layer_excluded_from_weighted_average():
    results = {
        "static": _result("static", 90),
        "semantic": _result("semantic", 0, skipped=True, skip_reason="presupuesto agotado"),
    }
    weights = {"static": 0.5, "semantic": 0.5}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    # Solo "static" cuenta: score == 90 -> ROJO.
    assert out.score == 90
    assert out.semaforo == Semaforo.ROJO


def test_all_layers_skipped_does_not_divide_by_zero():
    results = {
        "static": _result("static", 0, skipped=True, skip_reason="sin ficheros de código"),
    }
    weights = {"static": 1.0}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 0
    assert out.semaforo == Semaforo.VERDE


def test_thresholds_boundaries():
    weights = {"static": 1.0}

    verde = aggregate({"static": _result("static", 39)}, weights, None, "1", "r")
    amarillo = aggregate({"static": _result("static", 40)}, weights, None, "1", "r")
    rojo = aggregate({"static": _result("static", 70)}, weights, None, "1", "r")

    assert verde.semaforo == Semaforo.VERDE
    assert amarillo.semaforo == Semaforo.AMARILLO
    assert rojo.semaforo == Semaforo.ROJO


def test_render_comment_includes_score_and_semantic_justification():
    results = {
        "static": _result("static", 20),
        "semantic": _result("semantic", 85),
    }
    weights = {"static": 0.5, "semantic": 0.5}
    out = aggregate(results, weights, diff=None, pr_id="7", repo="org/repo")

    comment = render_comment(out)

    assert "52" in comment or str(out.score) in comment
    assert "justificación de semantic" in comment
    assert "Static: 20/100" in comment
    assert "Semantic: 85/100" in comment


def test_render_comment_shows_skip_reason_for_skipped_layer():
    results = {
        "static": _result("static", 10),
        "semantic": _result("semantic", 0, skipped=True, skip_reason="presupuesto agotado"),
    }
    weights = {"static": 1.0, "semantic": 0.0}
    out = aggregate(results, weights, diff=None, pr_id="7", repo="org/repo")

    comment = render_comment(out)

    assert "omitida: presupuesto agotado" in comment
    assert "Justificación (capa semántica):" not in comment


def test_high_confidence_severe_semantic_floors_score_to_red_despite_clean_reputation():
    """Caso real (tests/cases/malreal_npm_compromised_lib_posthog-node_2 y
    equivalentes): reputación intachable (cuenta comprometida sin señales
    propias) + semántica muy alta, de confianza y categoría backdoor. Sin
    este suelo, el combinado se queda en 65 (amarillo); con él, no debe
    poder bajar de rojo."""
    results = {
        "reputation": _result("reputation", 0),
        "semantic": _result(
            "semantic", 90, category=RiskCategory.BACKDOOR, confidence=Confidence.ALTA
        ),
    }
    weights = {"reputation": 0.15, "semantic": 0.40}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 70
    assert out.semaforo == Semaforo.ROJO


def test_semantic_floor_does_not_trigger_below_confidence_or_score_threshold():
    weights = {"reputation": 0.15, "semantic": 0.40}

    baja_confianza = aggregate(
        {
            "reputation": _result("reputation", 0),
            "semantic": _result(
                "semantic", 90, category=RiskCategory.BACKDOOR, confidence=Confidence.MEDIA
            ),
        },
        weights,
        None,
        "1",
        "r",
    )
    score_insuficiente = aggregate(
        {
            "reputation": _result("reputation", 0),
            "semantic": _result(
                "semantic", 80, category=RiskCategory.BACKDOOR, confidence=Confidence.ALTA
            ),
        },
        weights,
        None,
        "1",
        "r",
    )
    categoria_no_grave = aggregate(
        {
            "reputation": _result("reputation", 0),
            "semantic": _result(
                "semantic", 95, category=RiskCategory.NINGUNA, confidence=Confidence.ALTA
            ),
        },
        weights,
        None,
        "1",
        "r",
    )

    # Ninguno de los tres cumple las tres condiciones a la vez -- el suelo no
    # aplica, y el combinado real (bajo, por la reputación limpia) es el que manda.
    assert baja_confianza.semaforo != Semaforo.ROJO
    assert score_insuficiente.semaforo != Semaforo.ROJO
    assert categoria_no_grave.semaforo != Semaforo.ROJO


def test_high_confidence_obfuscation_semantic_floors_score_to_red():
    """Caso real (tests/cases/prompt_injection_fake_approval y
    prompt_injection_hides_real_payload): `_apply_prompt_injection_floor`
    (`_semantic/layer.py`) fuerza semantic=100/confidence=alta/categoría
    ofuscación de forma determinista y sin margen de duda -- el intento de
    manipular al revisor es la prueba en sí. Con las 5 capas reales,
    static/dependencies/vulnerabilities no tienen nada que ver en un ataque
    que vive en un comentario, así que sin este suelo el combinado se
    quedaba en 51 (amarillo) pese al 100 semántico."""
    results = {
        "static": _result("static", 0),
        "dependencies": _result("dependencies", 0),
        "vulnerabilities": _result("vulnerabilities", 0),
        "reputation": _result("reputation", 75),
        "semantic": _result(
            "semantic", 100, category=RiskCategory.OFUSCACION, confidence=Confidence.ALTA
        ),
    }
    weights = {
        "static": 0.25,
        "dependencies": 0.10,
        "vulnerabilities": 0.10,
        "reputation": 0.15,
        "semantic": 0.40,
    }

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 70
    assert out.semaforo == Semaforo.ROJO


def test_semantic_floor_never_lowers_a_score_that_was_already_higher():
    """El suelo es un `max()`, no una sustitución -- si el combinado ya era
    más alto que el umbral rojo por sí mismo, no debe tocarlo."""
    results = {
        "reputation": _result("reputation", 95),
        "semantic": _result(
            "semantic", 90, category=RiskCategory.BACKDOOR, confidence=Confidence.ALTA
        ),
    }
    weights = {"reputation": 0.5, "semantic": 0.5}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 92  # media ponderada real, sin que el suelo la baje
    assert out.semaforo == Semaforo.ROJO


def test_malicious_threat_forces_red_semaforo():
    finding = Finding(
        file_path="setup.py",
        rule_id="postinstall-script",
        message="Exfiltración en script",
        threat_nature=ThreatNature.MALICIOUS,
        severity="error",
    )
    deps_layer = LayerResult(
        layer_name="deps",
        risk_score=80,
        justification="Script malicioso",
        findings=[finding],
        confidence=Confidence.ALTA,
        threat_nature=ThreatNature.MALICIOUS,
    )
    results = {
        "reputation": _result("reputation", 0),
        "deps": deps_layer,
    }
    weights = {"reputation": 0.5, "deps": 0.5}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 100
    assert out.semaforo == Semaforo.ROJO
    assert out.threat_summary["malicioso"] == 1


def test_malicious_without_stated_confidence_does_not_force_red():
    """Caso real encontrado en revisión: `deps_layer.py` NUNCA rellena
    `confidence` (siempre None) y puntúa 75-80 para patrones habituales y a
    menudo legítimos (dependencia pinneada a una URL de git, script
    postinstall con chmod +x) con `threat_nature=MALICIOUS`. Antes, `or
    risk_score >= thresholds["red"]` trataba ese risk_score alto como si
    fuera lo mismo que alta confianza y forzaba el combinado a 100/ROJO --
    reproducido en vivo con un `package.json` que pinnea "left-pad" a un
    commit de git (patrón legítimo: fijar un hotfix aún no publicado), que
    con la config por defecto daba 100/ROJO pese a que la media ponderada
    real fuera ~10/100. Ahora, sin `confidence` declarada, esa capa cuenta
    solo por su peso normal en la media ponderada."""
    deps_layer = LayerResult(
        layer_name="dependencies",
        risk_score=75,
        justification="Instalación directa desde URL/Git",
        threat_nature=ThreatNature.MALICIOUS,
        confidence=None,
    )
    results = {
        "static": _result("static", 0),
        "dependencies": deps_layer,
        "reputation": _result("reputation", 5),
        "semantic": _result("semantic", 5),
    }
    weights = {"static": 0.25, "dependencies": 0.10, "reputation": 0.15, "semantic": 0.40}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.semaforo != Semaforo.ROJO
    assert out.score < 20


def test_uncertain_semantic_threat_nature_floors_combined_score_to_yellow():
    """Bug real encontrado regenerando el informe de validación
    (`malreal_pypi_malicious_intent_mirrorbot_10`): la escalada de
    "incertidumbre" anterior comprobaba `UNVERIFIED_CONTENT_MARKER in
    fc.diff_hunk` sobre el `NormalizedDiff` original -- pero ese marcador
    solo se inserta en el prompt que arma `prompting.py`, nunca se escribe
    de vuelta en `diff_hunk`, así que la condición era código muerto: nunca
    podía cumplirse. Caso real reproducido: la capa semántica marca
    `threat_nature=UNCERTAIN` (contenido truncado, nunca comprobado con
    fetch_referenced_file) y su propio `_apply_unverified_content_floor`
    ya sube su risk_score a 60+, pero con los pesos por defecto (semantic
    0.40) y el resto de capas activas puntuando 0 (no `skipped`, simplemente
    sin hallazgos), el combinado se queda en verde de todas formas -- pese a
    que la propia capa semántica ya señaló que no pudo comprobar el
    contenido. Ahora se consulta directamente el `threat_nature` ya
    calculado por la capa semántica, no una señal redundante y rota
    reconstruida desde el diff."""
    results = {
        "static": _result("static", 0),
        "dependencies": _result("dependencies", 0),
        "vulnerabilities": _result("vulnerabilities", 0),
        "reputation": _result("reputation", 75),
        "semantic": LayerResult(
            layer_name="semantic",
            risk_score=69,
            justification="Contenido truncado, no verificado con fetch_referenced_file.",
            threat_nature=ThreatNature.UNCERTAIN,
            confidence=Confidence.MEDIA,
        ),
    }
    weights = {
        "static": 0.25,
        "dependencies": 0.10,
        "vulnerabilities": 0.10,
        "reputation": 0.15,
        "semantic": 0.40,
    }

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    # Media ponderada real: 0.15*75 + 0.40*69 = 38.85 -> redondea a 39,
    # por debajo del umbral amarillo (40) por poco -- exactamente el caso
    # real que se coló en verde.
    assert out.score == 40
    assert out.semaforo == Semaforo.AMARILLO


def test_low_score_self_reported_uncertainty_does_not_floor_a_clean_diff():
    """Segundo bug real encontrado regenerando el informe de validación,
    esta vez introducido por el propio arreglo anterior (caso
    `benign_refactor`, un renombrado cosmético sin riesgo real que empezó a
    salir en amarillo). `threat_nature` es un campo que el LLM rellena
    libremente en su propia salida estructurada -- no es exclusivo de
    `_apply_unverified_content_floor`. El modelo puede devolver
    `threat_nature="incertidumbre"` con un `risk_score` bajísimo solo por
    prudencia genérica ("no puedo estar 100% seguro de que este renombrado
    no rompa algún contrato externo"), sin que exista contenido truncado sin
    verificar de por medio. El suelo NO debe activarse aquí -- el propio
    risk_score bajo de la capa (5) ya refleja que el modelo no le da
    importancia real; forzar amarillo de todas formas convertiría cualquier
    incertidumbre trivial autoreportada en una falsa alarma."""
    results = {
        "static": _result("static", 0),
        "dependencies": _result("dependencies", 0),
        "vulnerabilities": _result("vulnerabilities", 0),
        "reputation": _result("reputation", 0),
        "semantic": LayerResult(
            layer_name="semantic",
            risk_score=5,
            justification="Renombrado puramente cosmético, sin riesgo real.",
            threat_nature=ThreatNature.UNCERTAIN,
            confidence=Confidence.ALTA,
        ),
    }
    weights = {
        "static": 0.25,
        "dependencies": 0.10,
        "vulnerabilities": 0.10,
        "reputation": 0.15,
        "semantic": 0.40,
    }

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 2  # 0.40 * 5, sin suelo aplicado
    assert out.semaforo == Semaforo.VERDE


def test_uncertain_semantic_threat_nature_does_not_lower_an_already_higher_score():
    results = {
        "reputation": _result("reputation", 0),
        "semantic": LayerResult(
            layer_name="semantic",
            risk_score=85,
            justification="Riesgo ya alto por otro motivo, además incertidumbre real.",
            threat_nature=ThreatNature.UNCERTAIN,
            confidence=Confidence.MEDIA,
        ),
    }
    weights = {"reputation": 0.5, "semantic": 0.5}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 42  # media ponderada real, no se pisa con el suelo de 40
    assert out.semaforo == Semaforo.AMARILLO


def test_uncertain_semantic_threat_nature_ignored_when_semantic_is_skipped():
    """Si la capa semántica se omitió (presupuesto agotado, fallo del LLM),
    su `threat_nature` por defecto es None/UNCERTAIN según el modelo, pero
    `skipped=True` -- no debe activar el suelo, sería tratar "no se ejecutó"
    igual que "se ejecutó y no pudo verificar", que no es lo mismo."""
    results = {
        "reputation": _result("reputation", 0),
        "semantic": LayerResult(
            layer_name="semantic",
            risk_score=0,
            justification="",
            skipped=True,
            skip_reason="Presupuesto de tokens agotado",
        ),
    }
    weights = {"reputation": 1.0, "semantic": 0.0}

    out = aggregate(results, weights, diff=None, pr_id="1", repo="org/repo")

    assert out.score == 0
    assert out.semaforo == Semaforo.VERDE
