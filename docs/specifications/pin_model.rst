..
   Unified Pin model (pin map in AttributeDict)

================================================================================
Pin model (``pin`` namespace)
================================================================================

:Status: Draft (synarius-core)
:Scope: ``ElementaryInstance`` and subclasses (variables, operators, and generic / library elementary blocks including FMU-oriented ``MODEL.ELEMENTARY`` instances)

--------------------------------------------------------------------------------
Storage
--------------------------------------------------------------------------------

Diagram pins **SHALL** be stored in ``BaseObject.attribute_dict`` under the reserved top-level key **``pin``**:

* ``get("pin")`` → ``dict[str, dict[str, Any]]`` (pin name → pin record)
* ``get("pin.<name>")`` → pin record mapping
* ``get("pin.<name>.<field>)`` → scalar / leaf value

``pin`` is a normal dict-valued attribute and **SHALL** be manipulated using hierarchical paths (see ``attribute_path_semantics.rst``).

--------------------------------------------------------------------------------
Required pin record fields
--------------------------------------------------------------------------------

Each pin record **SHALL** contain at least:

* ``direction``: ``"IN"`` or ``"OUT"`` (explicit; no separate in/out containers)
* ``data_type``: string discriminator (e.g. ``"float"``)

Optional layout:

* ``y``: ``float | None`` pin-local vertical placement hint in model space. ``None`` means *auto placement* (host decides).

--------------------------------------------------------------------------------
Python compatibility helpers
--------------------------------------------------------------------------------

``ElementaryInstance`` exposes derived read-only views:

* ``in_pins`` / ``out_pins`` → ``list[Pin]`` reconstructed from the ``pin`` map (sorted by name)

These lists exist for engine/diagram code that still wants ``Pin`` objects.

--------------------------------------------------------------------------------
FMU ports
--------------------------------------------------------------------------------

An FMU scalar variable **SHALL** become one entry in ``pin`` keyed by its variable name.

The record **SHALL** satisfy the general pin requirements and **MAY** include additional fields (e.g. ``value_reference``, ``causality``, ``variability``, ``start_override``, …).

FMU imports that use Constructor keyword ``fmu_ports=[...]`` **SHALL** be interpreted as a **convenience input** that populates ``pin`` (there is no separate persisted ``fmu_ports`` attribute).

--------------------------------------------------------------------------------
Naming
--------------------------------------------------------------------------------

Pin names are validated with ``validate_pin_name``:

* Must be valid identifier segments
* Python keywords **ARE** allowed (diagram pins use ``in``, ``out``, …)
