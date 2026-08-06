from __future__ import annotations

import email.utils
import hashlib
import re
import typing as t
import warnings
from datetime import timedelta
from datetime import timezone
from enum import Enum
from time import mktime
from time import struct_time
from urllib.parse import quote


def generate_etag(data: bytes) -> str:
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
                            account.
    :return: `True` if the resource was modified, otherwise `False`.

    .. versionchanged:: 1.0
        The check is run for methods other than ``GET`` and ``HEAD``.
    """
    return _sansio_http.is_resource_modified(
