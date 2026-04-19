..
   Synarius — Attribute Configuration and Options Management — Technical Reference.

================================================================================
Attribute Configuration and Options Management — Technical Reference
================================================================================

:Status: Technical Reference
:Scope: synarius-core model layer; synarius_attr_config module; GUI application layer

.. admonition:: Architectural Principle

   Every piece of information in the configuration system has exactly one
   canonical source.  All other accesses are projections onto that source.
   This principle is non-negotiable and applies at every layer.

--------------------------------------------------------------------------------
1. Overview
--------------------------------------------------------------------------------

Model objects in Synarius carry attributes stored in ``AttributeDict``.  A
subset of these attributes constitutes *user-facing configuration*: values that
the user inspects and changes through GUI dialogs rather than through direct
scripting via the Controller Command Protocol (**CCP**).

The infrastructure is delivered in the ``synarius_attr_config`` package, which
depends on ``synarius_core`` and can be consumed by any GUI application.  The
package provides ``OptionMeta``, ``GuiHint``, the widget classes,
``RegistryOverlayStore``, and ``TomlPersistenceLayer``.

.. rubric:: Definition: attribute system

The term **attribute system** denotes the combined structure of
``AttributeEntry`` (in ``synarius_core``) together with its associated
``OptionMeta`` and ``GuiHint`` objects (in ``synarius_attr_config``).  All
three objects are required to fully describe a configurable attribute; no part
of that description resides in external configuration files at definition time.
When this document states that a property is defined "exclusively in the
attribute system", it means in the combination of these three code-defined
objects.  ``synarius_core`` has no dependency on ``OptionMeta`` or ``GuiHint``;
the extension is purely additive and does not modify the core model contract.

The system provides:

* A **unified attribute model** in which semantic metadata (bounds, units,
  enumerations), configuration role, and GUI hints are first-class, code-
  defined, type-checked properties — not external configuration files.
* Two **projections** of the same underlying attribute model: local per-object
  configuration and global application configuration.
* **Virtual attributes** as a uniform access layer over structured metadata.
* **CCP-based** change transmission and **TOML-based** persistence integrated
  with the unified model.

All structural and semantic properties of configuration options are defined
exclusively in the attribute system.  The Registry (Section 5) provides only
optional, non-structural overlays.

--------------------------------------------------------------------------------
2. Repository Boundary
--------------------------------------------------------------------------------

The Synarius repository boundary rule (*simulation logic in synarius-core;
Studio and Apps handle UI and integration only*) applies unchanged:

.. list-table::
   :widths: 32 34 34
   :header-rows: 1

   * - Belongs in **synarius-core**
     - Belongs in **synarius_attr_config**
     - Belongs in **consuming GUI application**
   * - ``AttributeEntry`` — base attribute storage and validation
     - ``OptionMeta`` — configuration role, scope, structural placement
     - Application-specific ``OptionMeta`` / ``GuiHint`` registrations
   * - Semantic metadata: numeric bounds, physical unit, enumeration,
       docstring
     - ``GuiHint`` — display name, widget-type hints, editor behaviour
     - Application stylesheet / colour palette
   * - ``value_spec`` — normative value validation
     - ``RegistryOverlayStore`` — i18n and user-preference overlays
     - ``ConfigController`` — app-specific controller wiring
   * - Schema-migration log messages
     - ``AttribViewModel``, ``AttribTableWidget``, ``OptionsMenuWidget``
     - TOML file locations (``platformdirs`` paths)

The defining test: if information is needed to *validate or simulate
correctly*, it belongs in core.  If it describes *presentation or
configuration structure*, it belongs in ``synarius_attr_config``.
Application-specific wiring stays in the consuming application.

--------------------------------------------------------------------------------
3. Unified Attribute Model
--------------------------------------------------------------------------------

**3.1 ``AttributeEntry`` — base and single semantic source**

``AttributeEntry`` is the canonical storage unit for a model attribute.  It
carries the value, its ``value_spec`` validator, the ``exposed`` and
``writable`` flags, and the *semantic* metadata:

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Field
     - Type
     - Meaning
   * - ``value``
     - ``Any``
     - Stored value for non-virtual attributes.
   * - ``setter`` / ``getter``
     - callable | ``None``
     - Virtual attribute contracts.  ``None`` for stored attributes.
   * - ``exposed``
     - ``bool``
     - Visible via CCP introspection (``lsattr``).  Default: ``True``.
   * - ``writable``
     - ``bool``
     - May be written via ``set_value``.  Default: ``False``.
   * - ``value_spec``
     - callable | ``None``
     - Validates and coerces incoming values at the write boundary (stored
       path only; mutually exclusive with ``setter``).
   * - ``bounds``
     - ``tuple[float, float]`` | ``None``
     - Inclusive numeric range ``(lo, hi)`` used by validation and the
       slider widget.
   * - ``unit``
     - ``str``
     - Physical unit string displayed in the unit column (e.g. ``"m/s"``).
   * - ``enum_values``
     - ``list[str]`` | ``None``
     - Ordered enumeration members; drives widget-type inference.
   * - ``docstring``
     - ``str``
     - Human-readable description shown in ``lsattr -r`` output.

Semantic metadata fields constrain *what values are valid* — a core-model
concern that applies equally in headless and GUI contexts.  No other object
may redefine or override semantic metadata.

**3.2 ``OptionMeta`` — configuration role and structural placement**

``OptionMeta`` is a dataclass (``synarius_attr_config.meta``) attached to an
``AttributeEntry`` by the attribute definition.  Its exclusive responsibility
is to describe *how the attribute participates in the configuration system*:

.. list-table::
   :widths: 28 15 57
   :header-rows: 1

   * - Field
     - Type
     - Meaning
   * - ``global_``
     - ``bool``
     - Participates in the global options dialog.  Default: ``False``.
   * - ``global_path``
     - ``str``
     - Forward-slash path for the options-menu tree (e.g.
       ``"Simulation/Solver"``).  Depth = number of components.
   * - ``local``
     - ``bool``
     - Participates in per-object local dialogs.  Default: ``True``.
   * - ``order``
     - ``int`` | ``None``
     - Sort key within the group; lower = earlier.  ``None`` = alphabetical.
   * - ``exposed_override``
     - ``bool`` | ``None``
     - GUI-only visibility override; does not modify ``AttributeEntry.exposed``.
   * - ``gui_writable_override``
     - ``bool`` | ``None``
     - GUI-only writability override.

``OptionMeta`` must not contain any display or editor details — those belong
exclusively in ``GuiHint``.  The roles of ``OptionMeta`` and ``GuiHint`` are
strictly disjoint.

**3.3 ``GuiHint`` — display and editor hints**

``GuiHint`` is a dataclass (``synarius_attr_config.meta``) that describes *how
the attribute value is presented and edited*:

.. list-table::
   :widths: 28 15 57
   :header-rows: 1

   * - Field
     - Type
     - Meaning
   * - ``display_name``
     - ``str``
     - English row label; the sole string the i18n registry may translate.
   * - ``widget_type_override``
     - ``str`` | ``None``
     - Force a specific widget, bypassing automatic inference.  See
       Section 8.1 for valid values.
   * - ``decimal_precision``
     - ``int`` | ``None``
     - Preferred decimal places for spin-box widgets.

``GuiHint`` is never consulted for any decision outside the rendering
pipeline.  In particular it must not influence whether an attribute is
globally configurable, where it appears in the options-menu tree, whether it
is stored or persisted, or which values are semantically valid.

**3.4 Relationship between the three objects**

.. code-block:: text

   AttributeEntry   ←── semantic metadata (bounds, unit, enum_values, docstring)
                        canonical value + validation (value_spec)
         │
         │  referenced by (synarius_attr_config; core has no dependency on either)
         ▼
   OptionMeta       ──── configuration role, scope, global_path, order,
         │               exposed_override, gui_writable_override
         │  associated with (synarius_attr_config)
         ▼
   GuiHint          ──── display_name, widget_type_override, decimal_precision

``OptionMeta`` and ``GuiHint`` reference an ``AttributeEntry`` by key; the
core model has no dependency on either.  Although implemented as separate
objects, they are conceptually part of the ``AttributeEntry`` definition —
they possess no independent model identity and are not addressable outside the
context of their ``AttributeEntry``.

--------------------------------------------------------------------------------
4. Two Categories of Mutable State
--------------------------------------------------------------------------------

.. important::

   Local object configuration produces **domain-model mutations**: they change
   simulation state, are recorded in the project file (``.syn``), and are
   **undoable** via the undo stack.  Global application configuration produces
   **user-preference changes**: they configure the tool rather than the
   simulation, have no effect on computational correctness, and are
   deliberately **not undoable**.

   This categorical distinction is the primary reason local and global
   configuration have separate write paths, separate controllers, and separate
   persistence mechanisms.  The fact that both categories use shared GUI
   components (``AttribViewModel``, ``AttribTableWidget``) is an
   implementation convenience — not a conceptual identity.  Any design that
   treats the two write paths as equivalent is an architectural violation.

--------------------------------------------------------------------------------
5. The Registry — Optional Non-Structural Overlay Only
--------------------------------------------------------------------------------

.. important::

   The Registry must not define or modify any structural property of the
   attribute system.  All canonical structural properties are defined
   exclusively in ``OptionMeta`` and ``AttributeEntry``.

The registry is an optional, non-structural overlay managed by
``RegistryOverlayStore`` (``synarius_attr_config.projection``).

**``RegistryOverlayStore`` responsibilities:**

* **Loading** — reads a TOML registry file at application startup (Section 5.1).
* **Overlay application** — merges registry overrides (i18n, user preferences)
  on top of ``GuiHint.display_name`` values at query time.
* **Validation** — checks all registry keys against the known set of
  ``(obj_type, attr_key)`` pairs; emits a WARNING for each orphan entry.
* **Error handling** — logs at WARNING level for missing files, parse errors,
  and schema mismatches; never raises exceptions.

The registry may hold only:

1. **Internationalised display names** — translations of
   ``GuiHint.display_name`` keyed by BCP 47 language tag.
2. **User-preferred alternative labels** — optional label overrides.

The registry is explicitly **not permitted** to determine whether an attribute
is globally configurable, where it appears in the options-menu tree, or
whether it is visible or editable.

The absence of a registry entry is never an error — ``GuiHint.display_name``
is the English fallback.

**5.1 TOML registry format**

Each section key is ``"ObjType.attr_key"`` (or bare ``"attr_key"`` for
type-independent overrides).  Sub-keys are BCP 47 language tags::

    ["SolverBlock.gain"]
    en = "Gain Factor"
    de = "Verstärkungsfaktor"

    ["SolverBlock.enabled"]
    en = "Solver Enabled"

Lookup order: qualified key → bare key → ``GuiHint.display_name``.

**5.2 I18n infrastructure**

Language tags follow BCP 47; strings are Unicode / UTF-8.  Physical storage
uses TOML with BCP 47 sub-keys.  No translated strings are required in v1.

--------------------------------------------------------------------------------
6. Virtual Attributes as a Projection Mechanism
--------------------------------------------------------------------------------

Virtual attributes expose metadata stored in ``OptionMeta`` and ``GuiHint``
through the standard ``AttributeDict`` accessor interface without creating a
second physical storage representation.

The following rules are normative:

1. **Not stored, not persisted.**  A virtual attribute is never written to the
   ``.syn`` file, to ``settings.toml``, or to the registry.  Persistence is
   always and exclusively the responsibility of the canonical source object.

2. **Read-only by default.**  Writability must be declared explicitly.

3. **Writes delegate directly; no second source, no persistence.**  A write
   delegates immediately to the backing ``OptionMeta`` or ``GuiHint`` object.
   The backing object remains the sole owner; the virtual attribute neither
   stores the value nor schedules any persistence action.

4. **No own identity.**  Virtual attributes do not appear in ``.syn``
   serialisation, do not participate in undo history, and must not be used to
   reconstruct the state of the metadata objects that back them.

5. **View, not copy.**  A read returns the current state of the backing object
   at access time.

6. **Uniform access layer.**  Virtual attributes allow ``lsattr``, the widget
   factory, and other tooling to traverse the full attribute surface through
   one API.

7. **Visible virtualness.**  ``AttributeDict.virtual(key)`` returns ``True``
   for virtual entries.  ``lsattr`` output marks them with ``[virtual]``.

8. **GUI writability mirrors declared writability.**  If declared writable
   (``AttributeEntry.writable = True``), the GUI renders an editable widget.
   ``OptionMeta.gui_writable_override`` can suppress or enable GUI editability
   independently.  Read-only virtual attributes always render as display-only.

--------------------------------------------------------------------------------
7. Plugin Integration
--------------------------------------------------------------------------------

Plugins introduce new configurable attributes entirely through code, without
any registry entries or configuration files.

A plugin defines ``AttributeEntry`` + ``OptionMeta`` + ``GuiHint`` for each
new attribute.  No further registration is required for full integration into
local and global configuration dialogs.  GUI generation, CCP integration,
TOML persistence, and ``lsattr`` output follow automatically from the
attribute system — the plugin requires no custom dialog or persistence code.

This is a direct consequence of the single-source-of-truth principle: because
all structural information lives in code objects, a plugin that provides those
objects is immediately and fully integrated.

--------------------------------------------------------------------------------
8. Two Projections of the Attribute Model
--------------------------------------------------------------------------------

Local object configuration and global application configuration are two
**projection criteria** applied to the same attribute model — not two separate
definition systems.

All structural and semantic properties of configuration options are defined
exclusively in the attribute system.  Local and global dialogs are views
produced by filtering that system.

**8.1 Local object configuration**

*Projection criterion*: ``AttributeEntry.exposed`` is ``True`` (or overridden
by ``OptionMeta.exposed_override``).

* Scope: one object instance.
* Persistence: bulk CCP ``set`` command through ``SynariusController``;
  written to the ``.syn`` file; **undoable**.
* Dialog invocation: double-click on a canvas element.  Exception: Kennlinien
  and Kennfelder blocks have dedicated editors and are excluded.

**8.2 Global application configuration**

*Projection criterion*: ``OptionMeta.global_`` is ``True``, collected across
all registered configurable objects and structured by ``OptionMeta.global_path``.

* Scope: all participating objects across the application.
* Persistence: ``ConfigController`` writes to ``settings.toml``;
  **not undoable**; effective on next application start.

**8.3 Shared foundations**

Both projections share, without duplication:

* ``AttributeEntry`` semantic metadata (bounds, unit, enum_values, docstring).
* Widget type inference (Section 9).
* ``AttribViewModel`` / ``AttribTableWidget`` / ``AttribFormWidget``.
* Validation and error-feedback pattern (Section 12).
* Ordering rules (Section 11).

--------------------------------------------------------------------------------
9. Widget Type Inference
--------------------------------------------------------------------------------

**9.1 Inference algorithm**

The function ``synarius_attr_config.widgets.infer_widget_type(entry, hint)``
selects a widget type using the following precedence.  Each condition is
tested in order; the first match wins:

.. list-table::
   :widths: 5 40 20 35
   :header-rows: 1

   * - #
     - Condition
     - Widget type
     - Notes
   * - 1
     - ``hint.widget_type_override is not None``
     - *(override value)*
     - Bypasses all automatic inference.
   * - 2
     - ``entry.enum_values is not None`` and ``len ≤ 3``
     - ``"radio"``
     - Radio buttons, vertical layout.
   * - 3
     - ``entry.enum_values is not None`` and ``len > 3``
     - ``"combobox"``
     - ``QComboBox``.
   * - 4
     - ``isinstance(value, bool)``
     - ``"checkbox"``
     - **Must precede rule 5**; ``bool ⊂ int`` in Python.
   * - 5
     - ``isinstance(value, (int, float))`` and ``bounds is not None``
     - ``"slider+spinbox"``
     - ``QDoubleSpinBox`` + ``QSlider`` (bounds-driven range).
   * - 6
     - ``isinstance(value, (int, float))``
     - ``"spinbox"``
     - ``QDoubleSpinBox`` with unlimited range.
   * - 7
     - ``isinstance(value, pathlib.Path)``
     - ``"path_picker"``
     - ``QLineEdit`` + ``QFileDialog`` button.
   * - 8
     - ``isinstance(value, (datetime.date, datetime.datetime))``
     - ``"datepicker"``
     - ``QDateEdit``.
   * - 9
     - *(fallback)*
     - ``"lineedit"``
     - ``QLineEdit``.

Valid ``widget_type_override`` values: ``"checkbox"``, ``"combobox"``,
``"radio"``, ``"spinbox"``, ``"slider+spinbox"``, ``"color_picker"``,
``"path_picker"``, ``"datepicker"``, ``"lineedit"``.

**9.2 ``AttribViewModel``**

``AttribViewModel`` (``synarius_attr_config.projection``) holds the projected
attribute set for one dialog scope.  It tracks original values, pending values,
and validation state per attribute.  Validation logic, change detection, and
bulk-set generation reside exclusively here — not in view classes.

Key methods:

* ``set_pending(key, value)`` — record a pending edit.
* ``changed_values() → dict[str, Any]`` — keys whose pending value differs
  from the original.
* ``validate(key) → ValidationResult`` — runs bounds, enum, and value_spec
  checks on the pending value.
* ``has_errors() → bool`` — True if any key fails validation.
* ``reset_to_default(key)`` — set pending to defaults.toml value; remove key
  from settings.toml via the persistence layer.
* ``reset_group(keys)`` — batch reset; only keys with defaults.toml entries
  are affected.
* ``display_name(key)`` — registry overlay → GuiHint.display_name → key.
* ``effective_exposed(key)`` / ``effective_writable(key)`` — respects
  ``OptionMeta`` overrides.

**9.3 ``AttribTableWidget`` and ``AttribFormWidget``**

``AttribTableWidget`` (``synarius_attr_config.widgets``) renders an
``AttribViewModel`` as a ``QTableWidget`` with three columns:
*display name* | *value widget* | *unit*.

``AttribFormWidget`` (``synarius_attr_config.widgets``) provides the same
three-column layout using ``QGridLayout`` — preferred in embedded panels.

Both widgets provide a **right-click context menu** on each row.  For
attributes that have a default value in ``defaults.toml``, the menu offers
*Reset to default*.

**9.4 ``OptionsMenuWidget``**

``OptionsMenuWidget`` (``synarius_attr_config.widgets``) is used for the
global configuration dialog:

* Left pane: ``QTreeWidget`` built from the ``global_path`` tree in
  ``OptionMeta``.
* Right pane: ``QScrollArea`` containing one ``AttribTableWidget`` per
  tree leaf node.

Path-depth semantics (depth of ``OptionMeta.global_path``):

* Depth 1: attribute in the top-level tree node.
* Depth 2: attribute under a sub-node.
* Depth 3+: additional subtree branches.

**Reset operations in ``OptionsMenuWidget``:**

*Per-attribute reset* — right-click on a row; calls
``AttribViewModel.reset_to_default(key)``.

*Per-group reset* — context menu of an ``AttribTableWidget`` panel.  A
confirmation dialog lists each affected attribute with its current override
value and the default it will revert to.  Calls
``AttribViewModel.reset_group(keys)``.

*Global reset* — toolbar action.  A warning dialog states that all
user-specific global configuration will be lost.  Calls
``TomlPersistenceLayer.reset_all()``.

--------------------------------------------------------------------------------
10. CCP Integration
--------------------------------------------------------------------------------

**10.1 Local object configuration — Bulk-Set command**

On dialog *OK*, ``AttribViewModel.changed_values()`` returns a dict of changed
attributes.  The dialog emits one CCP command:

.. code-block:: text

   set <object_hash_name> {attr1: value1, attr2: value2, ...}

This travels through ``SynariusController`` and is **undoable**.  Only changed
attributes are included.

**10.2 ConfigController**

``ConfigController`` is not a variant or subclass of ``SynariusController``.
It is a dedicated command interface for user-preference attributes only.

Relationship to ``SynariusController``:

* **Shared syntax** — accepts the same CCP ``set``, ``get``, and ``lsattr``
  command text format.
* **Shared console surface** — the same console widget dispatches to either
  controller based on the active CCP context.

The following are explicitly **not shared**:

.. list-table::
   :widths: 50 50
   :header-rows: 1

   * - ``SynariusController``
     - ``ConfigController``
   * - Undo stack
     - No undo stack
   * - Simulation model graph as model root
     - Global-config ``AttributeDict`` as model root
   * - Project and file context
     - No project context
   * - Commands affect simulation state
     - Commands affect user preferences only
   * - Changes written to ``.syn`` on project save
     - Changes written to ``settings.toml`` on OK

The console must never route a ``set`` command intended for a model attribute
to ``ConfigController``, nor a settings command to ``SynariusController``.
Routing is determined by the active CCP context object.

**10.3 CCP context — optional object argument**

Where a CCP command is issued within an established *object context*, the
``<object_hash_name>`` argument may be omitted:

.. code-block:: text

   # With explicit object:
   set my_block.gain 2.0

   # With implicit context object (same effect when context = my_block):
   set gain 2.0

See :doc:`../controller_command_protocol` for context establishment syntax.

--------------------------------------------------------------------------------
11. Ordering and Grouping
--------------------------------------------------------------------------------

**Default:** alphabetical by ``GuiHint.display_name`` at every level (tree
nodes, section headings, attribute rows).

**Override:** ``OptionMeta.order`` (integer) opts out of alphabetical ordering
at the attribute's own level.  Lower numbers sort first.  Items without an
explicit order sort alphabetically after all ordered items.

The same rules apply to both projections.

--------------------------------------------------------------------------------
12. Validation and Error Feedback
--------------------------------------------------------------------------------

All validation errors — from ``value_spec``, ``bounds``, or
``enum_values`` — are handled uniformly:

* **On input change**: immediate visual feedback (red border, inline message).
* **On OK**: *OK* button disabled until all errors are resolved; no values are
  committed while any error is active.
* **On Cancel**: all pending changes discarded; no CCP command emitted.

Validation runs in ``AttribViewModel.validate(key)``.  Order: bounds check →
enum membership check → ``value_spec`` call.

``bool`` values bypass the numeric bounds check (``bool`` is a subclass of
``int`` in Python; a boolean attribute should not carry numeric bounds).

--------------------------------------------------------------------------------
13. TOML Persistence for Global Configuration
--------------------------------------------------------------------------------

.. note::

   This section applies exclusively to **global application configuration**
   (attributes where ``OptionMeta.global_`` is ``True``).  Local object
   configuration is persisted via the ``.syn`` project format.

**13.1 Two-file approach**

``defaults.toml``
    Ships with the application.  All supported keys with their default values.
    Read-only at runtime; schema reference and reset target.
    Loaded once at first access; cached for the process lifetime.

``settings.toml``
    User-specific overrides only (keys that differ from defaults).
    Written on *OK* in the global config dialog.  Located at
    ``platformdirs.user_config_dir("synarius") / "settings.toml"``.

At startup both files are merged; ``settings.toml`` overrides individual keys.
Settings are effective on the **next application start**.

**13.2 Delta semantics invariant**

``settings.toml`` stores only override keys.  An absent key **always** means
"use the default".  A present key **always** means "user override".  Reset
operations remove keys — they never write the default value into
``settings.toml``.  This invariant must not be broken.

**13.3 Reading and writing**

* Reading: ``tomllib`` (Python 3.11+ stdlib).
* Writing: ``tomli-w`` (``synarius_attr_config`` optional dependency).
* Only non-virtual attributes that differ from their default are written.

**13.4 Schema migration**

Unknown keys in ``settings.toml`` are ignored and logged at WARNING level.

**13.5 Reset operations**

*Single-attribute reset* — removes the key from ``settings.toml``.

*Group reset* — removes all keys in the group from ``settings.toml`` in one
write operation.

*Global reset* — deletes ``settings.toml`` entirely.  Effective on next start.

--------------------------------------------------------------------------------
14. ``lsattr`` Command Extensions
--------------------------------------------------------------------------------

``lsattr -r <object>``
    Lists attribute keys with their ``OptionMeta`` and ``GuiHint`` fields.
    Virtual attributes are listed with a ``[virtual]`` marker.  Attributes
    with no associated ``OptionMeta`` / ``GuiHint`` are annotated
    ``(no option metadata)``.

``lsattr -ra <object>``
    Combined view showing model-side fields (value, bounds, unit,
    ``enum_values``, docstring, exposed, writable) and metadata-side fields
    (``display_name``, ``global_``, ``global_path``, ``order``) side by side.

Both flags work on domain objects (``SynariusController``) and config objects
(``ConfigController``).  The ``<object>`` argument may be omitted when a
CCP context object is active (Section 10.3).

--------------------------------------------------------------------------------
15. Limitations (v1)
--------------------------------------------------------------------------------

* **"Requires restart" flag** — not modelled.
* **Per-project configuration** — architecture accommodates a third TOML layer;
  not implemented.
* **Internationalisation** — infrastructure conventions established in
  Section 5; no translated strings in v1.
* **``ConfigController`` console layout** — single or separate console tab;
  deferred to the UI sprint.
* **Config export / import profiles** — not in scope.
* **Color picker widget** — specified in ``widget_type_override`` values but
  not yet implemented in ``AttribTableWidget``; use ``lineedit`` as interim.

--------------------------------------------------------------------------------
16. Related Documents
--------------------------------------------------------------------------------

* :doc:`../attribute_dict` — ``AttributeDict`` / ``AttributeEntry`` reference.
* :doc:`../controller_command_protocol` — CCP ``set`` command semantics.
* :doc:`../attribute_path_semantics` — hierarchical attribute paths.
* :doc:`../../developer/programming_guidelines` — repository boundary rules.
* :doc:`architecture` — package structure, class inventory, and data-flow diagrams.
* :doc:`implementation_plan` — phased work sequence and example script.
