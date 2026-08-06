        return os.path.getsize(self._path)

    def encode(self) -> Stream:
        return FileStream(self._path)

    def content_type(self) -> str:
        _, ext = os.path.splitext(self._path)
