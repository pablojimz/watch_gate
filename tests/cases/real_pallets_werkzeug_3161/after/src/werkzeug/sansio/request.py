
from ..datastructures import Accept
from ..datastructures import Authorization
from ..datastructures import ETags
from ..datastructures import Headers
from ..datastructures import HeaderSet
        return parse_accept_header(self.headers.get("Accept"), MIMEAccept)

    @cached_property
    def accept_charsets(self) -> Accept:
        """List of charsets this client supports as
        :class:`~werkzeug.datastructures.CharsetAccept` object.

        .. deprecated:: 3.2
            The header has not been used for a long time. Clients do not send
            it. Assume UTF-8. Will be removed in Werkzeug 3.3.
        """
        import warnings

        from ..datastructures.accept import _CharsetAccept

        warnings.warn(
            "The 'accept_charsets' attribute is deprecated and will be removed"
            " in Werkzeug 3.3. The header is not sent by browsers, and UTF-8 is"
            " assumed.",
            DeprecationWarning,
            stacklevel=2,
        )
        return parse_accept_header(self.headers.get("Accept-Charset"), _CharsetAccept)

    @cached_property
    def accept_encodings(self) -> Accept:
