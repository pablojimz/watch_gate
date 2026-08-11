"""Tests de watchgate/logging_config.py."""

from __future__ import annotations

import json
import logging

import pytest

from watchgate.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """`configure_logging()` reemplaza los handlers del logger raíz --
    sin restaurar el estado previo, un test que corra después con sus
    propias expectativas de logging (o pytest's caplog) podría ver
    handlers inesperados."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_json_format_produces_valid_json_with_service_field(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WATCHGATE_LOG_FORMAT", "json")
    configure_logging("test-service")

    logging.getLogger("watchgate.somewhere").warning("hola %s", "mundo")

    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert record["message"] == "hola mundo"
    assert record["service"] == "test-service"
    assert record["level"] == "WARNING"
    assert record["logger"] == "watchgate.somewhere"
    assert "timestamp" in record


def test_text_format_is_the_default(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WATCHGATE_LOG_FORMAT", raising=False)
    configure_logging("test-service")

    logging.getLogger("watchgate.somewhere").warning("mensaje de texto")

    out = capsys.readouterr().out
    assert "mensaje de texto" in out
    assert "test-service" in out
    # No debe poder parsearse como JSON -- si algún día esto empieza a
    # fallar porque el texto por casualidad parece JSON, es una señal de
    # que el formato por defecto cambió sin querer.
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip())


def test_log_level_env_var_is_respected(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WATCHGATE_LOG_LEVEL", "ERROR")
    configure_logging("test-service")

    logging.getLogger("watchgate.somewhere").info("no debería salir")
    logging.getLogger("watchgate.somewhere").error("sí debería salir")

    out = capsys.readouterr().out
    assert "no debería salir" not in out
    assert "sí debería salir" in out


def test_secret_redaction_survives_configure_logging(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """El orden documentado en api/main.py::lifespan (configure_logging
    ANTES que setup_logging_sanitizer) es justo para que esto funcione --
    test de regresión directo sobre esa integración, no solo sobre
    CryptographicLogFilter en aislado (que ya cubre test_security_audit.py)."""
    monkeypatch.setenv("WATCHGATE_LOG_FORMAT", "json")
    from watchgate.api.main import setup_logging_sanitizer

    configure_logging("engine-api")
    setup_logging_sanitizer()

    logging.getLogger("watchgate.test").warning("peticion con key wg_live_9f8e7d6c5b4a3f2e")

    out = capsys.readouterr().out
    assert "wg_live_9f8e7d6c5b4a3f2e" not in out
    assert "[REDACTED_SECRET]" in out
