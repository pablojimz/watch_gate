        return default


class CharsetAccept(Accept):
    """Like :class:`Accept` but with normalization for charsets."""

    def _value_matches(self, value: str, item: str) -> bool:
                return name.lower()

        return item == "*" or _normalize(value) == _normalize(item)
