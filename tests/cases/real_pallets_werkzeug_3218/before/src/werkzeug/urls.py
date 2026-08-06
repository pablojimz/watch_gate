
    :param uri: The URI to convert.

    .. versionchanged:: 3.0
        Passing a tuple or bytes, and the ``charset`` and ``errors`` parameters,
        are removed.
    if ":" in netloc:
        netloc = f"[{netloc}]"

    if parts.port:
        netloc = f"{netloc}:{parts.port}"

    if parts.username:
        auth = _unquote_user(parts.username)

        if parts.password:
            password = _unquote_user(parts.password)
            auth = f"{auth}:{password}"


    :param iri: The IRI to convert.

    .. versionchanged:: 3.0
        Passing a tuple or bytes, the ``charset`` and ``errors`` parameters,
        and the ``safe_conversion`` parameter, are removed.
    if ":" in netloc:
        netloc = f"[{netloc}]"

    if parts.port:
        netloc = f"{netloc}:{parts.port}"

    if parts.username:
        auth = quote(parts.username, safe="%!$&'()*+,;=")

        if parts.password:
            password = quote(parts.password, safe="%!$&'()*+,;=")
            auth = f"{auth}:{password}"

