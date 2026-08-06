        """Decode ANSI codes in an iterable of lines.

        Args:
            lines (Iterable[str]): An iterable of lines of terminal output.

        Yields:
            Text: Marked up Text.
        """
        for line in terminal_text.splitlines():
            yield self.decode_line(line)

    def decode_line(self, line: str) -> Text:
        """Decode a line containing ansi codes.
