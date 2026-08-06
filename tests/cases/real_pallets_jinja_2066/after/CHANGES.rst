Version 3.1.5
-------------

Released 2024-12-21

-   The sandboxed environment handles indirect calls to ``str.format``, such as
    by passing a stored reference to a filter that calls its argument.
