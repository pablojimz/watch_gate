    async def handle_requests(self):
        try:
            while not self._parser.is_closed():
                method, url, headers = await self._recv_head()
                stream = HTTPStream(self._recv_body, self._reset)
                # TODO: Handle endpoint exceptions
                async with Request(method, url, headers=headers, content=stream) as request:
                    try:
                        response = await self._endpoint(request)
                        await self._send_head(response)
                        await self._send_body(response)
                if self._parser.is_keepalive():
                    await stream.read()
                await self._reset()
        except Exception:
            logger.error("Internal Server Error", exc_info=True)
