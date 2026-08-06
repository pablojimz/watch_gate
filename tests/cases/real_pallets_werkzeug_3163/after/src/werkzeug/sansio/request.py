    def if_range(self) -> IfRange:
        """The parsed ``If-Range`` header.

        .. versionchanged:: 3.2
            A weak ETag is discarded.

        .. versionchanged:: 2.0
            ``IfRange.date`` is timezone-aware.

