    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("help_names", "params", "args", "expected_output"),
    [
        (["--help"], [], [], "\n"),
        (["--help"], [click.Argument(["help"])], ["value"], "value\n"),
        (
            ["--help"],
            [click.Option(["--assist", "help"])],
            ["--assist", "value"],
            "value\n",
        ),
        (["--man"], [click.Option(["--foo", "man"])], ["--foo", "value"], "value\n"),
    ],
    ids=["no-collision", "argument", "option", "custom-flags"],
)
def test_param_named_help(runner, help_names, params, args, expected_output):
    """User parameters never clash with the automatic help option, which
    stores its value under the reserved ``_click_default_help`` name.

    https://github.com/pallets/click/issues/2819
    """
    cli = click.Command(
        "cli",
        context_settings={"help_option_names": help_names},
        params=params,
        callback=lambda **kwargs: click.echo(next(iter(kwargs.values()), None)),
    )

    ctx = click.Context(cli, help_option_names=help_names)
    help_option = cli.get_help_option(ctx)
    assert help_option is not None
    assert help_option.name == "_click_default_help"

    result = runner.invoke(cli, args)
    assert result.output == expected_output
    assert result.exit_code == 0

    result = runner.invoke(cli, [help_names[0]])
    assert "Show this message and exit." in result.output
    assert result.exit_code == 0


def test_param_squatting_help_option_name(runner):
    """Claiming the reserved storage name of the automatic help option
    triggers a warning.
    """

    @click.command()
    @click.argument("_click_default_help")
    def cli(_click_default_help):
        click.echo(_click_default_help)

    with pytest.warns(UserWarning, match="reserved for the automatic help option"):
        result = runner.invoke(cli, ["value"])

    # The collision still breaks parsing, but no longer silently.
    assert result.exit_code == 2


def test_option_reusing_help_flag(runner):
    """An option reusing the ``--help`` flag replaces the automatic help
    option entirely.

    https://github.com/pallets/click/issues/2819
    """

    @click.command()
    @click.option("--help", default="default value")
    def cli(help):
        click.echo(help)

    assert cli.get_help_option(click.Context(cli)) is None

    result = runner.invoke(cli, [])
    assert result.output == "default value\n"
    assert result.exit_code == 0

    result = runner.invoke(cli, ["--help", "custom"])
    assert result.output == "custom\n"
    assert result.exit_code == 0


def test_repr():
    @click.command()
    def command():
