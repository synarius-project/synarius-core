..
   Technical reference: AttributeDict / AttributeEntry

================================================================================
``AttributeDict`` / ``AttributeEntry`` — technical reference
================================================================================

:Scope: ``synarius_core.model.attribute_dict``, ``BaseObject.get`` / ``BaseObject.set``,
        all writers of attribute entries, CLI/CCP value ingestion, persistence load paths

--------------------------------------------------------------------------------
Overview
--------------------------------------------------------------------------------

``AttributeDict`` is the per-object attribute store for all model elements.
It extends ``dict[str, AttributeEntry]`` and adds access-control metadata,
virtual getter/setter routing, and an optional per-key boundary contract
(``value_spec``).

Each slot is an immutable :class:`AttributeEntry` frozen dataclass instead of
the legacy opaque 5-tuple.  Updates go through ``dataclasses.replace``, not
in-place mutation.

--------------------------------------------------------------------------------
``AttributeEntry`` — frozen dataclass
--------------------------------------------------------------------------------

.. code-block:: python

   @dataclasses.dataclass(frozen=True)
   class AttributeEntry:
       value: Any = None
       setter: SetterFunction | None = None
       getter: GetterFunction | None = None
       exposed: bool = True
       writable: bool = False
       value_spec: Callable[[Any], Any] | None = None

**Fields**

.. list-table::
   :widths: 22 78
   :header-rows: 1

   * - Field
     - Meaning
   * - ``value``
     - Stored value for non-virtual attributes; ``None`` and ignored when the
       entry is virtual (``getter`` is not ``None``).
   * - ``setter`` / ``getter``
     - Callable contracts for virtual attributes; ``None`` for stored entries.
   * - ``exposed``
     - Whether the attribute appears in the public protocol surface
       (``lsattr``, CCP introspection).  Default: ``True``.
   * - ``writable``
     - Whether :meth:`~AttributeDict.set_value` (or ``BaseObject.set``) may
       overwrite this attribute.  Default: ``False``.
   * - ``value_spec``
     - Optional callable ``(Any) -> Any`` that **validates and returns** the
       canonical stored value at the write boundary.  See :ref:`value_spec`.

**Immutability note:** ``value`` may still reference mutable objects (``dict``,
``list``).  Freezing the dataclass does *not* deep-freeze values.  The existing
copy-on-write rules for hierarchical ``set`` (see :doc:`attribute_path_semantics`)
remain in effect.

**Invariant enforced by** ``__post_init__``:

* ``value_spec`` **MUST** be ``None`` whenever ``setter`` is not ``None``.
  Attempting to construct an ``AttributeEntry`` with both set raises
  ``ValueError``.  The setter is the write contract for virtual attributes;
  a parallel ``value_spec`` would create an ambiguous double-gate.

**Factory helpers**

.. code-block:: python

   # Stored (non-virtual) entry:
   AttributeEntry.stored(value, *, exposed=True, writable=False, value_spec=None)

   # Virtual entry backed by getter / setter:
   AttributeEntry.virtual(getter, setter=None, *, exposed=True, writable=False)

Both helpers enforce the ``setter`` / ``value_spec`` invariant at construction
time via ``__post_init__``.

--------------------------------------------------------------------------------
``AttributeDict`` — API
--------------------------------------------------------------------------------

``AttributeDict`` inherits ``dict[str, AttributeEntry]``.  All reads and writes
should go through the methods below rather than the raw ``dict`` API.

.. list-table::
   :widths: 38 62
   :header-rows: 1

   * - Method
     - Behaviour
   * - ``__setitem__(key, value)``
     - Stores *value* as ``AttributeEntry.stored(value)`` — exposed,
       non-writable.  Use for simple ``"type"`` / protocol key writes.
   * - ``set_virtual(key, getter, setter, *, exposed, writable)``
     - Registers a virtual entry via ``AttributeEntry.virtual``.
   * - ``__getitem__(key)``
     - Returns the logical value: calls ``getter()`` if virtual, otherwise
       returns ``entry.value``.
   * - ``set_value(key, value)``
     - Canonical write path — see below.
   * - ``stored_value(key)``
     - Same as ``__getitem__`` but intent is explicit (reads logical value).
   * - ``exposed(key)`` / ``writable(key)`` / ``virtual(key)``
     - Metadata accessors.
   * - ``allows_structural_value_replace(key)``
     - ``True`` if the slot is writable *or* has a virtual setter (used by
       ``BaseObject._root_is_writable_for_nested_update``).

**``set_value`` — write boundary**

.. code-block:: text

   set_value(key, value):
     1. Raises PermissionError if entry.writable is False.
     2. Virtual path (setter is not None):
        → calls setter(value); returns.
        → value_spec is NOT run (setter is the contract).
     3. Stored path:
        → runs value_spec(value) if value_spec is not None;
          propagates TypeError / ValueError on rejection.
        → persists via dataclasses.replace(entry, value=canonical_value).

.. _value_spec:

--------------------------------------------------------------------------------
``value_spec`` — boundary contracts
--------------------------------------------------------------------------------

A ``value_spec`` is a single callable ``(Any) -> Any`` that validates *and
returns* the canonical stored value.  It is called by ``set_value`` on the
non-virtual path before the new value is committed.

**Three forms in practice:**

1. ``None`` — no automatic check (legacy / polymorphic / experimental keys).
2. A dedicated callable — validates shape and returns canonical form.
3. A shared helper — small registered functions (e.g. "non-empty list of
   floats") in one module, to avoid copy-paste across keys.

**Default policy:** reject invalid input with a clear ``TypeError`` /
``ValueError`` that names the attribute and the expected contract.

**Coercion** (e.g. scalar → one-element list, string → bool) is an
*exception*: it must be explicitly documented next to the spec and covered by
tests.  Undocumented widening is forbidden.

``value_spec is None`` is allowed for polymorphic, experimental, or rarely
constrained keys — it must be a conscious, documented choice (see
:doc:`../developer/attribute_dict_contributor_notes`).

**Serialisation pitfalls**

* ``bool`` is a subclass of ``int`` — ``isinstance`` checks need care.
* After JSON/YAML (or similar) loads, integers may arrive as ``float``
  (e.g. ``1.0`` instead of ``1``).  Specs that require strict ``int`` should
  document whether ``float`` with integer value is accepted or rejected.

--------------------------------------------------------------------------------
Bypass writes — rules
--------------------------------------------------------------------------------

Some construction paths need to set full metadata (``exposed``, ``writable``,
``value_spec``) that ``AttributeDict.__setitem__`` does not expose.  These use
``dict.__setitem__`` to bypass the wrapper:

.. code-block:: python

   # Correct — use factory helpers:
   dict.__setitem__(obj.attribute_dict, "key", AttributeEntry.stored(value, writable=True))
   dict.__setitem__(obj.attribute_dict, "key", AttributeEntry.virtual(getter, setter, writable=True))

   # Wrong — raw tuples are legacy; do not introduce new ones:
   dict.__setitem__(obj.attribute_dict, "key", (value, None, None, True, True))  # ← forbidden

The adapter function ``_as_entry`` (module-private) normalises legacy 5-tuples
to ``AttributeEntry`` on every read path inside ``AttributeDict``.  It exists
as a migration safety net; no new code should produce raw tuples.

--------------------------------------------------------------------------------
Related documents
--------------------------------------------------------------------------------

* :doc:`attribute_path_semantics` — hierarchical paths on dict-backed attributes.
* :doc:`core_type_system` — model element typing at the ``type`` string level.
* :doc:`../developer/attribute_dict_contributor_notes` — contributor rules and
  conventions.
