
        .. versionadded:: 0.7
        """
        self._got_first_request = True

        try:
            if "werkzeug.debug.preserve_context" in environ:
                environ["werkzeug.debug.preserve_context"](ctx)

            if error is not None and self.should_ignore_error(error):
                error = None

            ctx.pop(error)
