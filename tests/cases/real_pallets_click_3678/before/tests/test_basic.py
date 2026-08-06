    assert result.exit_code == 0


def test_repr():
    @click.command()
    def command():
