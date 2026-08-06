        return f"<{type(self).__name__} {self.name}>"


_plain_int_re = re.compile(r"-?[a-z0-9]+", re.ASCII | re.IGNORECASE)


def _plain_int(value: str, base: int = 10) -> int:
    """Parse an int only if it is ASCII digits and ``-``.

    This disallows ``+``, ``_``, and non-ASCII digits, which are accepted by
    ``int`` but are not allowed in HTTP header values.

    Any surrounding whitespace is stripped.
    """
    value = value.strip()

    if _plain_int_re.fullmatch(value) is None:
        raise ValueError

    return int(value, base)
