    def handle_requests(self):
        try:
            while not self._parser.is_closed():
                if not self._parser.wait_ready():
                    # Wait until we have read data, or return
                    # if the stream closes.
                    return
                # Read the initial part of the request,
                # and setup a stream for reading the body.
                method, url, headers = self._recv_head()
                stream = HTTPStream(self._recv_body, self._reset)
                with Request(method, url, headers=headers, content=stream) as request:
                    try:
                        response = self._endpoint(request)
                        self._send_head(response)
                        self._send_body(response)
                if self._parser.is_keepalive():
                    # If the client hasn't read the request body to
                    # completion, then do that here.
                    stream.read()
                # Either revert to idle, or close the connection.
                self._reset()
        except Exception:
            logger.error("Internal Server Error", exc_info=True)

    def wait(self):
        while(True):
            sleep(1)


@contextlib.contextmanager
