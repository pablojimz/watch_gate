        runner.invoke(cli, [])


def test_argument_sharing_param_name_warning(runner):
    """An argument sharing its storage name with an option makes both
    silently overwrite each other's value, which triggers a warning.
    """

    @click.command()
    @click.option("--foo", "target")
    @click.argument("target")
    def cli(target):
        click.echo(target, nl=False)

    with pytest.warns(UserWarning, match="'target' is used by an argument"):
        result = runner.invoke(cli, ["--foo", "from_option", "from_argument"])

    # The value parsed by the option is lost to the argument's.
    assert result.output == "from_argument"
    assert result.exit_code == 0


def test_options_sharing_name_no_warning(runner):
    """Options deliberately sharing a storage name (feature switches) are
    exempt from the duplicate-name warning. Warnings are errors in this
    suite, so a clean run proves none fired.
    """

    @click.command()
    @click.option("--upper", "transformation", flag_value="upper")
    @click.option("--lower", "transformation", flag_value="lower")
    def cli(transformation):
        click.echo(transformation, nl=False)

    result = runner.invoke(cli, ["--upper"])
    assert result.output == "upper"
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("args", "expected"),
    [
