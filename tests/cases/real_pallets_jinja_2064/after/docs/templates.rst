Block Assignments
~~~~~~~~~~~~~~~~~

It's possible to use `set` as a block to assign the content of the block to a
variable. This can be used to create multi-line strings, since Jinja doesn't
support Python's triple quotes (``"""``, ``'''``).

Instead of using an equals sign and a value, you only write the variable name,
and everything until ``{% endset %}`` is captured.

.. code-block:: jinja

    {% set navigation %}
        <li><a href="/">Index</a>
        <li><a href="/downloads">Downloads</a>
    {% endset %}

Filters applied to the variable name will be applied to the block's content.

.. code-block:: jinja

    {% set reply | wordwrap %}
        You wrote:
        {{ message }}
    {% endset %}

.. versionadded:: 2.8

.. versionchanged:: 2.10

    Block assignment supports filters.

.. _extends:

