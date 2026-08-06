        """Returns ``True`` if autoescaping should be active for the given
        template name. If no template name is given, returns `True`.

        .. versionchanged:: 2.2
            Autoescaping is now enabled by default for ``.svg`` files.

        """
        if filename is None:
            return True
        return filename.endswith((".html", ".htm", ".xml", ".xhtml", ".svg"))

    @property
    def debug(self) -> bool:
