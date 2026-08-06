    deprecated. The header has not been used for a long time. :pr:`3158`
-   The ``pragma`` header property on ``Request`` is deprecated. The header has
    been officially deprecated for a long time. :pr:`3160`
-   The ``accept_charsets`` header property on ``Request``, and the
    ``CharsetAccept`` class, are deprecated. The header has not been used for a
    long time. :pr:`3161`
-   ``redirect`` returns a ``303`` status code by default instead of ``302``.
    This tells the client to always switch to ``GET``, rather than only
    switching ``POST`` to ``GET``. This preserves the current behavior of
