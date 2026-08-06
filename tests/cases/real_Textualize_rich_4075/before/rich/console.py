from functools import wraps
from itertools import islice
from math import ceil
from time import monotonic
from types import FrameType, ModuleType, TracebackType
from typing import (
    cast,
    runtime_checkable,
)
from os import PathLike

from rich._null_file import NULL_FILE

            new_line_start (bool, False): Insert a new line at the start if the output contains more than one line. Defaults to ``False``.
        """
        if not objects:
            objects = (NewLine(),)

        if soft_wrap is None:
            soft_wrap = self.soft_wrap
                del self._record_buffer[:]
        return text

    def save_text(self, path: Union[str, PathLike[str]], *, clear: bool = True, styles: bool = False) -> None:
        """Generate text from console and save to a given location (requires record=True argument in constructor).

        Args:
