

class IfRange:
    """Very simple object that represents the `If-Range` header in parsed
    form.  It will either have neither a etag or date or one of either but
    never both.

    .. versionadded:: 0.7
    """

    def __init__(self, etag: str | None = None, date: datetime | None = None):
        #: The etag parsed and unquoted.  Ranges always operate on strong
        #: etags so the weakness information is not necessary.
        self.etag = etag
        #: The date in parsed format or `None`.
        self.date = date

    @classmethod
    def from_header(cls, value: str | None) -> te.Self:
        """Parse an ``If-Range`` header value and create an instance of this class.

        .. versionadded:: 3.2
        """
        if (date := parse_date(value)) is not None:
            return cls(date=date)

        # drop weakness information
        return cls(unquote_etag(value)[0])

    def to_header(self) -> str:
        """Convert to an ``If-Range`` header value."""
