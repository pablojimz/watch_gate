
    def close(self):
        """Cleanup and (if leave=False) close the progress bar."""
        if self.disable:
            return

        # Prevent multiple closures
        pos = abs(self.pos)
        self._decr_instances(self)

        if self.last_print_t < self.start_t + self.delay:
            # haven't ever displayed; nothing to clear
            return
