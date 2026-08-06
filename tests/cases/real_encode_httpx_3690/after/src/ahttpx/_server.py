    async def handle_requests(self):
        try:
            while not self._parser.is_closed():
                if not await self._parser.wait_ready():
                    # Wait until we have read data, or return
                    # if the stream closes.
                    return
                # Read the initial part of the request,
                # and setup a stream for reading the body.
                method, url, headers = await self._recv_head()
                stream = HTTPStream(self._recv_body, self._reset)
                async with Request(method, url, headers=headers, content=stream) as request:
                    try:
                        response = await self._endpoint(request)
                        await self._send_head(response)
                        await self._send_body(response)
                if self._parser.is_keepalive():
                    # If the client hasn't read the request body to
                    # completion, then do that here.
                    await stream.read()
                # Either revert to idle, or close the connection.
                await self._reset()
        except Exception:
            logger.error("Internal Server Error", exc_info=True)
