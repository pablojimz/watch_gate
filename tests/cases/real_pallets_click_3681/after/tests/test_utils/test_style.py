        click.style("x y", **{param: value})


@pytest.mark.parametrize(
    ("text", "expect"),
    [
        ("\x1b[?25lx y\x1b[?25h", "x y"),
        # Colon-delimited true-color SGR (ISO 8613-6).
        ("\x1b[38:2:255:0:0mx y\x1b[0m", "x y"),
        # 256-color with colon sub-parameters.
        ("\x1b[38:5:200mx y\x1b[0m", "x y"),
        # SGR mouse reporting.
        ("\x1b[<0;1;1Mx y\x1b[<0;1;1m", "x y"),
        # Intermediate byte before the final byte.
        ("\x1b[0 qx y", "x y"),
        # Non-letter final byte.
        ("x\x1b[3~y", "xy"),
    ],
)
def test_unstyle_other_ansi(text, expect):
    assert click.unstyle(text) == expect
