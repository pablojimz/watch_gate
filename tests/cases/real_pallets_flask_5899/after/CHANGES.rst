    If subclasses were overriding these methods, the old signature is detected,
    shows a deprecation warning, and will continue to work during the
    deprecation period. :issue:`5815`
-   The ``should_ignore_error`` is deprecated. Handle errors as needed in
    teardown handlers instead. :issue:`5816`
-   ``template_filter``, ``template_test``, and ``template_global`` decorators
    can be used without parentheses. :issue:`5729`
-   ``redirect`` returns a ``303`` status code by default instead of ``302``.
