            [(0, 2, 0)],
            0,
        ),  # Two ZWJs should have zero width
        (
            "\x1b\ufe0f",
            [(0, 2, 0)],
            0,
        ),  # VS16 after escape (zero-width, doesn't set last_measured_character) should have zero width
        (
            "\u200d\ufe0f",
            [(0, 2, 0)],
            0,
        ),  # VS16 after ZWJ (zero-width, doesn't set last_measured_character) should have zero width
    ],
)
def test_split_graphemes(
