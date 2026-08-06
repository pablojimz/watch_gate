
    decoder = AnsiDecoder()
    lines = list(decoder.decode(terminal_codes))
    print(repr(lines))
    expected = [
        Text("Hello"),
        Text("foo", spans=[Span(0, 3, Style.parse("bold"))]),
        Text("bar", spans=[Span(0, 3, Style.parse("link http://example.org"))]),
        Text("red", spans=[Span(0, 3, Style.parse("#ff0000 on color(200)"))]),
        Text("red", spans=[Span(0, 3, Style.parse("color(200) on #ff0000"))]),
        Text(""),
    ]

    assert lines == expected
        console.print(text)
    result = capture.get()
    print(repr(result))
    print(result)
    expected = "\x1b[1mC:\\Users\\stefa\\AppData\\Local\\Temp\\tmp3ydingba:\x1b[0m In function '\x1b[1mmain\x1b[0m':\n\x1b[1mC:\\Users\\stefa\\AppData\\Local\\Temp\\tmp3ydingba:3:5:\x1b[0m \x1b[1;35mwarning: \x1b[0munused variable '\x1b[1ma\x1b[0m' \n[\x1b[1;35m-Wunused-variable\x1b[0m]\n    3 | int \x1b[1;35ma\x1b[0m=1;\n      |     \x1b[1;35m^\x1b[0m\n\n"
    assert result == expected


        # https://github.com/Textualize/rich/issues/2688
        (
            b"\x1b[31mFound 4 errors in 2 files (checked 18 source files)\x1b(B\x1b[m\n",
            "Found 4 errors in 2 files (checked 18 source files)\n",
        ),
        # https://mail.python.org/pipermail/python-list/2007-December/424756.html
        (b"Hallo", "Hallo"),
    expected = "x\n"

    assert capture.get() == expected


def test_decode_newlines():
    """Test newlines are preserved.
    Regression test for https://github.com/Textualize/rich/issues/3577
    """
    assert Text.from_ansi("").plain == ""
    assert Text.from_ansi("\n").plain == "\n"
    assert Text.from_ansi("\n\n").plain == "\n\n"
    assert Text.from_ansi("Hello").plain == "Hello"
    assert Text.from_ansi("\nHello").plain == "\nHello"
    assert Text.from_ansi("Hello\n").plain == "Hello\n"
    assert Text.from_ansi("Hello\n\n").plain == "Hello\n\n"
    assert Text.from_ansi("Hello\nWorld").plain == "Hello\nWorld"
    assert Text.from_ansi("Hello\n\nWorld").plain == "Hello\n\nWorld"
    assert Text.from_ansi("Hello\nWorld\n").plain == "Hello\nWorld\n"
    assert Text.from_ansi("Hello\nWorld\n\n").plain == "Hello\nWorld\n\n"
    assert Text.from_ansi("\nHello\nWorld\n\n").plain == "\nHello\nWorld\n\n"
