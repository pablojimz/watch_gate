"""Tests de aceptación de diffparser.py (spec §2).

Cada test construye un repo git real en un directorio temporal con
`git.Repo.init(...)` para no depender de fixtures externas ni de red.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import git
import pytest

from watchgate.core.diffparser import parse_diff
from watchgate.core.models import FileStatus


@pytest.fixture
def tmp_repo():
    tmp_dir = tempfile.mkdtemp()
    repo = git.Repo.init(tmp_dir)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test User")
        cw.set_value("user", "email", "test@example.com")
    yield tmp_dir, repo
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _write(repo_dir: str, relpath: str, content: str | bytes) -> None:
    path = Path(repo_dir) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


def test_two_commits_basic_diff(tmp_repo):
    repo_dir, repo = tmp_repo
    _write(repo_dir, "a.py", "print('hello')\n")
    repo.index.add(["a.py"])
    base = repo.index.commit("initial commit", author=git.Actor("Alice", "alice@example.com"))

    _write(repo_dir, "a.py", "print('hello')\nprint('world')\n")
    _write(repo_dir, "b.py", "x = 1\n")
    repo.index.add(["a.py", "b.py"])
    head = repo.index.commit("add line and new file", author=git.Actor("Bob", "bob@example.com"))

    result = parse_diff(repo_dir, base.hexsha, head.hexsha)

    assert result.base_sha == base.hexsha
    assert result.head_sha == head.hexsha
    paths = {f.path for f in result.files}
    assert paths == {"a.py", "b.py"}

    a_change = next(f for f in result.files if f.path == "a.py")
    assert a_change.status == FileStatus.MODIFIED
    assert a_change.additions == 1
    assert a_change.deletions == 0

    b_change = next(f for f in result.files if f.path == "b.py")
    assert b_change.status == FileStatus.ADDED

    assert result.commit_messages == ["add line and new file"]
    assert [a.email for a in result.authors] == ["bob@example.com"]


def test_empty_diff_when_base_equals_head_does_not_raise(tmp_repo):
    repo_dir, repo = tmp_repo
    _write(repo_dir, "a.py", "print('hello')\n")
    repo.index.add(["a.py"])
    commit = repo.index.commit("initial commit")

    result = parse_diff(repo_dir, commit.hexsha, commit.hexsha)

    assert result.files == []
    assert result.commit_messages == []
    assert result.authors == []


def test_renamed_file_without_content_change(tmp_repo):
    repo_dir, repo = tmp_repo
    _write(repo_dir, "old_name.py", "print('same content')\n")
    repo.index.add(["old_name.py"])
    base = repo.index.commit("add old_name.py")

    (Path(repo_dir) / "old_name.py").rename(Path(repo_dir) / "new_name.py")
    repo.index.remove(["old_name.py"])
    repo.index.add(["new_name.py"])
    head = repo.index.commit("rename file")

    result = parse_diff(repo_dir, base.hexsha, head.hexsha)

    assert len(result.files) == 1
    renamed = result.files[0]
    assert renamed.status == FileStatus.RENAMED
    assert renamed.path == "new_name.py"
    assert renamed.old_path == "old_name.py"
    assert renamed.additions == 0
    assert renamed.deletions == 0


def test_binary_file_marked_as_binary(tmp_repo):
    repo_dir, repo = tmp_repo
    _write(repo_dir, "readme.md", "hello\n")
    repo.index.add(["readme.md"])
    base = repo.index.commit("initial")

    # Contenido binario real (bytes nulos) — no decodifica como UTF-8.
    _write(repo_dir, "image.png", bytes([0x89, 0x50, 0x4E, 0x47, 0x00, 0x01, 0x02, 0xFF]))
    repo.index.add(["image.png"])
    head = repo.index.commit("add binary file")

    result = parse_diff(repo_dir, base.hexsha, head.hexsha)

    binary_change = next(f for f in result.files if f.path == "image.png")
    assert binary_change.is_binary is True
    assert binary_change.diff_hunk == ""


def test_deleted_file(tmp_repo):
    repo_dir, repo = tmp_repo
    _write(repo_dir, "gone.py", "x = 1\n")
    repo.index.add(["gone.py"])
    base = repo.index.commit("add gone.py")

    (Path(repo_dir) / "gone.py").unlink()
    repo.index.remove(["gone.py"])
    head = repo.index.commit("remove gone.py")

    result = parse_diff(repo_dir, base.hexsha, head.hexsha)

    deleted = next(f for f in result.files if f.path == "gone.py")
    assert deleted.status == FileStatus.DELETED


def test_merge_commit_uses_first_parent_only(tmp_repo):
    """Con un merge commit en medio, solo deben contarse los commits del
    primer padre (equivalente a `git log --first-parent`), sin arrastrar
    los commits de la rama ya fusionada previamente a `base_sha`."""
    repo_dir, repo = tmp_repo
    _write(repo_dir, "main.py", "v1\n")
    repo.index.add(["main.py"])
    base = repo.index.commit("initial", author=git.Actor("Alice", "alice@example.com"))

    # Rama feature con su propio commit.
    feature = repo.create_head("feature", base)
    repo.head.reference = feature
    repo.head.reset(index=True, working_tree=True)
    _write(repo_dir, "feature.py", "feature work\n")
    repo.index.add(["feature.py"])
    feature_commit = repo.index.commit(
        "work on feature", author=git.Actor("Carol", "carol@example.com")
    )

    # Volvemos a main y hacemos un commit propio + el merge.
    main = repo.heads.master if hasattr(repo.heads, "master") else repo.heads.main
    repo.head.reference = main
    repo.head.reset(index=True, working_tree=True)
    _write(repo_dir, "main.py", "v2\n")
    repo.index.add(["main.py"])
    repo.index.commit("main work", author=git.Actor("Bob", "bob@example.com"))

    repo.git.merge("feature", "--no-ff", "-m", "merge feature into main")
    head = repo.commit(main.commit.hexsha)

    result = parse_diff(repo_dir, base.hexsha, head.hexsha)

    # Con --first-parent, el commit "work on feature" (en la rama lateral)
    # no debe aparecer en commit_messages/authors.
    assert "work on feature" not in result.commit_messages
    assert "carol@example.com" not in [a.email for a in result.authors]
    assert "main work" in result.commit_messages


def test_language_inferred_from_extension(tmp_repo):
    repo_dir, repo = tmp_repo
    _write(repo_dir, "readme.md", "hello\n")
    repo.index.add(["readme.md"])
    base = repo.index.commit("initial")

    _write(repo_dir, "script.py", "print(1)\n")
    _write(repo_dir, "Dockerfile", "FROM python:3.11\n")
    _write(repo_dir, "data.unknownext", "???\n")
    repo.index.add(["script.py", "Dockerfile", "data.unknownext"])
    head = repo.index.commit("add files of various types")

    result = parse_diff(repo_dir, base.hexsha, head.hexsha)
    by_path = {f.path: f for f in result.files}

    assert by_path["script.py"].language == "python"
    assert by_path["Dockerfile"].language == "dockerfile"
    assert by_path["data.unknownext"].language is None
