            "",
            id="styled-long-word-breaks-on-visible-width",
        ),
        # Colon-delimited true-color (ISO 8613-6) escapes are excluded from the
        # width budget too.
        pytest.param(
            "\x1b[38:2:255:0:0malpha\x1b[0m \x1b[38:2:0:255:0mbeta\x1b[0m"
            " \x1b[38:2:0:0:255mgamma\x1b[0m \x1b[38:2:9:9:9mdelta\x1b[0m",
            15,
            "",
            id="colon-truecolor-body-wraps-on-visible-width",
        ),
        # A mouse-reporting sequence embedded mid-line is zero-width too.
        pytest.param(
            "\x1b[<0;1;1malpha beta gamma delta\x1b[<0;1;1m",
            15,
            "",
            id="mouse-sequence-is-zero-width",
        ),
    ],
)
def test_wrap_text_visible_width(body, width, initial_indent):
