            # Handle body close
            self.send_state = State.DONE

    async def wait_ready(self) -> bool:
        """
        Wait until read data starts arriving, and return `True`.
        Return `False` if the stream closes.
        """
        return await self.parser.wait_ready()

    async def recv_method_line(self) -> tuple[bytes, bytes, bytes]:
        """
        Receive the initial request method line:
        assert self._buffer == b''
        self._buffer = buffer

    async def wait_ready(self) -> bool:
        """
        Attempt a read, and return True if read succeeds or False if the
        stream is closed. The data remains in the read buffer.
        """
        data = await self._read_some()
        self._push_back(data)
        return data != b''

    async def read(self, size: int) -> bytes:
        """
        Read and return up to 'size' bytes from the stream, with I/O buffering provided.
