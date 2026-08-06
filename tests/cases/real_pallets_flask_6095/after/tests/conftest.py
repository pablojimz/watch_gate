import sys

import pytest

from flask import Flask
from flask.globals import request_ctx


@pytest.fixture(autouse=True)
def _standard_os_environ(monkeypatch):
    """Set up ``os.environ`` at the start of every test to have
    standard values.
    """
    for key in (
        "FLASK_ENV_FILE",
        "FLASK_APP",
        "FLASK_DEBUG",
        "FLASK_RUN_FROM_CLI",
        "WERKZEUG_RUN_MAIN",
    ):
        monkeypatch.delenv(key, False)

    yield


@pytest.fixture
