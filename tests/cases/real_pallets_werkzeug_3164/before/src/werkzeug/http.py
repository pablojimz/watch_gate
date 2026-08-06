from __future__ import annotations

import email.utils
import re
import typing as t
import warnings
from datetime import timedelta
from datetime import timezone
from enum import Enum
from hashlib import sha1
from time import mktime
from time import struct_time
from urllib.parse import quote


def generate_etag(data: bytes) -> str:
    """Generate an etag for some data.

    .. versionchanged:: 2.0
        Use SHA-1. MD5 may not be available in some environments.
    """
    return sha1(data).hexdigest()


def parse_date(value: str | None) -> datetime | None:
                            account.
    :return: `True` if the resource was modified, otherwise `False`.

    .. versionchanged:: 2.0
        SHA-1 is used to generate an etag value for the data. MD5 may
        not be available in some environments.

    .. versionchanged:: 1.0.0
        The check is run for methods other than ``GET`` and ``HEAD``.
    """
    return _sansio_http.is_resource_modified(
