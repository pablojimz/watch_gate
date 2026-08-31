"""Fragmento benigno de ejemplo: un test unitario normal."""

from __future__ import annotations


def add(a: int, b: int) -> int:
    return a + b


def test_add_returns_the_sum_of_two_numbers() -> None:
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
