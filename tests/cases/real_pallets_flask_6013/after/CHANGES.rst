    such as HTMX. :issue:`5895`
-   ``provide_automatic_options=True`` can be used to enable it for a view when
    it's disabled in config. Previously, only disabling worked. :issue:`5916`
-   ``Flask.select_jinja_autoescape`` uses case-insensitive comparison instead
    of only lower case file extensions. :pr:`6012`


Version 3.1.3
