        This implementation is shared for `if`, `while`, `for`, `try`, `except`,
        `def`, `with`, `class`, `assert`, and assignments.

        The relevant Python language `keywords` for a given statement
        appear as NAME leaves within it. This method puts those on a
        separate line.

        `parens` holds a set of string leaf values immediately after which
        invisible parens should be put.
            # these ones aren't useful to end users, but they do please fuzzers
            syms.for_stmt,
            syms.del_stmt,
        ]:
            return False

