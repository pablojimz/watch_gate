    def handle_requests(self):
        try:
            while not self._parser.is_closed():
                method, url, headers = self._recv_head()
                stream = HTTPStream(self._recv_body, self._reset)
                # TODO: Handle endpoint exceptions
                with Request(method, url, headers=headers, content=stream) as request:
                    try:
                        response = self._endpoint(request)
                        self._send_head(response)
                        self._send_body(response)
                if self._parser.is_keepalive():
                    stream.read()
                self._reset()
        except Exception:
            logger.error("Internal Server Error", exc_info=True)

    def wait(self):
        while(True):
            try:
                sleep(1)
            except KeyboardInterrupt:
                break


@contextlib.contextmanager
