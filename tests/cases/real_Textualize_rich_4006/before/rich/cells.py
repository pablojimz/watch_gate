def split_graphemes(
    text: str, unicode_version: str = "auto"
) -> "tuple[list[CellSpan], int]":
    """Divide text into spans that define a single grapheme.

    Args:
        text: String to split.
        unicode_version: Unicode version, `"auto"` to auto detect, `"latest"` for the latest unicode version.

    Returns:
        List of spans.
    """

    cell_table = load_cell_table(unicode_version)
    SPECIAL = {"\u200d", "\ufe0f"}
    while index < codepoint_count:
        if (character := text[index]) in SPECIAL:
            if character == "\u200d":
                # zero width joiner
                index += 2
                if spans:
                    start, _end, cell_length = spans[-1]
                    spans[-1] = (start, index, cell_length)
            elif last_measured_character:
                # variation selector 16
                index += 1
                if spans:
                    start, _end, cell_length = spans[-1]
                    if last_measured_character in cell_table.narrow_to_wide:
                        last_measured_character = None
                        cell_length += 1
                        total_width += 1
                    spans[-1] = (start, index, cell_length)
            continue

        if character_width := get_character_cell_size(character, unicode_version):
            last_measured_character = character
            spans.append((index, index := index + 1, character_width))
            total_width += character_width
        elif spans:
            # zero width characters are associated with the previous character
            start, _end, cell_length = spans[-1]
            spans[-1] = (start, index := index + 1, cell_length)

    return (spans, total_width)

