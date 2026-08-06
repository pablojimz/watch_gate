    ETag will be different. :pr:`3164`
-   ``generate_password_hash`` uses ``secrets.token_urlsafe`` to generate salt.
    The private ``gen_salt`` method is removed. :pr:`3167`


Version 3.1.9
