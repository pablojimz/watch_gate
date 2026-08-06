Block Assignments
~~~~~~~~~~~~~~~~~

.. versionadded:: 2.8

Starting with Jinja 2.8, it's possible to also use block assignments to
capture the contents of a block into a variable name.  This can be useful
in some situations as an alternative for macros.  In that case, instead of
using an equals sign and a value, you just write the variable name and then
everything until ``{% endset %}`` is captured.

Example::

    {% set navigation %}
        <li><a href="/">Index</a>
        <li><a href="/downloads">Downloads</a>
    {% endset %}

The `navigation` variable then contains the navigation HTML source.

.. versionchanged:: 2.10

Starting with Jinja 2.10, the block assignment supports filters.

Example::

    {% set reply | wordwrap %}
        You wrote:
        {{ message }}
    {% endset %}


.. _extends:

