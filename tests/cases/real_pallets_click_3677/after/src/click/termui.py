

def _interpret_color(color: int | tuple[int, int, int] | str, offset: int = 0) -> str:
    """Interprets a color value and returns the corresponding ANSI code."""
    if isinstance(color, str) and color in _ansi_colors:
        return str(_ansi_colors[color] + offset)

    # bool is an int subclass: without the exclusion, True and False would
    # silently render as the palette indices 1 and 0.
    elif isinstance(color, int) and not isinstance(color, bool):
        if 0 <= color <= 255:
            return f"{38 + offset};5;{color:d}"

    elif (
        isinstance(color, (tuple, list))
        and len(color) == 3
        and all(
            isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255
            for c in color
        )
    ):
        r, g, b = color
        return f"{38 + offset};2;{r:d};{g:d};{b:d}"

    raise ValueError(_("Unknown color {colour!r}").format(colour=color))


def style(
                  string which means that styles do not carry over.  This
                  can be disabled to compose styles.

    .. versionchanged:: 8.5
        All invalid color values raise :exc:`ValueError`. 256-color index
        ``0`` is not ignored

    .. versionchanged:: 8.0
        A non-string ``message`` is converted to a string.


    bits = []

    if fg is not None:
        bits.append(f"\033[{_interpret_color(fg)}m")

    if bg is not None:
        bits.append(f"\033[{_interpret_color(bg, 10)}m")

    if bold is not None:
        bits.append(f"\033[{1 if bold else 22}m")
