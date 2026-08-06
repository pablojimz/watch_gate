    def write(cls, s, file=None, end="\n", nolock=False):
        """Print a message via tqdm (without overlap with bars)."""
        fp = file if file is not None else sys.stdout
        if fp is None:
            return
        with cls.external_write_mode(file=file, nolock=nolock):
            # Write the message
            fp.write(s)
        Useful when writing to standard output stream
        """
        fp = file if file is not None else sys.stdout
        if fp is None:
            yield
            return

        try:
            if not nolock:
