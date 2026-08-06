

class IfRange:
    """A parsed ``If-Range`` header. Either a strong ETag or a date, but not
    both. Weak ETag values must not be used.

    .. versionadded:: 0.7
    """

    def __init__(self, etag: str | None = None, date: datetime | None = None):
        self.etag = etag
        """A strong ETag value, unquoted, without weakness information. Weak
        ETag values must not be used.
        """

        self.date = date
        """A parsed datetime object."""

    @classmethod
    def from_header(cls, value: str | None) -> te.Self:
        """Parse an ``If-Range`` header value and create an instance of this
        class. A weak ETag value is discarded.

        .. versionadded:: 3.2
        """
        if (date := parse_date(value)) is not None:
            return cls(date=date)

        value, weak = unquote_etag(value)

        if weak:
            return cls()

        return cls(etag=value)

    def to_header(self) -> str:
        """Convert to an ``If-Range`` header value."""
