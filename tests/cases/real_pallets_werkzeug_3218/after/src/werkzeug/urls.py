
    :param uri: The URI to convert.

    .. versionchanged:: 3.1.9
        Empty username, password, and port 0 are preserved.

    .. versionchanged:: 3.0
        Passing a tuple or bytes, and the ``charset`` and ``errors`` parameters,
        are removed.
    if ":" in netloc:
        netloc = f"[{netloc}]"

    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"

    if parts.username is not None:
        auth = _unquote_user(parts.username)

        if parts.password is not None:
            password = _unquote_user(parts.password)
            auth = f"{auth}:{password}"


    :param iri: The IRI to convert.

    .. versionchanged:: 3.1.9
        Empty username, password, and port 0 are preserved.

    .. versionchanged:: 3.0
        Passing a tuple or bytes, the ``charset`` and ``errors`` parameters,
        and the ``safe_conversion`` parameter, are removed.
    if ":" in netloc:
        netloc = f"[{netloc}]"

    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"

    if parts.username is not None:
        auth = quote(parts.username, safe="%!$&'()*+,;=")

        if parts.password is not None:
            password = quote(parts.password, safe="%!$&'()*+,;=")
            auth = f"{auth}:{password}"

