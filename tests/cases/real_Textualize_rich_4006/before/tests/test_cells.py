    assert chop_cells(text, 3) == ["あ1", "り2", "34", "が5", "と6", "う7", "8"]


def test_is_single_cell_widths() -> None:
    # Check _is_single_cell_widths reports correctly
    for character in string.printable:
        ("♻", [(0, 1, 1)], 1),
        ("♻️", [(0, 2, 2)], 2),
        ("♻♻️", [(0, 1, 1), (1, 3, 2)], 3),
    ],
)
def test_split_graphemes(
    text: str, expected_spans: list[CellSpan], expected_cell_length: int
):
    spans, cell_length = split_graphemes(text)
    assert cell_len(text) == expected_cell_length
    assert spans == expected_spans
    assert cell_length == expected_cell_length
