    def render(self, task):
        """Calculate common unit for completed and total."""
        completed = int(task.completed)
        # total is None when the iterable has no length (e.g. a generator)
        total = int(task.total) if task.total is not None else None
        base = total if total is not None else completed
        if self.unit_scale:
            unit, suffix = filesize.pick_unit_and_suffix(
                base,
                ["", "K", "M", "G", "T", "P", "E", "Z", "Y"],
                self.unit_divisor,
            )
        else:
            unit, suffix = filesize.pick_unit_and_suffix(base, [""], 1)
        precision = 0 if unit == 1 else 1
        total_str = f"{total/unit:,.{precision}f}" if total is not None else "?"
        return Text(
            f"{completed/unit:,.{precision}f}/{total_str} {suffix}",
            style="progress.download")


        pass

    def display(self, *_, **__):
        if not hasattr(self, '_task_id'):
            return
        self._prog.update(self._task_id, completed=self.n, description=self.desc)

