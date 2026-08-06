        return f"<{type(self).__name__} {self.name}>"


_plain_int_re = re.compile(r"-?\d+", re.ASCII)


def _plain_int(value: str) -> int:
    """Parse an int only if it is only ASCII digits and ``-``.

    This disallows ``+``, ``_``, and non-ASCII digits, which are accepted by ``int`` but
    are not allowed in HTTP header values.

    Any leading or trailing whitespace is stripped
    """
    value = value.strip()
    if _plain_int_re.fullmatch(value) is None:
        raise ValueError

    return int(value)
