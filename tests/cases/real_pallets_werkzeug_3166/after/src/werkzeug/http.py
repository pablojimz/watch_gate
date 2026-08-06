import re
import typing as t
import warnings
from base64 import b64encode
from datetime import date
from datetime import datetime
from datetime import time
    """Generate a strong ETag value by hashing the given data.

    .. versionchanged:: 3.2
        Use SHA3-256. SHA-1 is not allowed in FIPS-enabled systems. Use base64
        instead of hex digest. This increases the length from 40 to 43
        characters.

    .. versionchanged:: 2.0
        Use SHA-1. MD5 is not allowed in FIPS-enabled systems. This increases
        the length from 32 to 40 characters.
    """
    digest = hashlib.sha3_256(data, usedforsecurity=False).digest()
    return b64encode(digest).decode().rstrip("=")


def parse_date(value: str | None) -> datetime | None:
