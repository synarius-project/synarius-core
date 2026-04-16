..
   Contributor notes: AttributeDict / AttributeEntry

================================================================================
``AttributeDict`` / ``AttributeEntry`` — contributor notes
================================================================================

This page captures **synarius-core–specific** conventions for model attribute
entries.  It complements the monorepo-wide programming guidelines
(``programming_guidelines.rst``) and the full technical reference at
:doc:`../specifications/attribute_dict`.

--------------------------------------------------------------------------------
Frozen ``AttributeEntry``
--------------------------------------------------------------------------------

* Attribute entries **are** immutable ``@dataclass(frozen=True)`` instances.
* Updates **must** go through ``dataclasses.replace`` (or
  ``AttributeDict.set_value``) — never in-place mutation of fields, and never
  raw tuple literals.

Use the factory helpers for bypass writes:

.. code-block:: python

   dict.__setitem__(obj.attribute_dict, "key", AttributeEntry.stored(value, writable=True))
   dict.__setitem__(obj.attribute_dict, "key", AttributeEntry.virtual(getter, setter, writable=True))

--------------------------------------------------------------------------------
Virtual attributes vs ``value_spec``
--------------------------------------------------------------------------------

* If an attribute uses a **virtual setter**, that setter **is** the full write
  contract.  **Do not** add a parallel ``value_spec`` on the same entry:
  for virtual attributes, ``value_spec`` **MUST** be ``None``.
  ``AttributeEntry.__post_init__`` enforces this at construction time.
* For **stored** (non-virtual) attributes with stable shapes, prefer a
  non-``None`` ``value_spec`` callable (or document why ``None`` remains
  acceptable).

--------------------------------------------------------------------------------
Optional ``value_spec`` (stored attributes)
--------------------------------------------------------------------------------

* ``value_spec is None`` is allowed only for **polymorphic, experimental, or
  rarely constrained** keys — and must be a **conscious** choice, not the
  default for new stable attributes.
* Once a key has a boundary contract (``value_spec`` or virtual setter),
  **do not** duplicate the same shape logic in business logic.  Remove
  duplicates only under the gated process described in the technical reference
  (Phase 5: key covered by tests + CI passes).

--------------------------------------------------------------------------------
Reject vs coerce (default)
--------------------------------------------------------------------------------

* **Default:** invalid values are **rejected** at the boundary with a clear
  error naming the attribute and the expected contract.
* **Coercion** is an **exception**: allowed only when **explicitly documented**
  next to that key's spec/setter and covered by **tests** (no silent widening).

--------------------------------------------------------------------------------
Serialisation gotchas
--------------------------------------------------------------------------------

* After JSON/YAML (or similar), numbers may be ``int`` or ``float``; document
  whether a spec accepts ``1.0`` where an ``int`` is intended.
* ``bool`` is a subclass of ``int`` — ``isinstance`` checks need care.
