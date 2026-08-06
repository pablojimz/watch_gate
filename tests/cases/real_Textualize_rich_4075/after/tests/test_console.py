    assert console.file.getvalue() == "foo\n"


def test_print_empty_with_end() -> None:
    console = Console(file=io.StringIO(), color_system="truecolor")
    console.print(end="!")
    assert console.file.getvalue() == "!"


def test_print_multiple() -> None:
    console = Console(file=io.StringIO(), color_system="truecolor")
    console.print("foo", "bar")
