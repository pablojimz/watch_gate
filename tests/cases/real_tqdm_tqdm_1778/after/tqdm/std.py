
    def close(self):
        """Cleanup and (if leave=False) close the progress bar."""
        if getattr(self, 'disable', True):
            return

        # Prevent multiple closures
        pos = abs(self.pos)
        self._decr_instances(self)

        if not hasattr(self, 'last_print_t'):
            return
        if self.last_print_t < self.start_t + self.delay:
            # haven't ever displayed; nothing to clear
            return
