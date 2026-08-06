sandboxed environment.
"""

from __future__ import annotations

import typing as t

from .bccache import BytecodeCache as BytecodeCache
from .bccache import FileSystemBytecodeCache as FileSystemBytecodeCache
from .bccache import MemcachedBytecodeCache as MemcachedBytecodeCache
from .utils import pass_eval_context as pass_eval_context
from .utils import select_autoescape as select_autoescape


def __getattr__(name: str) -> t.Any:
    if name == "__version__":
        import importlib.metadata
        import warnings

        warnings.warn(
            "The `__version__` attribute is deprecated and will be removed in"
            " Werkzeug 3.3. Use feature detection or"
            ' `importlib.metadata.version("werkzeug")` instead.',
            DeprecationWarning,
            stacklevel=2,
        )
        return importlib.metadata.version("werkzeug")

    raise AttributeError(name)
