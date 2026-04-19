..
   Synarius — attr_config_demo example script.

``attr_config_demo.py`` — Configuration Demo Script
====================================================

:Source: :download:`attr_config_demo.py <attr_config_demo.py>`

This script demonstrates both forms of attribute configuration
(:doc:`../concept` Section 8):

**Local configuration** — opens an ``AttribTableWidget`` in a ``QDialog``,
lets the user edit exposed attributes of a demo object, and prints the
resulting CCP ``set`` command on *OK*.

**Global configuration** — opens an ``OptionsMenuWidget`` tree dialog
grouping all attributes with ``OptionMeta.global_=True`` by their
``global_path``, and persists the confirmed changes to a temporary
``settings.toml``.

**Persistence round-trip** — writes a delta to ``settings.toml``,
reloads it merged with ``defaults.toml``, and verifies correctness.
Runs without a display (no Qt required for this part).

.. literalinclude:: attr_config_demo.py
   :language: python
   :linenos:
