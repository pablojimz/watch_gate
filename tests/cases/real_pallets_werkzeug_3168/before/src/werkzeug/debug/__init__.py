from zlib import adler32

from .._internal import _log
from ..exceptions import NotFound
from ..exceptions import SecurityError
from ..http import parse_cookie
        ts_str, pin_hash = val.split("|", 1)

        try:
            ts = int(ts_str)
        except ValueError:
            return False

