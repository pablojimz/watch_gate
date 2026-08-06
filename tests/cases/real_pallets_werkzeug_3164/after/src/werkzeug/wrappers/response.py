        return self

    def add_etag(self, overwrite: bool = False, weak: bool = False) -> None:
        """Add an ETag by hashing this response's data. This causes the data to
        be read, don't call this on a streaming response.

        :param overwrite: Overwrite an existing ``ETag`` header.
        :param weak: Mark the ETag as weak. This is unlikely what you want, as
            a hash of the data is typically considered strong.

        .. versionchanged:: 3.2
            Use SHA3-256.

        .. versionchanged:: 2.0
            Use SHA-1.
        """
        if overwrite or "ETag" not in self.headers:
            self.set_etag(generate_etag(self.get_data()), weak)
