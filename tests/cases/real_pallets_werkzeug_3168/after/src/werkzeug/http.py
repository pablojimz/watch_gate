from urllib.parse import unquote

from ._internal import _dt_as_utc
from ._internal import _plain_int

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment
    if not value:
        return None
    try:
        seconds = _plain_int(value)
    except ValueError:
        return None
    if seconds < 0:
    """
    if age is None:
        return None

    if isinstance(age, timedelta):
        age = int(age.total_seconds())

    if age < 0:
        raise ValueError("age cannot be negative")
