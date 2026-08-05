"""Tests de cli.py."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import git
import pytest

from watchgate.cli import main


@pytest.fixture
def tmp_git_repo():
    tmp_dir = tempfile.mkdtemp()
    repo = git.Repo.init(tmp_dir)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test User")
        cw.set_value("user", "email", "test@example.com")

    # Initial commit
    a_file = Path(tmp_dir) / "main.py"
    a_file.write_text("print('hello')\n")
    repo.index.add(["main.py"])
    base_commit = repo.index.commit("initial commit")

    # Second commit
    a_file.write_text("print('hello world')\n")
    repo.index.add(["main.py"])
    head_commit = repo.index.commit("update main.py")

    yield tmp_dir, base_commit.hexsha, head_commit.hexsha
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_cli_help_returns_zero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "WatchGate" in captured.out


def test_cli_no_args_prints_help(capsys):
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out or "subcomandos" in captured.out


def test_cli_analyze_comment_format(tmp_git_repo, capsys):
    repo_dir, base_sha, head_sha = tmp_git_repo

    code = main(
        [
            "analyze",
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--repo-path",
            repo_dir,
            "--format",
            "comment",
        ]
    )

    assert code == 0
    captured = capsys.readouterr()
    assert "WatchGate: Riesgo" in captured.out


def test_cli_analyze_json_format(tmp_git_repo, capsys):
    repo_dir, base_sha, head_sha = tmp_git_repo

    code = main(
        [
            "analyze",
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--repo-path",
            repo_dir,
            "--format",
            "json",
        ]
    )

    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "score" in data
    assert "semaforo" in data
    assert "layer_results" in data


def test_cli_analyze_saves_output_to_file(tmp_git_repo, tmp_path, capsys):
    repo_dir, base_sha, head_sha = tmp_git_repo
    out_file = tmp_path / "result.md"

    code = main(
        [
            "analyze",
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--repo-path",
            repo_dir,
            "--output",
            str(out_file),
        ]
    )

    assert code == 0
    assert out_file.exists()
    file_content = out_file.read_text(encoding="utf-8")
    assert "WatchGate: Riesgo" in file_content


def test_cli_rag_reindex(tmp_path, capsys):
    index_path = str(tmp_path / "rag_index")

    with patch("watchgate.cli.build_index", return_value=12) as mock_build:
        code = main(["rag", "reindex", "--index-path", index_path])

    assert code == 0
    mock_build.assert_called_once_with(index_path=index_path)
    captured = capsys.readouterr()
    assert "[WatchGate] Indexados 12 fragmentos" in captured.out
