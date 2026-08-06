            except (TypeError, AttributeError):
                total = None
        if total == float("inf"):
            total = None  # same as unknown

        if disable:
            self.iterable = iterable
        """
        self.n = 0
        if total is not None:
            self.total = None if total == float("inf") else total
        if self.disable:
            return
        self.last_print_n = 0
