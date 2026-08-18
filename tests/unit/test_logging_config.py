"""Tests de watchgate/logging_config.py."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from watchgate.logging_config import _scrub_sentry_event, configure_logging, configure_sentry


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
    from watchgate.logging_config import setup_logging_sanitizer

    configure_logging("engine-api")
    setup_logging_sanitizer()

    logging.getLogger("watchgate.test").warning("peticion con key wg_live_9f8e7d6c5b4a3f2e")

    out = capsys.readouterr().out
    assert "wg_live_9f8e7d6c5b4a3f2e" not in out
    assert "[REDACTED_SECRET]" in out


def test_secret_redaction_covers_github_personal_access_tokens(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresión: el filtro original solo cubría claves propias de
    WatchGate/LLM -- ni un PAT de GitHub clásico (ghp_...) ni uno
    fine-grained (github_pat_...) se redactaban, pese a ser justo lo que
    las credenciales VCS por usuario (Mi Cuenta) manejan ahora."""
    from watchgate.logging_config import setup_logging_sanitizer

    monkeypatch.setenv("WATCHGATE_LOG_FORMAT", "json")
    configure_logging("dashboard-backend")
    setup_logging_sanitizer()

    logging.getLogger("watchgate.test").warning(
        "token classic=ghp_abcdefghijklmnopqrstuvwxyz0123456789 "
        "fine-grained=github_pat_11ABCDEFG0123456789abcdefghijklmnopqrstuvwxyz"
    )

    out = capsys.readouterr().out
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in out
    assert "github_pat_11ABCDEFG0123456789abcdefghijklmnopqrstuvwxyz" not in out
    assert out.count("[REDACTED_SECRET]") == 2


def test_configure_sentry_is_a_noop_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATCHGATE_SENTRY_DSN", raising=False)
    with patch("sentry_sdk.init") as mock_init:
        configure_sentry("test-service")
    mock_init.assert_not_called()


def test_configure_sentry_initializes_with_safe_defaults_when_dsn_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No basta con que Sentry se active -- tiene que activarse SIN abrir
    una vía nueva de fuga de secretos (variables locales de un traceback,
    o el propio filtro de redacción de logging quedando bypaseado por el
    handler que el SDK añade por su cuenta)."""
    monkeypatch.setenv("WATCHGATE_SENTRY_DSN", "https://fake@sentry.example/1")
    with patch("sentry_sdk.init") as mock_init:
        configure_sentry("dashboard-backend")

    mock_init.assert_called_once()
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://fake@sentry.example/1"
    assert kwargs["server_name"] == "dashboard-backend"
    assert kwargs["send_default_pii"] is False
    assert kwargs["include_local_variables"] is False
    assert kwargs["before_send"] is _scrub_sentry_event
    # Integración de logging desactivada a propósito -- ver docstring de
    # configure_sentry.
    (logging_integration,) = kwargs["integrations"]
    assert logging_integration._handler is None
    assert logging_integration._breadcrumb_handler is None


def test_scrub_sentry_event_redacts_message_and_exception_values() -> None:
    leaked_token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    event = {
        "message": "fallo con key wg_live_9f8e7d6c5b4a3f2e",
        "exception": {
            "values": [{"type": "ValueError", "value": f"token inválido: {leaked_token}"}]
        },
    }
    scrubbed = _scrub_sentry_event(event, {})
    assert scrubbed is not None
    assert "wg_live_9f8e7d6c5b4a3f2e" not in scrubbed["message"]
    assert "[REDACTED_SECRET]" in scrubbed["message"]
    exc_value = scrubbed["exception"]["values"][0]["value"]
    assert leaked_token not in exc_value
