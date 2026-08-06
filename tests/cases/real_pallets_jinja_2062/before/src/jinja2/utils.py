        elif (
            "@" in middle
            and not middle.startswith("www.")
            and ":" not in middle
            and _email_re.match(middle)
        ):
