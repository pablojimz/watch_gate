Alternate screen
----------------

Terminals support an 'alternate screen' mode which is separate from the regular terminal and allows for full-screen applications that leave your stream of input and commands intact. Rich supports this mode via the :meth:`~rich.console.Console.set_alt_screen` method, although it is recommended that you use :meth:`~rich.console.Console.screen` which returns a context manager that disables alternate mode on exit.

Here's an example of an alternate screen::
