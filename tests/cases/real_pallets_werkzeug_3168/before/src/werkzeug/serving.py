from urllib.parse import urlsplit

from ._internal import _log
from ._internal import _wsgi_encoding_dance
from .datastructures import HeaderSet
from .exceptions import InternalServerError
    def read_chunk_len(self) -> int:
        try:
            line = self._rfile.readline().decode("latin1")
            _len = int(line.strip(), 16)
        except ValueError as e:
            raise OSError("Invalid chunk header") from e
        if _len < 0:
