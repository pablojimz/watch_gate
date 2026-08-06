
import enum
import os

import pytest


@pytest.mark.parametrize(
    ("value", "expect"),
    [
        *((x, "True") for x in ("1", "true", "t", "yes", "y", "on")),
        *((x, "False") for x in ("0", "false", "f", "no", "n", "off")),
    ],
)
def test_boolean_conversion(runner, value, expect):
    @click.command()
