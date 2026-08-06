        elif (
            "@" in middle
            and not middle.startswith("www.")
            # ignore values like `@a@b`
            and not middle.startswith("@")
            and ":" not in middle
            and _email_re.match(middle)
        ):
