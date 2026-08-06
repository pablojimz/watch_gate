-   Use SHA3-256 instead of SHA-1 for generating ETags and the debugger pin.
    SHA-1 is not available FIPS 140. This may invalidate some caches since the
    ETag will be different. :pr:`3164`
-   ``generate_password_hash`` uses ``secrets.token_urlsafe`` to generate salt.
    The private ``gen_salt`` method is removed. :pr:`3167`


Version 3.1.8
