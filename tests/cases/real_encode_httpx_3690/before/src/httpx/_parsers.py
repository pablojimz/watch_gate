            # Handle body close
            self.send_state = State.DONE

    def recv_method_line(self) -> tuple[bytes, bytes, bytes]:
        """
        Receive the initial request method line:
        assert self._buffer == b''
        self._buffer = buffer

    def read(self, size: int) -> bytes:
        """
        Read and return up to 'size' bytes from the stream, with I/O buffering provided.
