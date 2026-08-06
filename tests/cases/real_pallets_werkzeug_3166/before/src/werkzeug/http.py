import re
import typing as t
import warnings
from datetime import date
from datetime import datetime
from datetime import time
    """Generate a strong ETag value by hashing the given data.

    .. versionchanged:: 3.2
        Use SHA3-256. SHA-1 is not allowed in FIPS-enabled systems. This
        increases the length from 40 to 64 characters.

    .. versionchanged:: 2.0
        Use SHA-1. MD5 is not allowed in FIPS-enabled systems. This increases
        the length from 32 to 40 characters.
    """
    return hashlib.sha3_256(data, usedforsecurity=False).hexdigest()


def parse_date(value: str | None) -> datetime | None:
