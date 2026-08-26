"""Tests unitarios para el mapa de conocimiento de un repo
(watchgate/core/repo_graph.py) -- filtrado de ficheros, extracción de
símbolos/imports y grafo de referencias sobre contenido REAL (no diffs).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from watchgate.core.repo_graph import (
    build_repo_import_graph,
    extract_symbols_and_imports,
    index_repo_files,
    select_files_to_index,
    should_index_file,
)


def test_should_index_file_excludes_vendored_dirs():
    assert should_index_file("node_modules/lodash/index.js", 100) is False
    assert should_index_file("vendor/lib/x.go", 100) is False
    assert should_index_file("src/app.py", 100) is True


def test_should_index_file_excludes_binaries_by_suffix():
    assert should_index_file("assets/logo.png", 100) is False
    assert should_index_file("dist/bundle.min.js", 100) is False
    assert should_index_file("README.md", 100) is True


def test_should_index_file_excludes_oversized_files():
    assert should_index_file("data/huge.py", 300_000) is False


def test_select_files_to_index_prioritizes_source_over_docs_and_caps_total():
    paths = [("README.md", 10), ("src/app.py", 10), ("docs/guide.md", 10)]
    selected = select_files_to_index(paths)
    assert selected[0] == "src/app.py"
    assert set(selected) == {"README.md", "src/app.py", "docs/guide.md"}


def test_extract_symbols_and_imports_python_file():
    content = "import os\nfrom sys import argv\n\ndef handler():\n    pass\n"
    symbols, imports = extract_symbols_and_imports(content, "src/handler.py")
    assert any("def handler" in s for s in symbols)
    assert "os" in imports


def test_extract_symbols_and_imports_unrecognized_language_returns_empty():
    symbols, imports = extract_symbols_and_imports("binary garbage", "data.bin")
    assert symbols == []
    assert imports == []


def test_build_repo_import_graph_links_files_by_stem_match():
    files = {
        "app/main.py": ("import app.utils\n", "python"),
        "app/utils.py": ("def helper():\n    pass\n", "python"),
        "app/unrelated.py": ("x = 1\n", "python"),
    }
    graph = build_repo_import_graph(files)
    assert "app/utils.py" in graph["app/main.py"]
    assert "app/main.py" in graph["app/utils.py"]
    assert "app/unrelated.py" not in graph["app/main.py"]


class _FakeLLMClient:
    def summarize_file(self, file_path, content, symbols):
        from watchgate.core.layers._semantic.client import FileSummary

        return FileSummary(category="util", summary=f"Resumen de {file_path}")

    def synthesize_text(self, system_prompt, user_prompt):
        return "## Arquitectura\nRepo de prueba."


@pytest.fixture
def _real_db(tmp_path, monkeypatch):
    """`index_repo_files` usa `get_session()` real (no inyectable) -- se
    apunta a una sqlite temporal para el test, mismo patrón que otros
    tests de este proyecto que ejercitan código con `get_session()` fijo."""
    from watchgate.db.connection import SQLModel, build_engine
    from watchgate.db.repository import create_organization

    db_file = tmp_path / "test_repo_graph.db"
    engine = build_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(engine)

    import watchgate.core.repo_graph as rg
    import watchgate.db.connection as db_connection

    monkeypatch.setattr(db_connection, "default_engine", engine)
    monkeypatch.setattr(rg, "get_session", db_connection.get_session)

    from sqlmodel import Session
    from watchgate.db.models import MonitoredRepo

    with Session(engine) as session:
        org = create_organization(session, name="Test Org", org_id="test-org-graph")
        session.add(
            MonitoredRepo(
                id="repo-graph-test",
                org_id=org.id,
                repo_path="test/repo-graph",
                monitor_type="audited",
            )
        )
        session.commit()

    return engine


def test_index_repo_files_end_to_end_with_fake_llm_and_chroma(_real_db, tmp_path):
    """Reproduce en miniatura la prueba manual real hecha en vivo contra
    Flask -- aquí con un LLM falso y Chroma en un directorio temporal, para
    que corra rápido y sin red."""
    from sqlmodel import Session, select

    from watchgate.db.models import RepoArchitectureSummary, RepoGraphNode

    files = {
        "api/handler.py": "import os\n\ndef handle_request():\n    pass\n",
        "utils/helpers.py": "def helper():\n    pass\n",
        "README.md": "# Test repo\n",
    }

    with (
        patch("watchgate.core.repo_graph.build_llm_client", return_value=_FakeLLMClient()),
        patch("watchgate.core.repo_graph.DEFAULT_INDEX_PATH", str(tmp_path / "chroma")),
    ):
        index_repo_files("repo-graph-test", "test/repo-graph", files)

    with Session(_real_db) as session:
        summary = session.exec(
            select(RepoArchitectureSummary).where(
                RepoArchitectureSummary.monitored_repo_id == "repo-graph-test"
            )
        ).first()
        assert summary is not None
        assert summary.status == "ready"
        assert summary.node_count == 3
        assert "Arquitectura" in summary.overview

        nodes = session.exec(
            select(RepoGraphNode).where(RepoGraphNode.monitored_repo_id == "repo-graph-test")
        ).all()
        assert {n.file_path for n in nodes} == set(files)
