
## Help Parameter Customization

Help parameters are automatically added by Click for any command. The default is `--help` but can be overridden by the context setting {attr}`~Context.help_option_names`. Click resolves conflicts automatically: an option reusing one of the help option names takes it over, and the default help parameter is dropped once all its names are taken. A parameter merely named `help`, like `click.argument("help")`, does not disable it: both keep working independently.

This example changes the default parameters to `-h` and `--help`
instead of just `--help`:
