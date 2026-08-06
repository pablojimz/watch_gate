    assert console.file.getvalue() == "foo\n"


def test_print_multiple() -> None:
    console = Console(file=io.StringIO(), color_system="truecolor")
    console.print("foo", "bar")
