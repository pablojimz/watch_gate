            return False

        prefix = get_string_prefix(node.value)
        if set(prefix).intersection("bBfF"):
            return False

    if (
