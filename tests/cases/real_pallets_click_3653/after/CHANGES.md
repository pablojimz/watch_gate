  Colorama is no longer a dependency and is not used. {issue}`2986` {pr}`3505`
- {class}`Argument` accepts a `help` parameter, and help output includes
  a `Positional arguments` section when argument help is available. {issue}`2983` {pr}`3473`
- `confirm()` and `prompt()` strip ANSI color and style codes from the
  prompt when the output stream does not support them, matching `echo()`.
  This stripping was lost in `8.4.0` when {pr}`2969` began writing the
  prompt with `input()` directly. {issue}`3572` {pr}`3653`
- Fix test failures when using pytest >= 9.1. {pr}`3656`

## Version 8.4.2
