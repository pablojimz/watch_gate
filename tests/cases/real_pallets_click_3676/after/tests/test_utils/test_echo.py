    out, err = capfd.readouterr()
    assert out == f"{styled_text}\n"

    click.echo(styled_text)
    out, err = capfd.readouterr()
    assert out == f"{styled_text}\n"

    isatty = False
    click.echo(styled_text)
    out, err = capfd.readouterr()
    assert out == f"{text}\n"

    click.echo(styled_text, color=True)
    out, err = capfd.readouterr()
    assert out == f"{styled_text}\n"


@pytest.mark.skipif(WIN, reason="Test too complex to make work windows.")
