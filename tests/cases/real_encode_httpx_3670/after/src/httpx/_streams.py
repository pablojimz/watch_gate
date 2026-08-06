import io
import typing
import types
import os



class FileStream(Stream):
    def __init__(self, path: str, fin: typing.Any) -> None:
        self._path = path
        self._fin = fin

    def read(self, size: int=-1) -> bytes:
        return self._fin.read(size)

    def close(self) -> None:
        self._fin.close()

    @property
    def size(self) -> int | None:
        return os.path.getsize(self._path)


class HTTPStream(Stream):
        # Mutable state...
        self._form_progress = list(self._form)
        self._files_progress = list(self._files)
        self._fin: typing.Any = None
        self._complete = False
        self._buffer = io.BytesIO()

                f"\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        elif self._files_progress and self._fin is None:
            # return start of a file item
            key, value = self._files_progress.pop(0)
            self._fin = open(value, 'rb')
            name = key.translate({10: "%0A", 13: "%0D", 34: "%22"})
            filename = os.path.basename(value)
            return (
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"\r\n"
            ).encode("utf-8")
        elif self._fin is not None:
            chunk = self._fin.read(64*1024)
            if chunk != b'':
                # return some bytes from file
                return chunk
            else:
                # return end of file item
                self._fin.close()
                self._fin = None
                return b"\r\n"
        elif not self._complete:
            # return final section of multipart
        return b""

    def close(self) -> None:
        if self._fin is not None:
            self._fin.close()
            self._fin = None
        self._buffer.close()

    @property
