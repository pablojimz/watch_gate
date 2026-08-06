        return default


class _CharsetAccept(Accept):
    """Like :class:`Accept` but with normalization for charsets."""

    def _value_matches(self, value: str, item: str) -> bool:
                return name.lower()

        return item == "*" or _normalize(value) == _normalize(item)


def __getattr__(name: str) -> t.Any:
    if name == "CharsetAccept":
        import warnings

        warnings.warn(
            "The 'CharsetAccept' class is deprecated and will be removed in"
            " Werkzeug 3.3. The 'Accept-Charset' header is not sent by"
            " browsers, and UTF-8 is assumed.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _CharsetAccept

    raise AttributeError(name)
