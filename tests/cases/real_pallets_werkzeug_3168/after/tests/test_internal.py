import pytest

from werkzeug._internal import _plain_int
from werkzeug.test import create_environ
from werkzeug.wrappers import Request
from werkzeug.wrappers import Response
    response = Response(["Hällo Wörld".encode()])
    headers = response.get_wsgi_headers(create_environ())
    assert "Content-Length" in headers


@pytest.mark.parametrize(
    ("value", "base", "expect"),
    [
        ("123", 10, 123),
        ("-123", 10, -123),
        ("1_23", 10, None),
        ("+123", 10, None),
        ("𝟙𝟚𝟛", 10, None),
        ("7B", 10, None),
        ("7B", 16, 123),
        ("-7B", 16, -123),
        ("7b", 16, 123),
    ],
)
def test_plain_int(value: str, base: int, expect: int | None) -> None:
    if expect is None:
        with pytest.raises(ValueError):
            _plain_int(value, base)
    else:
        assert _plain_int(value, base) == expect
