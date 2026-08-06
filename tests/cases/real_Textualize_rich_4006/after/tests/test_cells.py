    assert chop_cells(text, 3) == ["あ1", "り2", "34", "が5", "と6", "う7", "8"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", []),
        ("\x1b", []),
        ("\x1b\x1b", []),
        ("\x1b\x1b\x1b", []),
        ("\x1b\x1b\x1b\x1b", []),
    ],
)
def test_chop_cells_zero_width(text: str, expected: list[str]) -> None:
    """Test zer width characters being chopped."""
    assert chop_cells(text, 3) == expected


def test_is_single_cell_widths() -> None:
    # Check _is_single_cell_widths reports correctly
    for character in string.printable:
        ("♻", [(0, 1, 1)], 1),
        ("♻️", [(0, 2, 2)], 2),
        ("♻♻️", [(0, 1, 1), (1, 3, 2)], 3),
        ("\x1b", [(0, 1, 0)], 0),  # One escape should have zero width
        ("\x1b\x1b", [(0, 2, 0)], 0),  # Two escapes should have zero width
        (
            "\ufe0f",
            [(0, 1, 0)],
            0,
        ),  # Variation selector 16, without anything to change should have zero width
        (
            "\ufe0f\ufe0f",
            [(0, 2, 0)],
            0,
        ),  # 2 X variation selector 16, without anything to change should have zero width
        (
            "\u200d",
            [(0, 1, 0)],
            0,
        ),  # A zero width joiner within noting prior should have zero width
        (
            "\u200d\u200d",
            [(0, 2, 0)],
            0,
        ),  # Two ZWJs should have zero width
    ],
)
def test_split_graphemes(
    text: str, expected_spans: list[CellSpan], expected_cell_length: int
):
    spans, cell_length = split_graphemes(text)
    print(spans)
    assert cell_len(text) == expected_cell_length
    assert spans == expected_spans
    assert cell_length == expected_cell_length
