        if not conn:
            # Try again
            log.warning(
                "Retrying (%r) after connection broken by '%r': %s",
                retries,
                err,
                url,
                # Provide an unique attribute with the host needed by pip to
                # rewrite this warning. Ideally, we'd go with a better solution,
                # but backwards compatibility and other constraints make those
                # unfeasible, so this is the least bad option.
                # See also: https://github.com/urllib3/urllib3/issues/2580.
                extra={"__urllib3-retry-warning": {"host": self.host}},
            )
            return self.urlopen(
                method,
