F = t.TypeVar("F", bound="t.Callable[..., t.Any]")
V = t.TypeVar("V")

# Reserved storage name of the automatic help option. No user parameter is
# expected to claim it.
_HELP_OPTION_STORAGE_NAME = "_click_default_help"


def _complete_visible_commands(
    ctx: Context, incomplete: str
                    stacklevel=3,
                )

            # Options may deliberately share a storage name to compete for
            # the same value (feature switches), but an argument sharing a
            # name silently overwrites the other parameter's value.
            names_counter = Counter(param.name for param in params)
            duplicate_names = (
                name for name, count in names_counter.items() if count > 1
            )

            for duplicate_name in duplicate_names:
                sharers = [param for param in params if param.name == duplicate_name]

                if help_option in sharers:
                    warnings.warn(
                        (
                            f"The name {duplicate_name!r} is reserved for the "
                            "automatic help option. Give the parameter a "
                            "different name."
                        ),
                        stacklevel=3,
                    )
                elif any(isinstance(param, Argument) for param in sharers):
                    warnings.warn(
                        (
                            f"The name {duplicate_name!r} is used by an argument "
                            "and another parameter. They will overwrite each "
                            "other's value during parsing. Give each parameter "
                            "a unique name."
                        ),
                        stacklevel=3,
                    )

        return params

    def format_usage(self, ctx: Context, formatter: HelpFormatter) -> None:

        Skipped if :attr:`add_help_option` is ``False``.

        .. versionchanged:: 8.5.0
            The help option stores its value under the reserved name
            ``_click_default_help``, so a parameter named ``help`` no
            longer breaks parsing.

        .. versionchanged:: 8.1.8
            The help option is now cached to avoid creating it multiple times.
        """
            # Avoid circular import.
            from .decorators import help_option

            # The help option never exposes its value, so it uses a reserved
            # storage name, keeping it clear of user parameters (like an
            # argument named "help") that would otherwise clobber its value.
            help_option(*help_option_names, _HELP_OPTION_STORAGE_NAME)(self)
            self._help_option = self.params.pop()  # type: ignore[assignment]

        return self._help_option
