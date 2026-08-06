        kw["method"] = "GET"
        return self.open(*args, **kw)

    def post(self, *args: t.Any, **kw: t.Any) -> TestResponse:
        """Call :meth:`open` with ``method`` set to ``POST``."""
        kw["method"] = "POST"
