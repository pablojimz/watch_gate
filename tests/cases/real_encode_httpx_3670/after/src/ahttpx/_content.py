        return os.path.getsize(self._path)

    def encode(self) -> Stream:
        fin = open(self._path, 'rb')
        return FileStream(self._path, fin)

    def content_type(self) -> str:
        _, ext = os.path.splitext(self._path)
