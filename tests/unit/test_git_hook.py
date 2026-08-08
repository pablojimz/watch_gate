"""Tests unitarios para el Hook Git pre-receive (watchgate/adapters/git_hook/)."""

from __future__ import annotations

import signal
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from watchgate.adapters.git_hook.pre_receive import (
    EMPTY_TREE_SHA,
    NULL_SHA,
    extract_diff_from_shas,
    parse_pre_receive_input,
    run_pre_receive,
)
from watchgate.core.models import AggregatedResult, LayerResult, Semaforo


def test_parse_pre_receive_input() -> None:
    stdin_data = (
        "0000000000000000000000000000000000000000 abc123def456 refs/heads/main\n"
        "1111111111111111111111111111111111111111 222222222222 refs/heads/feature\n"
    )
    parsed = parse_pre_receive_input(stdin_data)
    assert len(parsed) == 2
    assert parsed[0] == (
        "0000000000000000000000000000000000000000",
        "abc123def456",
        "refs/heads/main",
    )


def test_extract_diff_from_shas_null_sha_initial_push() -> None:
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.stdout = "diff --git a/file.py b/file.py\n+x = 1"
        mock_run.return_value = mock_proc

        diff_out = extract_diff_from_shas(
            old_sha=NULL_SHA, new_sha="1111111111111111111111111111111111111111"
        )
        assert "diff --git" in diff_out
        # Debe comparar contra el árbol vacío de Git
        cmd_args = mock_run.call_args[0][0]
        assert EMPTY_TREE_SHA in cmd_args[2]


def test_extract_diff_from_shas_propagates_subprocess_failure() -> None:
    """Antes, cualquier fallo de `git diff` (proceso, timeout, decodificación)
    se atrapaba con un `except Exception` genérico y se devolvía `""` --
    indistinguible de "no hay cambios". Ahora debe propagarse para que el
    llamador (`run_pre_receive`, con su política `fail_closed`) decida."""
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["git", "diff"])):
        with pytest.raises(subprocess.CalledProcessError):
            extract_diff_from_shas(
                old_sha=NULL_SHA, new_sha="1111111111111111111111111111111111111111"
            )


def test_run_pre_receive_fails_closed_when_diff_extraction_fails() -> None:
    """Caso real encontrado en revisión: un fallo al extraer el diff (p. ej.
    un `UnicodeDecodeError` con contenido binario en el push) se tragaba
    silenciosamente y el push se aceptaba SIN analizar -- fail-open en un
    hook `pre-receive`, justo donde se espera fail-closed. Con
    `fail_closed=True` (el valor por defecto) debe rechazar el push."""
    stdin_data = (
        "1111111111111111111111111111111111111111 "
        "2222222222222222222222222222222222222222 refs/heads/main\n"
    )
    with patch(
        "watchgate.adapters.git_hook.pre_receive.extract_diff_from_shas",
        side_effect=subprocess.CalledProcessError(1, ["git", "diff"]),
    ):
        exit_code = run_pre_receive(stdin_text=stdin_data, fail_closed=True)
    assert exit_code == 1


def test_run_pre_receive_respects_fail_open_when_diff_extraction_fails() -> None:
    """Con `fail_closed=False` explícito, un fallo de extracción del diff
    sigue sin bloquear el push -- el operador optó conscientemente por esa
    política, y debe seguir funcionando igual que para cualquier otro
    fallo de infraestructura."""
    stdin_data = (
        "1111111111111111111111111111111111111111 "
        "2222222222222222222222222222222222222222 refs/heads/main\n"
    )
    with patch(
        "watchgate.adapters.git_hook.pre_receive.extract_diff_from_shas",
        side_effect=subprocess.CalledProcessError(1, ["git", "diff"]),
    ):
        exit_code = run_pre_receive(stdin_text=stdin_data, fail_closed=False)
    assert exit_code == 0


@pytest.mark.skipif(not hasattr(signal, "SIGALRM"), reason="SIGALRM requiere POSIX")
def test_run_pre_receive_enforces_timeout_on_hung_analysis() -> None:
    """Caso real encontrado en revisión: `timeout_seconds` se aceptaba como
    parámetro (poblado desde `WATCHGATE_TIMEOUT`) pero nunca se usaba en
    ningún sitio -- un análisis colgado (p. ej. la capa semántica esperando
    una respuesta del LLM que nunca llega) bloqueaba `git push`
    INDEFINIDAMENTE. Con un timeout muy corto y un análisis que tarda más,
    debe rechazar el push (fail_closed) en vez de colgarse."""
    stdin_data = (
        "1111111111111111111111111111111111111111 "
        "2222222222222222222222222222222222222222 refs/heads/main\n"
    )
    dummy_diff = "diff --git a/app.py b/app.py\n+x = 1"

    def _hung_analysis(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ARG001
        time.sleep(5)
        raise AssertionError("no debería completarse: el timeout debió interrumpirlo antes")

    with patch(
        "watchgate.adapters.git_hook.pre_receive.extract_diff_from_shas",
        return_value=dummy_diff,
    ):
        with patch(
            "watchgate.adapters.git_hook.pre_receive.run_full_analysis",
            side_effect=_hung_analysis,
        ):
            start = time.monotonic()
            exit_code = run_pre_receive(
                stdin_text=stdin_data, fail_closed=True, timeout_seconds=0.2
            )
            elapsed = time.monotonic() - start

    assert exit_code == 1
    assert elapsed < 4  # se interrumpió por el timeout, no esperó los 5s completos


def test_run_pre_receive_approved_push() -> None:
    stdin_data = (
        "1111111111111111111111111111111111111111 "
        "2222222222222222222222222222222222222222 refs/heads/main\n"
    )
    dummy_diff = "diff --git a/app.py b/app.py\n+x = 1"

    aggregated_approved = AggregatedResult(
        score=10,
        semaforo=Semaforo.VERDE,
        layer_results={},
        weights_used={"static": 1.0},
        pr_id="main",
        repo=".",
        timestamp="2026-08-07T12:00:00Z",
    )

    with patch(
        "watchgate.adapters.git_hook.pre_receive.extract_diff_from_shas",
        return_value=dummy_diff,
    ):
        with patch(
            "watchgate.adapters.git_hook.pre_receive.run_full_analysis",
            return_value=aggregated_approved,
        ):
            exit_code = run_pre_receive(stdin_text=stdin_data)
            assert exit_code == 0


def test_run_pre_receive_blocked_push() -> None:
    stdin_data = (
        "1111111111111111111111111111111111111111 "
        "2222222222222222222222222222222222222222 refs/heads/main\n"
    )
    dummy_diff = "diff --git a/app.py b/app.py\n+eval(x)"

    aggregated_blocked = AggregatedResult(
        score=85,
        semaforo=Semaforo.ROJO,
        layer_results={
            "static": LayerResult(
                layer_name="static", risk_score=85, justification="eval detectado"
            )
        },
        weights_used={"static": 1.0},
        pr_id="main",
        repo=".",
        timestamp="2026-08-07T12:00:00Z",
    )

    with patch(
        "watchgate.adapters.git_hook.pre_receive.extract_diff_from_shas",
        return_value=dummy_diff,
    ):
        with patch(
            "watchgate.adapters.git_hook.pre_receive.run_full_analysis",
            return_value=aggregated_blocked,
        ):
            exit_code = run_pre_receive(stdin_text=stdin_data)
            assert exit_code == 1
