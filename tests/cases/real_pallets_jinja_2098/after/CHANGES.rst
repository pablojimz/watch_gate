-   Drop support for Python 3.7, 3.8, and 3.9.
-   Update minimum MarkupSafe version to >= 3.0.
-   Update minimum Babel version to >= 2.17.
-   Deprecate the ``__version__`` attribute. Use feature detection or
    ``importlib.metadata.version("jinja2")`` instead.
-   Use modern packaging metadata with ``pyproject.toml`` instead of ``setup.cfg``.
    :pr:`1793`
-   Use ``flit_core`` instead of ``setuptools`` as build backend.
