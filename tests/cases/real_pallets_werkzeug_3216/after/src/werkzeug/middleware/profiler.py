import typing as t
from pstats import Stats

if sys.version_info >= (3, 15):
    from profiling.tracing import Profile
else:
    try:
        from cProfile import Profile
    except ImportError:
        from profile import Profile  # type: ignore[assignment]

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
