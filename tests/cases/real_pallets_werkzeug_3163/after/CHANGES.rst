-   The development server does not send an extra ``100 Continue`` response, as
    Python's base server already sends it. :issue:`3138`
-   The float URL converter does not produce scientific notation. :issue:`3146`
-   ``Request.if_range`` discards the header if it is an invalid weak ETag.
    :pr:`3163`


Version 3.1.8
