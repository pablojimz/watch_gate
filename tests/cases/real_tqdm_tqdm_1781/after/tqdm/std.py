        """

        # sanity check: total
        if total and (n >= (total + 0.5) or total == float("inf")):
            # allow float imprecision (#849) or inf (#651)
            total = None

        # apply custom scale if necessary
