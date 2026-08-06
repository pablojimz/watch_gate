from __future__ import annotations

import sys

import pytest

import click


def test_is_jupyter_kernel_output():
    if expected_override is not None:
        expected = expected_override
    assert click._compat.should_strip_ansi(stream=stream, color=color) == expected
