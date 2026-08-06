import typing as t
from pstats import Stats

try:
    from cProfile import Profile
except ImportError:
    from profile import Profile  # type: ignore

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
