            # Handle body close
            self.send_state = State.DONE

    def wait_ready(self) -> bool:
        """
        Wait until read data starts arriving, and return `True`.
        Return `False` if the stream closes.
        """
        return self.parser.wait_ready()

    def recv_method_line(self) -> tuple[bytes, bytes, bytes]:
        """
        Receive the initial request method line:
        assert self._buffer == b''
        self._buffer = buffer

    def wait_ready(self) -> bool:
        """
        Attempt a read, and return True if read succeeds or False if the
        stream is closed. The data remains in the read buffer.
        """
        data = self._read_some()
        self._push_back(data)
        return data != b''

    def read(self, size: int) -> bytes:
        """
        Read and return up to 'size' bytes from the stream, with I/O buffering provided.
