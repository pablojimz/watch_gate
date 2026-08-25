"""Empaquetado de un diff demasiado grande para una única llamada al LLM en
varios "chunks" que sí caben, preservando cohesión de código.

Estrategia (de más a menos preferida -- `SemanticLayer.analyze` solo entra
aquí cuando el diff completo NO cabe en `max_diff_tokens`; si cabe, sigue
con la única llamada de siempre, este módulo no se usa):

1. Cada FICHERO se manda entero en algún chunk -- a diferencia del truncado
   heurístico de `prompting.py::build_user_prompt` (que puede dejar un
   fichero entero sin mostrar, solo con `UNVERIFIED_CONTENT_MARKER`), aquí
   ningún fichero pierde contenido salvo que se agote `_MAX_CHUNKS`.
2. Los ficheros se agrupan en chunks hasta llenar `max_diff_tokens`,
   prefiriendo agrupar ficheros que se referencian entre sí
   (`build_reference_graph`, vía imports/require detectados con AST en
   `ast_boundaries.py`) -- así el riesgo transversal (función cambiada en A
   + su único caller en B, ambos en el mismo PR) es visible dentro de UN
   chunk, sin depender solo de la síntesis final para detectarlo.
3. Si un ÚNICO fichero ya supera `max_diff_tokens` él solo (raro: fichero
   generado, bundle minificado...), se trocea ese fichero en fragmentos que
   respetan fronteras de función/clase (AST) para no partir una
   construcción por la mitad; si el lenguaje no tiene soporte AST o el
   fichero no parsea, cae a trocear por líneas con solape (misma
   herramienta que ya usa `core/rag/indexer.py` para el corpus:
   `RecursiveCharacterTextSplitter`).
4. Si el número de chunks resultante supera `_MAX_CHUNKS` (PR patológico,
   miles de ficheros), el resto queda fuera del análisis LLM y se reporta
   como contenido no verificado a la llamada de síntesis final -- mismo
   criterio honesto que ya usa `build_user_prompt` cuando se agota el
   presupuesto (nunca una falsa garantía de limpieza).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from watchgate.core.layers._semantic import ast_boundaries, prompting
from watchgate.core.models import FileChange

# Tope duro de chunks: un PR que tocara miles de ficheros no debe traducirse
# en miles de llamadas al LLM (coste/latencia sin control). Por encima de
# este número, el resto de ficheros se reporta como no verificado en vez de
# analizarse -- degradación explícita, no un error.
MAX_CHUNKS = 20

# Igual que `_DummyCostController.estimate_tokens`/`indexer.py`: ~4
# caracteres por token de media en inglés/español/código, sin tokenizer real
# a mano en este módulo (el tokenizer real vive en `CostController`, mide
# tokens del PROMPT completo, no de un fragmento de texto suelto en
# aislamiento -- para trocear un fichero grande basta la aproximación).
_CHARS_PER_TOKEN = 4
_OVERLAP_CHARS = 200


@dataclass
class Piece:
    """Unidad empaquetable: un fichero entero, o un fragmento de un fichero
    demasiado grande para caber él solo en un chunk."""

    source_path: str  # ruta real del fichero -- para el grafo de referencias
    content: str  # texto ya renderizado (delimitadores incluidos), listo para el prompt
    token_cost: int
    part_label: str | None = None  # "parte 2/4" si es un fragmento, None si es el fichero entero


@dataclass
class Chunk:
    pieces: list[Piece] = field(default_factory=list)
    token_total: int = 0

    @property
    def source_paths(self) -> set[str]:
        return {p.source_path for p in self.pieces}

    def render(self) -> str:
        return "\n".join(p.content for p in self.pieces)


def _reconstruct_new_content(diff_hunk: str) -> str:
    """Aproxima el contenido del fichero en la versión NUEVA a partir del
    hunk unificado: conserva líneas de contexto (' ') y añadidas ('+'),
    descarta las eliminadas ('-') y las cabeceras ('@@'/'---'/'+++'). Para
    un fichero AÑADIDO esto reconstruye el fichero completo tal cual (todo
    el hunk es '+'); para uno MODIFICADO es una aproximación limitada a lo
    que el hunk incluye. Suficiente para detectar fronteras de
    función/imports en la parte presente -- no hace falta el fichero exacto
    para eso, y este caso (fichero demasiado grande él solo) es, en la
    práctica, casi siempre un fichero AÑADIDO (ver razonamiento en
    `prompting.py::_STATUS_PRIORITY`)."""
    lines = []
    for raw_line in diff_hunk.splitlines():
        if raw_line.startswith(("@@", "--- ", "+++ ")):
            continue
        if raw_line.startswith(("+", " ")):
            lines.append(raw_line[1:])
        # líneas '-' se descartan: no existen en la versión nueva
    return "\n".join(lines)


def build_reference_graph(files: list[FileChange]) -> dict[str, set[str]]:
    """Grafo no dirigido best-effort `path -> {otros paths del mismo diff
    que referencia}`, a partir de imports/require detectados en el
    contenido reconstruido de cada fichero. Puramente heurístico: un import
    no detectado (lenguaje sin soporte AST, import fuera del hunk de un
    fichero modificado...) simplemente no añade una arista, nunca es un
    error -- `pack_pieces` cae a empaquetado por tamaño para esos ficheros."""
    graph: dict[str, set[str]] = {fc.path: set() for fc in files}
    for fc in files:
        content = _reconstruct_new_content(fc.diff_hunk)
        raw_refs = ast_boundaries.import_specifiers(content, fc.language)
        if not raw_refs:
            continue
        for other in files:
            if other.path == fc.path:
                continue
            other_stem = other.path.rsplit("/", 1)[-1].split(".")[0]
            if other_stem and any(other_stem in ref for ref in raw_refs):
                graph[fc.path].add(other.path)
                graph[other.path].add(fc.path)
    return graph


# Literales notables para correlacionar ficheros por símbolo compartido en
# vez de por import -- deliberadamente NO son los mismos patrones que
# `_SUSPICIOUS_PATTERNS` de `_shared.py` (esos buscan SINTAXIS peligrosa:
# "eval(", "curl | sh"; ver el `find_suspicious_lines` que ya usa
# `prompting.py` para anclar extractos). Reutilizar esos aquí generaría
# ruido: que dos ficheros contengan "eval(" cada uno no implica ninguna
# relación ENTRE ellos, es un patrón demasiado común. Aquí se busca lo
# contrario: un VALOR concreto (una URL, una IP, un blob largo) que, si
# aparece IDÉNTICO en dos ficheros distintos, difícilmente es casualidad --
# es la misma lógica que un analista de seguridad usa para correlacionar
# IOCs (indicadores de compromiso) entre ficheros de un mismo ataque.
#
# Se descartó deliberadamente usar similitud de embeddings (estilo RAG)
# para esto: la similitud de texto mide "de qué habla esto" (vocabulario),
# no "hay una relación de flujo de datos maliciosa real" -- "leer un
# fichero" y "escribir un fichero" saldrían parecidos por vocabulario sin
# relación real (falso positivo), y el patrón clásico de exfiltración
# ("lee un secreto aquí" + "mándalo allá por HTTP") es LÉXICAMENTE distinto
# entre sus dos mitades, así que embeddings fallaría en conectar justo el
# caso que importa (falso negativo, el peor de los dos para una
# herramienta de seguridad). Coincidencia EXACTA de un literal concreto no
# tiene ninguno de los dos problemas.
_NOTABLE_LITERAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"https?://[^\s'\"<>]{6,}"),  # URLs
    re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),  # IPs
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),  # blobs base64 largos
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),  # blobs hex largos
]


def _extract_notable_literals(text: str) -> set[str]:
    """Strings literales inusuales (URLs/IPs/blobs largos) para correlacionar
    ficheros por símbolo compartido. Deliberadamente NO incluye nombres de
    variable/identificadores genéricos -- demasiado comunes, generarían
    falsos positivos ("utils", "config"...); solo valores lo bastante
    específicos como para que compartirlos entre dos ficheros sea señal
    real, no coincidencia."""
    literals: set[str] = set()
    for pattern in _NOTABLE_LITERAL_PATTERNS:
        literals.update(pattern.findall(text))
    return literals


def build_symbol_reference_graph(files: list[FileChange]) -> dict[str, set[str]]:
    """Mismo contrato que `build_reference_graph` (grafo no dirigido
    `path -> {paths relacionados}`), pero la arista viene de compartir al
    menos un literal notable EXACTO (`_extract_notable_literals`) entre dos
    ficheros, no de un import -- complementario, no sustituto: captura
    relaciones reales (p. ej. una URL de exfiltración referenciada en dos
    sitios) que no pasan por ningún import explícito."""
    graph: dict[str, set[str]] = {fc.path: set() for fc in files}
    literals_by_path = {
        fc.path: _extract_notable_literals(_reconstruct_new_content(fc.diff_hunk)) for fc in files
    }
    for i, fc in enumerate(files):
        if not literals_by_path[fc.path]:
            continue
        for other in files[i + 1 :]:
            if literals_by_path[fc.path] & literals_by_path[other.path]:
                graph[fc.path].add(other.path)
                graph[other.path].add(fc.path)
    return graph


def merge_reference_graphs(*graphs: dict[str, set[str]]) -> dict[str, set[str]]:
    """Unión de aristas de varios grafos no dirigidos sobre las mismas
    claves (paths) -- p. ej. imports + símbolos compartidos, sin perder
    ninguna señal de ninguno de los dos."""
    merged: dict[str, set[str]] = {}
    for graph in graphs:
        for path, neighbors in graph.items():
            merged.setdefault(path, set()).update(neighbors)
    return merged


def _overlap_split(text: str, max_diff_tokens: int) -> list[str]:
    """Fallback sin AST: trocea `text` por caracteres con solape, misma
    herramienta que `core/rag/indexer.py` usa para el corpus (`langchain-
    text-splitters`, ya dependencia del extra "analysis")."""
    chunk_size_chars = max(500, max_diff_tokens * _CHARS_PER_TOKEN - _OVERLAP_CHARS)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size_chars, chunk_overlap=_OVERLAP_CHARS
    )
    return splitter.split_text(text)


def _group_ranges_into_fragments(
    lines: list[str],
    ranges: list[tuple[int, int]],
    count_tokens: Callable[[str], int],
    max_diff_tokens: int,
) -> list[str]:
    """Agrupa definiciones de nivel superior consecutivas en fragmentos que
    caben en `max_diff_tokens`, cortando solo entre definiciones (nunca a
    mitad de una). El primer fragmento arranca en la línea 1 (para incluir
    imports/constantes de módulo antes de la primera definición); el último
    llega hasta el final del fichero (para incluir cualquier código tras la
    última definición)."""
    ranges = sorted(ranges)
    fragments: list[str] = []
    group_start_idx = 0  # índice 0-based de inicio del fragmento actual
    group_end_line = 0  # última línea (1-based) cubierta por el fragmento actual

    for start, end in ranges:
        candidate_text = "\n".join(lines[group_start_idx:end])
        if group_end_line and count_tokens(candidate_text) > max_diff_tokens:
            fragments.append("\n".join(lines[group_start_idx:group_end_line]))
            group_start_idx = start - 1
        group_end_line = end
    fragments.append("\n".join(lines[group_start_idx:]))

    # Una única definición ya puede superar el presupuesto ella sola (una
    # función enorme) -- ahí el fallback por solape se aplica sobre ESE
    # fragmento concreto, no sobre el fichero entero.
    result: list[str] = []
    for frag in fragments:
        if frag.strip() and count_tokens(frag) > max_diff_tokens:
            result.extend(_overlap_split(frag, max_diff_tokens))
        elif frag.strip():
            result.append(frag)
    return result


def _split_oversized_file(
    fc: FileChange, count_tokens: Callable[[str], int], max_diff_tokens: int
) -> list[Piece]:
    """Un único fichero cuyo diff, él solo, ya supera `max_diff_tokens`: se
    trocea en fragmentos que caben, preservando fronteras de función/clase
    cuando el lenguaje tiene soporte AST; si no, cae a trocear por líneas
    con solape."""
    content = _reconstruct_new_content(fc.diff_hunk)
    lines = content.splitlines()
    ranges = ast_boundaries.top_level_ranges(content, fc.language)

    fragments = (
        _group_ranges_into_fragments(lines, ranges, count_tokens, max_diff_tokens)
        if ranges
        else _overlap_split(content, max_diff_tokens)
    )
    if not fragments:
        fragments = [content]

    total = len(fragments)
    pieces = []
    for i, fragment_text in enumerate(fragments, start=1):
        label = f"parte {i}/{total}"
        rendered = (
            f"--- {fc.path} ({fc.status.value}, {label} -- fichero demasiado grande "
            "para un único análisis, este es solo un fragmento) ---\n"
            f"{prompting.wrap_untrusted_content(fragment_text)}"
        )
        pieces.append(
            Piece(
                source_path=fc.path,
                content=rendered,
                token_cost=count_tokens(rendered),
                part_label=label,
            )
        )
    return pieces


def build_pieces(
    files: list[FileChange], count_tokens: Callable[[str], int], max_diff_tokens: int
) -> list[Piece]:
    """Un `Piece` por fichero (el fichero entero), o varios si el fichero
    por sí solo ya supera `max_diff_tokens` (ver `_split_oversized_file`)."""
    pieces: list[Piece] = []
    for fc in files:
        rendered = prompting.render_file_change(fc)
        cost = count_tokens(rendered)
        if cost <= max_diff_tokens:
            pieces.append(Piece(source_path=fc.path, content=rendered, token_cost=cost))
        else:
            pieces.extend(_split_oversized_file(fc, count_tokens, max_diff_tokens))
    return pieces


def pack_pieces(
    pieces: list[Piece],
    reference_graph: dict[str, set[str]],
    max_diff_tokens: int,
    max_chunks: int | None = None,
) -> tuple[list[Chunk], list[Piece]]:
    """Empaqueta `pieces` en chunks que no superen `max_diff_tokens`,
    prefiriendo colocar juntas piezas cuyos ficheros de origen se
    referencian entre sí (`reference_graph`). Empaquetado *first-fit*
    determinista: se procesan las piezas con más conexiones primero (más
    probable que encajar temprano evite fragmentar un grupo relacionado
    entre varios chunks).

    Devuelve `(chunks, overflow)`: `overflow` son las piezas que no
    encontraron sitio tras alcanzar `max_chunks` -- quien llama debe
    reportarlas como no verificadas en la síntesis final, nunca callarlas."""
    # `max_chunks` se resuelve aquí dentro (no como default de parámetro) a
    # propósito: así los tests pueden monkeypatchear `chunking.MAX_CHUNKS`
    # y que surta efecto -- un default `= MAX_CHUNKS` en la firma capturaría
    # el valor de una vez al importar el módulo, antes de que el test
    # tuviera ocasión de cambiarlo.
    if max_chunks is None:
        max_chunks = MAX_CHUNKS
    degree = {path: len(neighbors) for path, neighbors in reference_graph.items()}
    ordered = sorted(pieces, key=lambda p: -degree.get(p.source_path, 0))

    chunks: list[Chunk] = []
    overflow: list[Piece] = []

    for piece in ordered:
        neighbors = reference_graph.get(piece.source_path, set())
        target: Chunk | None = None

        if neighbors:
            for chunk in chunks:
                if (
                    chunk.source_paths & neighbors
                    and chunk.token_total + piece.token_cost <= max_diff_tokens
                ):
                    target = chunk
                    break
        if target is None:
            for chunk in chunks:
                if chunk.token_total + piece.token_cost <= max_diff_tokens:
                    target = chunk
                    break
        if target is None:
            if len(chunks) >= max_chunks:
                overflow.append(piece)
                continue
            target = Chunk()
            chunks.append(target)

        target.pieces.append(piece)
        target.token_total += piece.token_cost

    return chunks, overflow
