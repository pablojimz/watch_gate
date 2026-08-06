
## Help Parameter Customization

Help parameters are automatically added by Click for any command. The default is `--help` but can be overridden by the context setting {attr}`~Context.help_option_names`. Click also performs automatic conflict resolution on the default help parameter, so if a command itself implements a parameter named `help` then the default help will not be run.

This example changes the default parameters to `-h` and `--help`
instead of just `--help`:
