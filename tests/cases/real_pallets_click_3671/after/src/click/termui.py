

def _readline_prompt(func: t.Callable[[str], str], text: str, err: bool) -> str:
    """Call a prompt function, passing the full prompt so readline can
    handle line editing and cursor positioning correctly.

    The prompt is handed to *func* (such as :func:`input`) rather than
    written through :func:`echo`, so it has to strip ANSI color and style
