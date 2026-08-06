import io
import types
import os



class FileStream(Stream):
    def __init__(self, path):
        self._path = path
        self._fileobj = None
        self._size = None

    def read(self, size: int=-1) -> bytes:
        if self._fileobj is None:
            raise ValueError('I/O operation on unopened file')
        return self._fileobj.read(size)

    def open(self):
        self._fileobj = open(self._path, 'rb')
        self._size = os.path.getsize(self._path)
        return self

    def close(self) -> None:
        if self._fileobj is not None:
            self._fileobj.close()

    @property
    def size(self) -> int | None:
        return self._size

    def __enter__(self):
        self.open()
        return self


class HTTPStream(Stream):
        # Mutable state...
        self._form_progress = list(self._form)
        self._files_progress = list(self._files)
        self._filestream: FileStream | None = None
        self._complete = False
        self._buffer = io.BytesIO()

                f"\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        elif self._files_progress and self._filestream is None:
            # return start of a file item
            key, value = self._files_progress.pop(0)
            self._filestream = FileStream(value).open()
            name = key.translate({10: "%0A", 13: "%0D", 34: "%22"})
            filename = os.path.basename(value)
            return (
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"\r\n"
            ).encode("utf-8")
        elif self._filestream is not None:
            chunk = self._filestream.read(64*1024)
            if chunk != b'':
                # return some bytes from file
                return chunk
            else:
                # return end of file item
                self._filestream.close()
                self._filestream = None
                return b"\r\n"
        elif not self._complete:
            # return final section of multipart
        return b""

    def close(self) -> None:
        if self._filestream is not None:
            self._filestream.close()
            self._filestream = None
        self._buffer.close()

    @property
