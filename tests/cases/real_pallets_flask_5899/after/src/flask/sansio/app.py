
        return False

    should_ignore_error: None = None
    """If this method returns ``True``, the error will not be passed to
    teardown handlers, and the context will not be preserved for
    debugging.

    .. deprecated:: 3.2
        Handle errors as needed in teardown handlers instead.

    .. versionadded:: 0.10
    """

    def redirect(self, location: str, code: int = 303) -> BaseResponse:
        """Create a redirect response object.
