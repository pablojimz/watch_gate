        """Decode ANSI codes in an iterable of lines.

        Args:
            terminal_text: Output potentially containing ANSI escape sequences.

        Yields:
            Text: Marked up Text.
        """
        for line in re.split(r"(?<=\n)", terminal_text):
            yield self.decode_line(line.rstrip("\n"))

    def decode_line(self, line: str) -> Text:
        """Decode a line containing ansi codes.
