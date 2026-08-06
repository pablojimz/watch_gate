

def _interpret_color(color: int | tuple[int, int, int] | str, offset: int = 0) -> str:
    if isinstance(color, int):
        return f"{38 + offset};5;{color:d}"

    if isinstance(color, (tuple, list)):
        r, g, b = color
        return f"{38 + offset};2;{r:d};{g:d};{b:d}"

    return str(_ansi_colors[color] + offset)


def style(
                  string which means that styles do not carry over.  This
                  can be disabled to compose styles.

    .. versionchanged:: 8.0
        A non-string ``message`` is converted to a string.


    bits = []

    if fg:
        try:
            bits.append(f"\033[{_interpret_color(fg)}m")
        except KeyError:
            raise TypeError(_("Unknown color {colour!r}").format(colour=fg)) from None

    if bg:
        try:
            bits.append(f"\033[{_interpret_color(bg, 10)}m")
        except KeyError:
            raise TypeError(_("Unknown color {colour!r}").format(colour=bg)) from None

    if bold is not None:
        bits.append(f"\033[{1 if bold else 22}m")
