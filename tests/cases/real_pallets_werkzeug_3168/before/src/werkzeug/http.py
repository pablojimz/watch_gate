from urllib.parse import unquote

from ._internal import _dt_as_utc

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment
    if not value:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    if seconds < 0:
    """
    if age is None:
        return None
    if isinstance(age, timedelta):
        age = int(age.total_seconds())
    else:
        age = int(age)

    if age < 0:
        raise ValueError("age cannot be negative")
