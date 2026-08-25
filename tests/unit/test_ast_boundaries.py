"""Tests de watchgate/core/layers/_semantic/ast_boundaries.py."""

from __future__ import annotations

from pathlib import Path

from watchgate.core.layers._semantic import ast_boundaries

_PYTHON_SOURCE = """\
import os
from pathlib import Path


def foo():
    return 1


class Bar:
    def method(self):
        return 2
"""

_JS_SOURCE = """\
import { helper } from "./helper";
const other = require("./other");

function greet() {
  return 1;
}

class Widget {
  render() {}
}
"""


def test_python_top_level_ranges_covers_function_and_class():
    ranges = ast_boundaries.top_level_ranges(_PYTHON_SOURCE, "python")
    assert len(ranges) == 2
    (foo_start, foo_end), (bar_start, bar_end) = ranges
    assert _PYTHON_SOURCE.splitlines()[foo_start - 1].startswith("def foo")
    assert _PYTHON_SOURCE.splitlines()[bar_start - 1].startswith("class Bar")
    assert foo_end < bar_start


def test_python_top_level_ranges_falls_back_to_indentation_on_syntax_error():
    """Si `ast.parse` falla (fragmento de diff sintácticamente inválido),
    cae al fallback de indentación (nivel 3) en vez de devolver vacío --
    sigue siendo mejor que nada para no partir a mitad de un bloque."""
    ranges = ast_boundaries.top_level_ranges("def broken(:\n  pass", "python")
    assert ranges == [(1, 2)]


def test_python_top_level_ranges_empty_when_nothing_at_all_matches():
    assert ast_boundaries.top_level_ranges("", "python") == []


def test_python_import_specifiers_covers_import_and_from_import():
    specs = ast_boundaries.import_specifiers(_PYTHON_SOURCE, "python")
    assert specs == {"os", "pathlib"}


def test_unknown_language_returns_empty():
    assert ast_boundaries.top_level_ranges("whatever", "cobol") == []
    assert ast_boundaries.import_specifiers("whatever", "cobol") == set()


def test_none_language_returns_empty():
    assert ast_boundaries.top_level_ranges(_PYTHON_SOURCE, None) == []
    assert ast_boundaries.import_specifiers(_PYTHON_SOURCE, None) == set()


def test_javascript_top_level_ranges_covers_function_and_class():
    ranges = ast_boundaries.top_level_ranges(_JS_SOURCE, "javascript")
    types_found = len(ranges)
    # import_statement (lexical_declaration) + function_declaration + class_declaration
    assert types_found >= 2
    lines = _JS_SOURCE.splitlines()
    matched = [lines[start - 1] for start, _ in ranges]
    assert any("function greet" in line for line in matched)
    assert any("class Widget" in line for line in matched)


def test_javascript_import_specifiers_covers_import_and_require():
    specs = ast_boundaries.import_specifiers(_JS_SOURCE, "javascript")
    assert specs == {"./helper", "./other"}


# --- Nivel 3: heurística sin parser (balance de llaves / indentación) -----


def test_brace_heuristic_never_cuts_mid_function():
    """Solo con contar '{'/'}' (sin tree-sitter en absoluto), la frontera
    cae justo al cierre de cada función/clase de nivel superior."""
    ranges = ast_boundaries._heuristic_top_level_ranges(_JS_SOURCE)
    lines = _JS_SOURCE.splitlines()
    for start, end in ranges:
        # cada rango debe empezar y terminar en balance 0: la línea de cierre
        # de un rango que contiene una función siempre incluye su '}' final.
        assert start <= end
    # el rango que contiene "function greet" debe llegar hasta su '}' de cierre
    greet_range = next(
        r for r in ranges if any("function greet" in lines[i - 1] for i in range(r[0], r[1] + 1))
    )
    assert lines[greet_range[1] - 1].strip() == "}"


def test_brace_heuristic_ignores_braces_inside_strings_and_comments():
    """Las '{'/'}' de dentro del string y del comentario no cuentan --
    si contaran, el balance nunca volvería a 0 y no habría ningún rango.
    Como no hay ninguna llave REAL hasta la función, las líneas previas
    (sin punto de corte natural) se agrupan junto con ella en un único
    rango que sí termina limpiamente en el '}' de cierre de la función."""
    src = (
        'const s = "{ not a real brace }";\n'
        "// comment with { brace }\n"
        "function f() {\n"
        "  return 1;\n"
        "}\n"
    )
    ranges = ast_boundaries._heuristic_top_level_ranges(src)
    lines = src.splitlines()
    assert len(ranges) == 1
    assert lines[ranges[0][1] - 1].strip() == "}"


def test_heuristic_import_specifiers_matches_common_forms():
    src = 'import { x } from "./a";\nconst y = require("./b");\nimport "./c";\n'
    specs = ast_boundaries._heuristic_import_specifiers(src)
    assert specs == {"./a", "./b", "./c"}


def test_indentation_fallback_splits_on_top_level_lines():
    src = "class Foo\n  def bar\n    1\n  end\nend\n\nclass Baz\n  def qux\n  end\nend\n"
    ranges = ast_boundaries._indentation_top_level_ranges(src)
    lines = src.splitlines()
    assert lines[ranges[0][0] - 1].startswith("class Foo")
    assert lines[ranges[1][0] - 1].startswith("class Baz")


# --- Aislamiento del subproceso de tree-sitter -----------------------------


def test_treesitter_disabled_falls_back_to_brace_heuristic(monkeypatch):
    """Con tree-sitter "no disponible" (simula que no está instalado, o
    que el subproceso aislado no pudo ejecutarlo), sigue habiendo una
    división lógica real vía la heurística de llaves -- no un vacío."""
    monkeypatch.setattr(ast_boundaries, "_run_treesitter_isolated", lambda *a, **k: None)
    ranges = ast_boundaries.top_level_ranges(_JS_SOURCE, "javascript")
    assert ranges  # la heurística encontró algo, no cayó a vacío
    specs = ast_boundaries.import_specifiers(_JS_SOURCE, "javascript")
    assert specs == {"./helper", "./other"}  # el regex fallback también funciona


def test_treesitter_ruby_without_isolation_falls_back_to_indentation(monkeypatch):
    monkeypatch.setattr(ast_boundaries, "_run_treesitter_isolated", lambda *a, **k: None)
    src = "class Foo\n  def bar\n  end\nend\n"
    ranges = ast_boundaries.top_level_ranges(src, "ruby")
    assert ranges == [(1, 4)]


def test_isolated_subprocess_survives_a_real_native_crash():
    """Regresión del bug real encontrado: tree-sitter revienta (SIGSEGV)
    parseando el JS de un paquete malicioso auténtico de la suite
    (tests/cases/malreal_npm_malicious_intent_nit-quotation-service-core-
    lib_34/after/helpers.js). Este test llama al camino REAL (subproceso
    aislado de verdad, sin mockear nada) -- si el aislamiento no
    funcionara, este test tumbaría todo el proceso de pytest, no solo
    fallaría con un AssertionError."""
    case_file = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "cases"
        / "malreal_npm_malicious_intent_nit-quotation-service-core-lib_34"
        / "after"
        / "helpers.js"
    )
    if not case_file.is_file():
        import pytest

        pytest.skip("fixture del caso real no disponible en este checkout")
    source = case_file.read_text()
    # No debe lanzar, ni (sobre todo) tumbar el proceso -- si tree-sitter
    # crashea en el subproceso aislado, cae a la heurística de llaves y
    # devuelve algo (o como mucho vacío), nunca un crash del proceso padre.
    ranges = ast_boundaries.top_level_ranges(source, "javascript")
    assert isinstance(ranges, list)
