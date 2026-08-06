
import click
import pytest
from click.testing import CliRunner

from flask import Blueprint

@need_dotenv
def test_load_dotenv(monkeypatch):
    for item in ("FOO", "BAR", "SPAM", "HAM"):
        monkeypatch.delenv(item, False)

    monkeypatch.setenv("EGGS", "3")
    monkeypatch.chdir(test_path)
@need_dotenv
def test_dotenv_path(monkeypatch):
    for item in ("FOO", "BAR", "EGGS"):
        monkeypatch.delenv(item, False)

    load_dotenv(test_path / ".flaskenv")
    assert Path.cwd() == cwd


def test_dotenv_optional(monkeypatch):
    monkeypatch.delenv("FOO", False)
    monkeypatch.setitem(sys.modules, "dotenv", None)
    monkeypatch.chdir(test_path)
    load_dotenv()

@need_dotenv
def test_disable_dotenv_from_env(monkeypatch, runner):
    monkeypatch.delenv("FOO", False)
    monkeypatch.chdir(test_path)
    monkeypatch.setitem(os.environ, "FLASK_SKIP_DOTENV", "1")
    runner.invoke(FlaskGroup())
