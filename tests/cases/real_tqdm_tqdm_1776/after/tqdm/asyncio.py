                       total=total, **tqdm_kwargs)

    @classmethod
    async def gather(cls, *fs, loop=None, timeout=None, total=None, return_exceptions=False,
                     **tqdm_kwargs):
        """
        Wrapper for `asyncio.gather`.
        """
        async def wrap_awaitable(i, f):
            try:
                return i, await f
            except Exception as e:  # noqa: BLE001
                if return_exceptions:
                    return i, e
                raise

        ifs = [wrap_awaitable(i, f) for i, f in enumerate(fs)]
        res = [await f for f in cls.as_completed(ifs, loop=loop, timeout=timeout,
