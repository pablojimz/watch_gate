        return self

    def add_etag(self, overwrite: bool = False, weak: bool = False) -> None:
        """Add an etag for the current response if there is none yet.

        .. versionchanged:: 2.0
            SHA-1 is used to generate the value. MD5 may not be
            available in some environments.
        """
        if overwrite or "ETag" not in self.headers:
            self.set_etag(generate_etag(self.get_data()), weak)
