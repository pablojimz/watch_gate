   pytest_foo/plugin.py
   pytest_foo/helper.py

With the following typical ``pyproject.toml`` extract:

.. code-block:: toml

   [project.entry-points.pytest11]
   foo = "pytest_foo.plugin"

In this case only ``pytest_foo/plugin.py`` will be rewritten.  If the
helper module also contains assert statements which need to be
