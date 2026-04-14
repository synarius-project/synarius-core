..
   Hierarchical attribute paths — get/set + CCP

================================================================================
Hierarchical attribute paths (dict-valued attributes)
================================================================================

:Status: Draft (synarius-core)
:Scope: ``BaseObject.get`` / ``BaseObject.set``, ``AttributeDict``, and CCP commands ``get`` / ``set`` / ``lsattr``

--------------------------------------------------------------------------------
Purpose
--------------------------------------------------------------------------------

Some attributes store **JSON-like mapping trees** (``dict``) while remaining a single logical field in ``AttributeDict`` (for example the pin map under ``pin``).

Hosts **SHALL** support **hierarchical path strings** so users can address leaf values without replacing entire dicts on every edit.

--------------------------------------------------------------------------------
Path syntax
--------------------------------------------------------------------------------

* Segments are separated by unescaped ``.`` (dot).
* Escape sequences:
  * ``\\.`` → literal dot
  * ``\\\\`` → literal backslash

Helpers:

* ``synarius_core.model.attribute_path.split_attribute_path``
* ``synarius_core.model.attribute_path.join_attribute_path``

--------------------------------------------------------------------------------
Semantics on ``BaseObject``
--------------------------------------------------------------------------------

For a path ``p`` split into segments ``s0, s1, …, sn``:

* If ``n == 0``: reject (empty path).
* If ``n == 1``: identical to direct ``AttributeDict`` access.
* If ``n >= 2``:
  * ``get(p)`` traverses ``get(s0)`` which **must** be a ``dict``, then walks ``s1…sn-1``, then returns the leaf ``sn``.
  * ``set(p, v)`` performs a **deep copy** of the mapping stored at ``s0``, writes the leaf, then replaces the stored mapping via ``set_value(s0, new_mapping)``.

Writability for hierarchical updates is determined by the **root** key ``s0`` using ``AttributeDict.allows_structural_value_replace`` (writable entries, or virtual entries that route through a setter).

--------------------------------------------------------------------------------
Errors
--------------------------------------------------------------------------------

* Missing segment: ``KeyError``
* Traversal through a non-mapping: ``TypeError``
* Root not structurally replaceable: ``PermissionError``

--------------------------------------------------------------------------------
CCP mapping
--------------------------------------------------------------------------------

The controller parses ``<objectRef>.<attr.path>`` as:

* ``objectRef =`` first path segment (as resolved by the existing reference/path rules)
* ``attr.path =`` remaining segments joined with ``.``

This implies **object references must not rely on unescaped dots** in the reference token; dots after the first segment belong to the attribute path.

**Exception (normative, ``new``):** The ``new`` command is **not** subject to this split for its first argument. The token immediately following ``new`` is the **type designator** (for example ``FmuInstance`` or ``std.FmuCoSimulation``) and **MAY** contain ``.`` as part of a single argument; it does **not** introduce an attribute path. Only ``get`` / ``set`` / ``lsattr`` (and similar reference-based forms) use ``<objectRef>.<attr.path>`` as specified above.

--------------------------------------------------------------------------------
``lsattr`` flattening
--------------------------------------------------------------------------------

For each top-level attribute whose stored value is a non-virtual ``dict``, ``lsattr`` **SHALL** list **flattened** rows:

* ``<root>.< nested…>.<leaf>``

Long-mode meta columns (``VIRTUAL``/``EXPOSED``/``WRITABLE``) **SHALL** be taken from the **root** key’s metadata.

Grouped output **MAY** insert a blank line when the top-level group (first segment of the flattened key) changes.
