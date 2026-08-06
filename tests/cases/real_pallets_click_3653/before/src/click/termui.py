from contextlib import redirect_stdout
from gettext import gettext as _

from ._compat import isatty
from ._compat import strip_ansi
from .exceptions import Abort
def _readline_prompt(func: t.Callable[[str], str], text: str, err: bool) -> str:
    """Call a prompt function, passing the full prompt on non-Windows so
    readline can handle line editing and cursor positioning correctly.
    """
    if err:
        with redirect_stdout(sys.stderr):
            return func(text)
