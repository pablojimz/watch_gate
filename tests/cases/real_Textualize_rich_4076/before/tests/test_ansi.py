
    decoder = AnsiDecoder()
    lines = list(decoder.decode(terminal_codes))

    expected = [
        Text("Hello"),
        Text("foo", spans=[Span(0, 3, Style.parse("bold"))]),
        Text("bar", spans=[Span(0, 3, Style.parse("link http://example.org"))]),
        Text("red", spans=[Span(0, 3, Style.parse("#ff0000 on color(200)"))]),
        Text("red", spans=[Span(0, 3, Style.parse("color(200) on #ff0000"))]),
    ]

    assert lines == expected
        console.print(text)
    result = capture.get()
    print(repr(result))
    expected = "\x1b[1mC:\\Users\\stefa\\AppData\\Local\\Temp\\tmp3ydingba:\x1b[0m In function '\x1b[1mmain\x1b[0m':\n\x1b[1mC:\\Users\\stefa\\AppData\\Local\\Temp\\tmp3ydingba:3:5:\x1b[0m \x1b[1;35mwarning: \x1b[0munused variable '\x1b[1ma\x1b[0m' \n[\x1b[1;35m-Wunused-variable\x1b[0m]\n    3 | int \x1b[1;35ma\x1b[0m=1;\n      |     \x1b[1;35m^\x1b[0m\n"
    assert result == expected


        # https://github.com/Textualize/rich/issues/2688
        (
            b"\x1b[31mFound 4 errors in 2 files (checked 18 source files)\x1b(B\x1b[m\n",
            "Found 4 errors in 2 files (checked 18 source files)",
        ),
        # https://mail.python.org/pipermail/python-list/2007-December/424756.html
        (b"Hallo", "Hallo"),
    expected = "x\n"

    assert capture.get() == expected
