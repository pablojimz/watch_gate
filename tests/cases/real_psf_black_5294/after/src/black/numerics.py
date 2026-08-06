def normalize_numeric_literal(leaf: Leaf) -> None:
    """Normalizes numeric (float, int, and complex) literals.

    All letters used in the representation are normalized to lowercase,
    except for hexadecimal literals, which are normalized to uppercase
    after the `0x` prefix."""
    text = leaf.value.lower()
    if text.startswith(("0o", "0b")):
        # Leave octal and binary literals alone.
