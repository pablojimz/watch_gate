```{versionadded} 2.0
```

The {func}`echo` function supports ANSI colors and styles.

Primarily this means that:

- Click's {func}`echo` function will automatically strip ANSI color codes if the stream is not connected to a terminal.
- the {func}`echo` function will transparently connect to the terminal on Windows and translate ANSI codes to terminal
  API calls. This means that colors will work on Windows the same way they do on other operating systems.

:::{admonition} Older Windows Support
:class: note
