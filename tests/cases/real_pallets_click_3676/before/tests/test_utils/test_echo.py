    out, err = capfd.readouterr()
    assert out == f"{styled_text}\n"

    isatty = True
    click.echo(styled_text)
    out, err = capfd.readouterr()
    assert out == f"{styled_text}\n"

    isatty = False
    # Faking isatty() is not enough on Windows;
    # the implementation caches the colorama wrapped stream
    # so we have to use a new stream for each test
    stream = StringIO()
    click.echo(styled_text, file=stream)
    assert stream.getvalue() == f"{text}\n"

    stream = StringIO()
    click.echo(styled_text, file=stream, color=True)
    assert stream.getvalue() == f"{styled_text}\n"


@pytest.mark.skipif(WIN, reason="Test too complex to make work windows.")
