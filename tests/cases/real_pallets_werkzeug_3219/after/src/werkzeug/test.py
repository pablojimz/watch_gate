        kw["method"] = "GET"
        return self.open(*args, **kw)

    def query(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``QUERY``.

        .. versionadded:: 3.2
        """
        kw["method"] = "QUERY"
        return self.open(*args, **kw)

    def post(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``POST``."""
        kw["method"] = "POST"
