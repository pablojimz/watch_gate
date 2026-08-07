"""Tests unitarios para el Hook Git pre-receive (watchgate/adapters/git_hook/)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
