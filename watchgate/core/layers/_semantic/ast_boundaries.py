"""Fronteras de función/clase e imports vía AST, para trocear/agrupar
ficheros grandes en la capa semántica sin perder cohesión de código (ver
`chunking.py`, que es el único consumidor real de este módulo).

Dos usos:
- `top_level_ranges`: rangos de línea (1-indexados, inclusive) de las
  definiciones de nivel superior (función/clase) de un fichero -- para no
  partir una construcción por la mitad al trocear un fichero demasiado
  grande para un único chunk.
- `import_specifiers`: strings de import/require tal cual aparecen en el
  código -- para detectar qué ficheros del mismo diff se referencian entre
  sí, sin resolución real de módulos (heurística: `chunking.py` compara
  esto contra las rutas de los ficheros del propio PR).

Tres niveles de fallback, de más a menos preciso -- NUNCA se propaga un
fallo hacia quien llama, en el peor caso se devuelve vacío:

1. Python: `ast` de la stdlib (memory-safe de verdad -- en el peor caso
   lanza `SyntaxError`, nunca puede tumbar el proceso).
2. Resto de lenguajes: `tree-sitter` vía `tree_sitter_language_pack`, pero
   ejecutado en un SUBPROCESO aislado con timeout (`_run_treesitter_
   isolated`), nunca en el proceso principal. Hallazgo real, reproducido:
   tree-sitter puede crashear con un SIGSEGV nativo (no una excepción
   Python capturable) al parsear JS deliberadamente ofuscado de un paquete
   malicioso real (tests/cases/malreal_npm_malicious_intent_nit-
   quotation-service-core-lib_34) -- dado que esta herramienta analiza
   código potencialmente malicioso A PROPÓSITO, un `try/except` alrededor
   de la llamada no basta: solo el aislamiento en proceso hace que un
   crash nativo se quede contenido, sin tumbar el análisis completo.
3. Si tree-sitter no está instalado, no soporta el lenguaje, crashea o se
   cuelga: heurística sin ninguna librería de parseo (`_heuristic_*`) --
   balance de '{'/'}' para lenguajes de llaves, indentación para el resto.
   Sigue siendo una división "lógica" real (nunca corta a mitad de una
   función), solo que más tosca que un AST de verdad (puede confundirse
   con llaves dentro de un string/comentario mal detectado, en el peor
   caso corta un poco antes/después de donde debería -- nunca revienta).

Si ni siquiera la heurística encuentra nada (fichero sin estructura
reconocible), listas/sets vacíos: `chunking.py` cae entonces a trocear por
líneas con solape, el último nivel de todos.
"""

from __future__ import annotations

import ast
import concurrent.futures
import logging
import multiprocessing
import re
from concurrent.futures.process import BrokenProcessPool
from typing import Any

logger = logging.getLogger("watchgate.semantic.ast_boundaries")

try:
    from tree_sitter_language_pack import get_parser

    _TREE_SITTER_AVAILABLE = True
except ImportError:  # pragma: no cover - depende del extra "analysis"
    _TREE_SITTER_AVAILABLE = False

# `spawn`, no `fork`: un `fork()` duplicaría el estado de memoria del
# proceso padre tal cual (incluido cualquier estado ya corrupto que no
# haya crasheado todavía); `spawn` arranca un intérprete Python limpio de
# verdad en el subproceso, sin heredar nada del padre -- aislamiento real,
# no solo nominal.
_mp_context = multiprocessing.get_context("spawn")
_SUBPROCESS_TIMEOUT_SECONDS = 10.0

# Nuestro nombre de lenguaje (`diffparser._infer_language`) -> nombre que
# espera `tree_sitter_language_pack.get_parser()`. Solo se listan lenguajes
# con nociones reales de "función"/"import"; formatos de datos/marcado
# (yaml/json/toml/markdown) se dejan fuera a propósito, no es un olvido.
_LANGUAGE_TO_TREE_SITTER: dict[str, str] = {
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "ruby": "ruby",
    "c": "c",
    "cpp": "cpp",
    "shell": "bash",
}

# Lenguajes cuya heurística de fallback (sin parser) es balance de llaves
# -- todos los de `_LANGUAGE_TO_TREE_SITTER` menos ruby, que delimita
# bloques con `end`, no con '{'/'}' (sin heurística sin-parser razonable
# para ruby por ahora; si tree-sitter falla ahí, cae directo al solape por
# líneas de `chunking.py`, el último nivel).
_BRACE_LANGUAGES = frozenset(
    {"javascript", "typescript", "go", "rust", "java", "c", "cpp", "shell"}
)

# Tipos de nodo que cuentan como "definición de nivel superior" por
# lenguaje -- la unidad mínima que no se debe partir por la mitad.
_BOUNDARY_NODE_TYPES: dict[str, frozenset[str]] = {
    "javascript": frozenset(
        {"function_declaration", "class_declaration", "lexical_declaration", "method_definition"}
    ),
    "typescript": frozenset(
        {
            "function_declaration",
            "class_declaration",
            "lexical_declaration",
            "method_definition",
            "interface_declaration",
        }
    ),
    "go": frozenset({"function_declaration", "method_declaration", "type_declaration"}),
    "rust": frozenset({"function_item", "impl_item", "struct_item", "enum_item", "trait_item"}),
    "java": frozenset({"class_declaration", "interface_declaration", "method_declaration"}),
    "ruby": frozenset({"method", "class", "module"}),
    "c": frozenset({"function_definition", "struct_specifier"}),
    "cpp": frozenset({"function_definition", "class_specifier", "struct_specifier"}),
    "shell": frozenset({"function_definition"}),
}

# Tipos de nodo de import/require/include por lenguaje -- de ahí se extrae
# el primer string literal descendiente como especificador de módulo/ruta.
_IMPORT_NODE_TYPES: dict[str, frozenset[str]] = {
    "javascript": frozenset({"import_statement", "call_expression"}),
    "typescript": frozenset({"import_statement", "call_expression"}),
    "go": frozenset({"import_spec"}),
    "rust": frozenset({"use_declaration"}),
    "java": frozenset({"import_declaration"}),
    "ruby": frozenset({"call"}),  # require/require_relative son "call" en el AST de ruby
    "c": frozenset({"preproc_include"}),
    "cpp": frozenset({"preproc_include"}),
}


# --- Nivel 1: Python vía `ast` (stdlib, memory-safe) -----------------------


def _python_top_level_ranges(source: str) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    ranges = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            end = getattr(node, "end_lineno", None) or node.lineno
            ranges.append((node.lineno, end))
    return ranges


def _python_import_specifiers(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    specs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            specs.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            specs.add(node.module)
    return specs


# --- Nivel 2: tree-sitter, aislado en subproceso ---------------------------


def _get_ts_parser(language: str) -> Any | None:
    """Solo se llama ya dentro del subproceso aislado (`_treesitter_
    worker`) -- nunca en el proceso principal."""
    ts_name = _LANGUAGE_TO_TREE_SITTER.get(language)
    if ts_name is None:
        return None
    try:
        # `get_parser` tipa su argumento como Literal[...] (los ~150 nombres
        # de grammar que empaqueta tree-sitter-language-pack); ts_name viene
        # de `_LANGUAGE_TO_TREE_SITTER`, un dict fijo de nuestros propios
        # nombres -> un subconjunto válido de ese Literal, pero mypy no
        # puede verificar eso a través de un `dict.get()` dinámico.
        return get_parser(ts_name)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - grammar no empaquetada en esta instalación, etc.
        logger.debug("Sin parser tree-sitter para %r", language, exc_info=True)
        return None


def _treesitter_top_level_ranges(source: str, language: str) -> list[tuple[int, int]]:
    parser = _get_ts_parser(language)
    if parser is None:
        return []
    boundary_types = _BOUNDARY_NODE_TYPES.get(language, frozenset())
    tree = parser.parse(source.encode("utf-8", errors="replace"))
    return [
        (node.start_point.row + 1, node.end_point.row + 1)
        for node in tree.root_node.children
        if node.type in boundary_types
    ]


def _string_literal_text(node: Any) -> str | None:
    text = node.text.decode("utf-8", errors="replace")
    return text.strip("'\"`") or None


def _first_string_descendant(node: Any) -> str | None:
    if (
        node.type == "string"
        or node.type == "string_literal"
        or node.type == "interpreted_string_literal"
    ):
        return _string_literal_text(node)
    for child in node.children:
        found = _first_string_descendant(child)
        if found is not None:
            return found
    return None


def _treesitter_import_specifiers(source: str, language: str) -> set[str]:
    parser = _get_ts_parser(language)
    if parser is None:
        return set()
    import_types = _IMPORT_NODE_TYPES.get(language, frozenset())
    if not import_types:
        return set()
    tree = parser.parse(source.encode("utf-8", errors="replace"))

    specs: set[str] = set()

    def visit(node: Any) -> None:
        is_require_call = node.type == "call_expression" and (
            (callee := node.child_by_field_name("function")) is not None
            and callee.text.decode("utf-8", errors="replace") == "require"
        )
        if node.type in import_types and (node.type != "call_expression" or is_require_call):
            spec = _first_string_descendant(node)
            if spec:
                specs.add(spec)
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return specs


def _treesitter_worker(source: str, language: str, mode: str) -> list[Any]:
    """Punto de entrada del subproceso aislado (`_mp_context`, `spawn`) --
    aquí es donde tree-sitter puede crashear de verdad; si lo hace, solo
    muere ESTE subproceso (`_run_treesitter_isolated`, en el proceso
    padre, lo detecta como `BrokenProcessPool`), nunca el proceso
    principal que sigue analizando el resto del PR."""
    if mode == "ranges":
        return _treesitter_top_level_ranges(source, language)
    return list(_treesitter_import_specifiers(source, language))


def _run_treesitter_isolated(source: str, language: str, mode: str) -> list[Any] | None:
    """`None` si tree-sitter no está disponible, no soporta `language`,
    crashea, o se cuelga -- en cualquiera de esos casos quien llama debe
    caer al fallback heurístico (`_heuristic_top_level_ranges`/
    `_heuristic_import_specifiers`), nunca propagar el fallo."""
    if not _TREE_SITTER_AVAILABLE or language not in _LANGUAGE_TO_TREE_SITTER:
        return None
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=1, mp_context=_mp_context) as pool:
            future = pool.submit(_treesitter_worker, source, language, mode)
            return future.result(timeout=_SUBPROCESS_TIMEOUT_SECONDS)
    except BrokenProcessPool:
        # Caso real reproducido: tree-sitter crashea (SIGSEGV) parseando JS
        # deliberadamente ofuscado de un paquete malicioso auténtico. El
        # subproceso muere, el pool lo detecta y lanza esto -- se captura
        # aquí, nunca sube más allá.
        logger.warning(
            "tree-sitter crasheó en subproceso aislado analizando %r -- cae a heurística", language
        )
        return None
    except concurrent.futures.TimeoutError:
        logger.warning(
            "tree-sitter excedió %.0fs en subproceso aislado analizando %r",
            _SUBPROCESS_TIMEOUT_SECONDS,
            language,
        )
        return None
    except Exception:  # noqa: BLE001 - cualquier otro fallo del propio mecanismo de aislamiento
        logger.debug("fallo inesperado ejecutando tree-sitter aislado", exc_info=True)
        return None


# --- Nivel 3: heurística sin parser (balance de llaves / indentación) ------


# Balance de '{'/'}' carácter a carácter, ignorando strings ('...'/"..."/
# `...`, con escapes) y comentarios ('//' de línea, '/* */' de bloque,
# persistente entre líneas) de forma best-effort -- no es un lexer real
# del lenguaje (puede confundirse con una plantilla de string anidada
# compleja en JS, p. ej.), pero para el propósito de "no cortar a mitad de
# una función" basta: en el peor caso el corte cae un poco antes/después
# de donde un parser real lo pondría, nunca revienta ni deja de avanzar.
def _heuristic_top_level_ranges(source: str) -> list[tuple[int, int]]:
    # Tope real de líneas: si `source` termina en '\n', el bucle de abajo
    # cuenta esa línea final vacía como una línea más (`line_no` sube en
    # cada '\n' visto, incluido el último) -- sin este tope, el rango de
    # cola quedaría con un `end` apuntando a una línea que `splitlines()`
    # ni siquiera considera que existe (bug real, reproducido).
    total_lines = len(source.splitlines())
    depth = 0
    line_no = 1
    start_line = 1
    ranges: list[tuple[int, int]] = []
    in_string: str | None = None
    in_block_comment = False
    saw_content = False
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch == "\n":
            line_no += 1
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and i + 1 < n and source[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            saw_content = True
            i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            j = source.find("\n", i)
            i = n if j == -1 else j
            continue
        if ch == "{":
            depth += 1
            saw_content = True
        elif ch == "}":
            depth -= 1
            saw_content = True
            if depth <= 0 and saw_content:
                ranges.append((start_line, line_no))
                start_line = line_no + 1
                depth = max(depth, 0)
                saw_content = False
        elif not ch.isspace():
            saw_content = True
        i += 1
    if start_line <= total_lines:
        ranges.append((start_line, min(line_no, total_lines)))
    return ranges


_CLOSING_ONLY_LINE = frozenset({"end", "}", ")", "]", "end;", "end.", "end,"})


def _indentation_top_level_ranges(source: str) -> list[tuple[int, int]]:
    """Fallback sin parser para lenguajes que delimitan bloques por
    indentación en vez de llaves (p. ej. Python con un fragmento que no
    parsea de verdad -- `_python_top_level_ranges` ya devolvió [] --, o
    Ruby, que usa `end` en vez de '{'/'}'). Una línea que SOLO cierra el
    bloque anterior (`end`, `}`...) a columna 0 no cuenta como el inicio
    de uno nuevo -- sin este caso especial, cada `end` de Ruby a nivel
    superior partiría el fichero en un rango de una sola línea."""
    lines = source.splitlines()
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped not in _CLOSING_ONLY_LINE:
            if start is not None:
                ranges.append((start, i - 1))
            start = i
    if start is not None:
        ranges.append((start, len(lines)))
    return ranges


_IMPORT_REGEX_PATTERNS: tuple[re.Pattern[str], ...] = (
    # import ... from "x" / import "x" / require("x") / require "x"
    re.compile(r"""(?:from|require)\s*\(?\s*['"]([^'"]+)['"]"""),
    re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.MULTILINE),
)


def _heuristic_import_specifiers(source: str) -> set[str]:
    """Regex sobre el texto crudo, sin ningún parser -- cubre las formas
    más comunes de import/require en los lenguajes de `_LANGUAGE_TO_TREE_
    SITTER` (import ... from "x", require("x")). Puramente textual, no
    puede fallar más que devolver menos aristas de las que un AST real
    encontraría -- `chunking.py` ya trata cualquier import no detectado
    como "sin relación conocida", nunca como un error."""
    specs: set[str] = set()
    for pattern in _IMPORT_REGEX_PATTERNS:
        specs.update(pattern.findall(source))
    return specs


# --- API pública -------------------------------------------------------


def top_level_ranges(source: str, language: str | None) -> list[tuple[int, int]]:
    """Rangos de línea (1-indexados, inclusive) de las definiciones de nivel
    superior de `source`, con el fallback de tres niveles documentado en el
    docstring del módulo. Lista vacía si `language` es `None` o si ningún
    nivel encontró nada -- quien llama (`chunking.py`) debe caer entonces
    al trocear por líneas con solape, el último nivel de todos."""
    if language == "python":
        ranges = _python_top_level_ranges(source)
        return ranges if ranges else _indentation_top_level_ranges(source)
    if language is None:
        return []
    isolated = _run_treesitter_isolated(source, language, mode="ranges")
    if isolated is not None:
        return isolated
    if language in _BRACE_LANGUAGES:
        return _heuristic_top_level_ranges(source)
    if language == "ruby":
        return _indentation_top_level_ranges(source)
    return []


def import_specifiers(source: str, language: str | None) -> set[str]:
    """Strings de import/require/include tal cual aparecen en `source`, sin
    resolver a rutas reales. Mismo fallback de tres niveles que
    `top_level_ranges`."""
    if language == "python":
        return _python_import_specifiers(source)
    if language is None:
        return set()
    isolated = _run_treesitter_isolated(source, language, mode="imports")
    if isolated is not None:
        return set(isolated)
    return _heuristic_import_specifiers(source)
