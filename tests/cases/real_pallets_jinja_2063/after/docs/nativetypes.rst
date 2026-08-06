>>> print(result.value)
15

Sandboxed Native Environment
----------------------------

You can combine :class:`.SandboxedEnvironment` and :class:`NativeEnvironment` to
get both behaviors.

.. code-block:: python

    class SandboxedNativeEnvironment(SandboxedEnvironment, NativeEnvironment):
        pass

API
---

