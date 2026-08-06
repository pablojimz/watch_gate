            return False

        prefix = get_string_prefix(node.value)
        # Bytes, f-strings and t-strings never evaluate to str, so they are not
        # docstrings even in docstring position.
        if set(prefix).intersection("bBfFtT"):
            return False

    if (
