-   The float URL converter does not produce scientific notation. :issue:`3146`
-   ``Request.if_range`` discards the header if it is an invalid weak ETag.
    :pr:`3163`
-   Use SHA3-256 instead of SHA-1 for generating ETags and the debugger pin.
    SHA-1 is not available FIPS 140. This may invalidate some caches since the
    ETag will be different. :pr:`3164`


Version 3.1.8
