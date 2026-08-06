    assert file.getvalue() == "-\n"
    file_proxy.flush()
    assert file.getvalue() == "-\n-\n"


def test_isatty():
    """Check isatty is proxied

    Regression test for https://github.com/Textualize/rich/issues/4041

    """

    class TTYFile:
        def isatty(self) -> bool:
            return True

    file = TTYFile()
    console = Console()
    file_proxy = FileProxy(console, file)
    assert file_proxy.isatty()
