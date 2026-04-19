:orphan:

..
   This file is superseded by attribute_config/concept.rst.
   Kept only to avoid broken links from external references.
   Synarius — Attribute Configuration and Options Management, implementation concept v0.6.

================================================================================
Attribute Configuration and Options Management — Implementation Concept
================================================================================

:Status: Implementation Concept
:Version: 0.6
:Scope: synarius-core model layer; options management module; GUI application layer

.. admonition:: Architectural Principle

   Every piece of information in the configuration system has exactly one
   canonical source.  All other accesses are projections onto that source.
   This principle is non-negotiable and applies at every layer.

--------------------------------------------------------------------------------
1. Overview and Motivation
--------------------------------------------------------------------------------

Model objects in Synarius carry attributes stored in ``AttributeDict``.  A
subset of these attributes constitutes *user-facing configuration*: values that
the user actively inspects and changes through GUI dialogs rather than through
direct scripting via the Controller Command Protocol (hereafter **CCP**).

The infrastructure described in this document is delivered as a **standalone
Python module** (the *options management module*) that depends on
``synarius-core`` and can be consumed by any GUI application — not exclusively
by Synarius Studio.  The module provides ``OptionMeta``, ``GuiHint``, the
widget classes, the ``RegistryOverlayStore``, and the TOML persistence layer.

This document defines:

* How the attribute model carries full configuration metadata — both semantic
  (validation, units, enumeration) and structural (configuration role, GUI
  hints) — as first-class citizens with a single canonical source each.
* How local per-object configuration and global app-wide configuration arise
  as two **projections** of the same underlying attribute model.
* How virtual attributes provide a uniform access layer over structured
  metadata without creating a second physical representation.
* How CCP-based change transmission and TOML-based persistence integrate with
  this unified model.

All structural and semantic properties of configuration options are defined
exclusively in the attribute system.  The Registry (Section 5) provides only
optional, non-structural overlays.

**Version history**

* v0.1 — Initial concept.
* v0.2 — Flat metadata fields on ``AttributeEntry``; Studio Registry in TOML;
  ``StudioConfigController`` Variant C; GUI class hierarchy.
* v0.3 — Architectural revision: ``OptionMeta`` and ``GuiHint`` as structured
  metadata objects; Registry demoted to optional overlay; virtual attributes
  introduced as projection mechanism.
* v0.4 — Precision revision: write semantics of virtual attributes finalised;
  OptionMeta / GuiHint role separation made explicit with prohibitions; Registry
  overlay rule formalised; Plugin Integration section added; architectural
  principle made explicit.
* v0.5 — Finalisation: ``exposed_override`` clarified as pure GUI-projection
  with no semantic effect; ``GuiHint`` exclusions made explicit; ``OptionMeta``
  and ``GuiHint`` declared as conceptual parts of ``AttributeEntry`` with no
  independent model identity; virtual-attribute persistence rule sharpened;
  registry overlay data path disambiguated from virtual-attribute write path.
* v0.6 — Review integration: standalone options-management module introduced;
  Studio-exclusive scope generalised; ``RegistryOverlayStore`` class specified;
  TOML persistence scope clarified (global config only); reset-to-default
  mechanism (per attribute, per group, global) added; writable virtual
  attributes exposed in GUI (Section 6, rule 8); ``StudioConfigController``
  label "Variant C" removed; CCP context command (object omission) added;
  ``lsattr`` context note added.

--------------------------------------------------------------------------------
2. Why the Registry-Centric Approach Was Insufficient
--------------------------------------------------------------------------------

Version 0.2 delegated structural metadata (display names, grouping,
global-path, ordering) to a separate TOML-based Studio Registry.  This created
five architectural problems that v0.3 and v0.4 address:

**Dual metadata ownership.**
The same conceptual attribute was described in two places — the Python model
definition and a TOML registry file.  Neither alone was sufficient.

**No single source of truth.**
Structural decisions resided in a text file; no type system could verify
consistency between the file and the code.

**Synchronisation and drift risk.**
Adding, renaming, or removing an attribute required updating both the code and
the TOML file.  Orphan registry entries accumulated silently.

**Reduced plugin capability.**
A plugin contributing new configurable attributes had to ship and register a
separate TOML fragment alongside its code.

**Conflation of canonical model and optional overlay.**
The registry acted as a *structural definition* mechanism, not as an
*overlay* — conflating two roles that must be separated.

   **The complete structural definition of a configurable attribute lives in
   the attribute model itself, not in an external registry.**

--------------------------------------------------------------------------------
3. Repository Boundary
--------------------------------------------------------------------------------

The Synarius repository boundary rule (*simulation logic in synarius-core;
Studio and Apps handle UI and integration only*) applies unchanged:

.. list-table::
   :widths: 32 34 34
   :header-rows: 1

   * - Belongs in **synarius-core**
     - Belongs in **options management module**
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

The defining test is unchanged: if information is needed to *validate or
simulate correctly*, it belongs in core.  If it describes *presentation
or configuration structure*, it belongs in the options management module.
Application-specific wiring stays in the consuming application.

--------------------------------------------------------------------------------
4. Unified Attribute Model
--------------------------------------------------------------------------------

**4.1 ``AttributeEntry`` — base and single semantic source**

``AttributeEntry`` is the canonical storage unit for a model attribute.  It
carries the value, its ``value_spec`` validator, the ``exposed`` and
``writable`` flags, and the *semantic* metadata (numeric bounds, physical unit,
enumeration member list, docstring).

Semantic metadata fields belong here because they constrain *what values are
valid* — a core-model concern that applies equally in headless and GUI contexts.
No other object is permitted to redefine or override semantic metadata.

**4.2 ``OptionMeta`` — configuration role and structural placement**

``OptionMeta`` is a structured Studio-side metadata object attached to an
``AttributeEntry`` by reference.  Its exclusive responsibility is to describe
*how the attribute participates in the configuration system*:

* Whether the attribute participates in the **global** configuration dialog,
  and if so, at which position in the options-menu tree (``global_path``).
* Whether the attribute participates in **local** per-object dialogs.
* Its **sort order** within its group (default: alphabetical by display name).
* An optional **exposition override** (``exposed_override``) that adjusts the
  visibility of the attribute *in the GUI projection only*.
  ``exposed_override`` is a pure rendering instruction: it does not modify
  ``AttributeEntry.exposed``, has no effect outside dialog rendering, and
  carries no semantic meaning for validation or simulation.
  The underlying ``AttributeEntry.exposed`` value is never altered by
  ``exposed_override``.

``OptionMeta`` is defined in code alongside the attribute definition.

.. important::

   ``OptionMeta`` must not contain any UI-specific display details (labels,
   widget preferences, formatting).  Those belong exclusively in ``GuiHint``.
   The roles of ``OptionMeta`` and ``GuiHint`` are strictly disjoint.
   ``OptionMeta`` describes *where* and *whether* an attribute participates in
   the configuration system; it does not describe *how* it looks.

**4.3 ``GuiHint`` — display and editor hints**

``GuiHint`` is a structured Studio-side metadata object that describes *how the
attribute value is presented and edited*:

* The English **display name** shown as a row label (the sole string the
  optional i18n registry may translate).
* An optional **widget-type override** (the inference rules in Section 8 are
  the default).
* Additional editor details — e.g. preferred decimal precision, colour-picker
  flag — that do not belong in the model contract.

``GuiHint`` is defined in code.  It describes presentation and interaction
only.  ``GuiHint`` is not consulted for any decision outside the rendering
context.

.. important::

   ``GuiHint`` is exclusively a description of presentation and editor
   behaviour.  It must not influence and is never consulted for:

   * whether an attribute is globally configurable
     (canonical source: ``OptionMeta``);
   * where an attribute appears in the options-menu tree
     (canonical source: ``OptionMeta.global_path``);
   * whether an attribute is stored or persisted
     (canonical source: ``AttributeEntry`` stored/virtual flag);
   * which values are semantically valid for the attribute
     (canonical source: ``AttributeEntry.value_spec`` and ``bounds``).

   Any appearance of ``GuiHint`` data outside the rendering pipeline is
   an architectural violation.

**4.4 Relationship between the three objects**

.. code-block:: text

   AttributeEntry   ←── semantic metadata (bounds, unit, enum_values, docstring)
                        canonical value + validation
         │
         │  referenced by (options management module; core has no dependency on either)
         ▼
   OptionMeta       ──── configuration role, scope, global_path, order,
         │               exposed_override, gui_writable_override
         │  associated with (options management module)
         ▼
   GuiHint          ──── display_name, widget_type_override, editor details

Arrow direction is intentional.  ``OptionMeta`` and ``GuiHint`` reference an
``AttributeEntry`` by key; the core model has no dependency on either.
``AttributeEntry`` does not know about ``OptionMeta`` or ``GuiHint``.

Although ``OptionMeta`` and ``GuiHint`` are implemented as separate objects,
they are **conceptually part of the ``AttributeEntry`` definition** to which
they are attached.  They possess no independent model identity: they are not
addressable as standalone entities, are not enumerable outside the context of
their ``AttributeEntry``, and carry no information that can exist or be
interpreted independently of an ``AttributeEntry``.

--------------------------------------------------------------------------------
5. The Registry — Optional Non-Structural Overlay Only
--------------------------------------------------------------------------------

.. important::

   The Registry must not define or modify any structural property of the
   attribute system.  All canonical structural properties — whether an attribute
   is globally configurable, where it appears in the menu, whether it is exposed
   or editable — are defined exclusively in ``OptionMeta`` and ``AttributeEntry``.

The Registry is retained solely as an optional, non-structural overlay.  Its
responsibilities are encapsulated in a dedicated **``RegistryOverlayStore``**
class provided by the options management module.

**``RegistryOverlayStore`` responsibilities:**

* **Loading** — reads registry TOML file(s) at application startup.
* **Overlay application** — merges registry overrides (i18n, user preferences)
  on top of the canonical ``GuiHint.display_name`` values at query time.
* **Validation** — checks all registry keys against the known set of
  ``(object_type, attribute_key)`` pairs after loading; produces a WARNING for
  each orphan entry.
* **Warnings** — emits structured log warnings for schema mismatches, missing
  files, and parse errors; never raises exceptions that crash the application.

The ``RegistryOverlayStore`` is permitted to hold only:

1. **Internationalised display names** — translations of
   ``GuiHint.display_name`` keyed by BCP 47 language tag.
2. **Optional UI overlays** — e.g. a user-preferred alternative label.
3. **User-specific preferences** — e.g. a user-chosen sort order for one
   attribute in one dialog.  These preferences are managed by dedicated
   settings UI or direct TOML editing; they are **never set via virtual
   attribute write operations**.

The ``RegistryOverlayStore`` is explicitly **not permitted** to:

* Determine whether an attribute is globally configurable
  (canonical source: ``OptionMeta``).
* Determine where an attribute appears in the options-menu tree
  (canonical source: ``OptionMeta.global_path``).
* Determine whether an attribute is visible or editable
  (canonical source: ``AttributeEntry.exposed`` / ``AttributeEntry.writable``,
  adjustable for GUI via ``OptionMeta.exposed_override``).

**Consistency rule**: the absence of a registry entry for an attribute is never
an error — ``GuiHint.display_name`` is the English fallback.

**I18n infrastructure**: language tags follow BCP 47, strings are Unicode /
UTF-8, plural forms use ICU MessageFormat, physical storage uses gettext PO/MO
or TOML with BCP 47 sub-keys.  No i18n work is required in v1.

--------------------------------------------------------------------------------
6. Virtual Attributes as a Projection Mechanism
--------------------------------------------------------------------------------

Virtual attributes expose metadata stored in ``OptionMeta`` and ``GuiHint``
through the standard ``AttributeDict`` accessor interface, without creating a
second physical storage representation.

The following rules govern virtual attributes in this context:

1. **Not stored, not persisted.**  A virtual attribute backed by ``OptionMeta``
   or ``GuiHint`` is never written to the ``.syn`` file, to
   ``settings.toml``, or to the Registry.  Virtual attributes possess no own
   persistence logic of any kind — they neither trigger nor participate in any
   persistence path.  Persistence is always and exclusively the responsibility
   of the canonical source object, managed through that object's own mechanism.

2. **Read-only by default.**  The default writability of a virtual attribute is
   read-only.  Writability must be declared explicitly and documented.

3. **Writes delegate directly; no second source, no persistence.**  Where a
   virtual attribute is declared writable, a write operation delegates
   *immediately and directly* to the backing ``OptionMeta`` or ``GuiHint``
   object.  A write to a virtual attribute must never create a second
   in-memory or on-disk copy of the value.  The backing object remains the
   sole owner after the write.  The virtual attribute itself neither stores
   the written value nor schedules any persistence action as a side effect of
   the write.

4. **No own identity.**  Virtual attributes have no independent identity in the
   model.  They do not appear in the ``.syn`` serialisation, do not participate
   in undo history, and must not be used to reconstruct or infer the state of
   the metadata objects that back them.

5. **View, not copy.**  Accessing a virtual attribute does not transfer
   ownership.  The virtual attribute is a *view* onto the canonical source.
   Reads return the current state of the backing object at access time.

6. **Uniform access layer.**  Virtual attributes allow ``lsattr`` (Section 11),
   the widget factory (Section 8), and other tooling to traverse the full
   attribute surface of an object through one uniform API — without
   special-casing metadata objects.

7. **Visible virtualness.**  ``AttributeDict`` exposes a per-entry
   ``virtual: bool`` flag.  ``lsattr`` output marks virtual attributes with a
   ``[virtual]`` indicator.

8. **GUI writability mirrors declared writability.**  If a virtual attribute
   is declared writable (``AttributeEntry.writable = True``), the GUI framework
   renders an editable widget for it — applying the same ``GuiHint``-driven
   widget inference as for stored attributes.  ``OptionMeta`` may override this
   with an explicit ``gui_writable_override`` flag to suppress or enable GUI
   editability independently of the underlying ``writable`` flag.  Read-only
   virtual attributes always render as display-only widgets.

--------------------------------------------------------------------------------
7. Plugin Integration
--------------------------------------------------------------------------------

Plugins can introduce new configurable attributes entirely through code, without
any registry entries or configuration files.

   A plugin defines ``AttributeEntry`` + ``OptionMeta`` + ``GuiHint`` for each
   new attribute.  No further registration is required for full integration into
   local and global configuration dialogs.

Specifically:

* The plugin's ``AttributeEntry`` definitions register the attribute in the
  model with its semantic metadata.
* The plugin's ``OptionMeta`` definitions determine whether and where the
  attribute appears in local and global dialogs.
* The plugin's ``GuiHint`` definitions provide the English display name and any
  editor hints.
* GUI generation, CCP integration, TOML persistence, and ``lsattr`` output all
  follow automatically from the attribute system — the plugin requires no
  custom dialog or persistence code for standard configurable attributes.

This property is a direct consequence of the single-source-of-truth principle:
because all structural information lives in code objects, a plugin that provides
those objects is immediately and fully integrated.

--------------------------------------------------------------------------------
8. Two Projections of the Attribute Model
--------------------------------------------------------------------------------

Local object configuration and global application configuration are two
**projection criteria** applied to the same attribute model, not two separate
definition systems.

   All structural and semantic properties of configuration options are defined
   exclusively in the attribute system.  Local and global configuration dialogs
   are views produced by filtering that system, not by consulting separate
   definitions.

**8.1 Local object configuration**

*Projection criterion*: ``AttributeEntry.exposed`` is ``True`` (or overridden
to ``True`` by ``OptionMeta.exposed_override``).

* Scope: one object instance.
* Persistence: bulk CCP ``set`` command through ``SynariusController``;
  written to the ``.syn`` file; **undoable**.
* Dialog invocation: double-click on a canvas element.  Exception: Kennlinien
  and Kennfelder blocks have dedicated editors and are excluded.

**8.2 Global application configuration**

*Projection criterion*: ``OptionMeta.global`` is ``True``, collected across all
registered configurable objects and structured by ``OptionMeta.global_path``.

* Scope: all participating objects across the application.
* Persistence: ``StudioConfigController`` writes to ``settings.toml``;
  **not undoable**; effective on next application start.

**8.3 Shared foundations**

Both projections share, without duplication:

* ``AttributeEntry`` semantic metadata (bounds, unit, enum_values, docstring).
* ``GuiHint``-driven widget type inference (Section 9).
* ``AttribViewModel`` / ``AttribTableWidget`` / ``AttribFormWidget`` (Section 9).
* Validation and error-feedback pattern (Section 13).
* Ordering rules (Section 12).

The difference between local and global configuration lies entirely in the
**projection criterion**, the **scope**, and the **write path** — not in
separate metadata definitions.

--------------------------------------------------------------------------------
9. Widget Type Inference and GUI Classes
--------------------------------------------------------------------------------

**9.1 Widget type inference**

The Studio widget factory selects a widget for each attribute using the
following precedence:

1. Explicit override in ``GuiHint.widget_type_override`` (if set).

2. Runtime type of ``entry.value`` plus semantic metadata from
   ``AttributeEntry``:

   .. list-table::
      :widths: 40 60
      :header-rows: 1

      * - Condition
        - Widget
      * - ``enum_values`` is not ``None``, ``len <= 3``
        - Radio buttons (vertical)
      * - ``enum_values`` is not ``None``, ``len > 3``
        - Drop-down (``QComboBox``)
      * - ``isinstance(value, bool)``
        - Checkbox (``QCheckBox``)
      * - ``isinstance(value, (int, float))`` and ``bounds`` is not ``None``
        - Input field + slider (``QDoubleSpinBox`` + ``QSlider``)
      * - ``isinstance(value, (int, float))``
        - Spin-box with direct entry (``QDoubleSpinBox``)
      * - Colour value
        - Colour picker (``QColorDialog`` inline button)
      * - ``pathlib.Path`` or path string (heuristic)
        - File/path picker (``QFileDialog`` inline button)
      * - Date / datetime
        - Date picker (``QDateEdit``)
      * - All other types
        - Plain text input (``QLineEdit``) with ``value_spec``-based validation

3. Fallback: plain text input (``QLineEdit``).

``bool`` must be tested before ``int`` (``bool`` is a subclass of ``int`` in
Python).

**9.2 ``AttribViewModel``**

``AttribViewModel`` holds the projected set of ``AttributeEntry`` objects for
one dialog scope.  It tracks original values, pending values, and validation
state per attribute.  Validation logic, change detection, and bulk-set
generation reside exclusively here — not in view classes.

**9.3 ``AttribTableWidget`` and ``AttribFormWidget``**

Two view classes render the same ``AttribViewModel``; both are functionally
equivalent.

``AttribTableWidget``
    ``QTableWidget`` with three columns (display name | value widget | unit).
    Default for canvas dialogs and ``OptionsMenuWidget``.

``AttribFormWidget``
    ``QGridLayout`` with the same three-column structure.  System widget style.
    Preferred in embedded panels and context menus.

Both widget classes provide a **right-click context menu** on each attribute
row.  For attributes that have a default value in ``defaults.toml``, the menu
offers:

* **Reset to default** — restores the individual attribute to its
  ``defaults.toml`` value immediately (with inline confirmation for the single
  attribute).

**9.4 ``OptionsMenuWidget``**

Used for the global configuration dialog:

* Left: ``QTreeView`` built from the ``global_path`` tree in ``OptionMeta``.
* Right: ``QScrollArea`` with stacked ``AttribTableWidget`` instances, one per
  section (path depth ≥ 3) or one flat widget for shallower nodes.

Path-depth semantics (depth of ``OptionMeta.global_path``):

* Depth 1: attribute in the ``AttribWidget`` of the top-level tree node.
* Depth 2: attribute under a sub-node.
* Depth 3: attribute in a labelled ``AttribWidget`` in the stacked right panel.
* Depth > 3: additional subtree branches in the tree view.

**Reset operations in ``OptionsMenuWidget``:**

*Per-group reset* — a *Reset group to defaults* action is available in the
context menu of each ``AttribWidget`` panel (right side).  Before applying, a
confirmation dialog lists every attribute in the group that would be reset,
together with its current value and its default value.  Only attributes that
have a ``defaults.toml`` entry are included.

*Global reset* — a *Reset all settings to defaults* action is available in the
toolbar or menu of the ``OptionsMenuWidget``.  Before applying, a warning
dialog explicitly states that **all user-specific global configuration will be
lost** and asks for confirmation.  No per-attribute detail is shown in the
global reset dialog (the scope is the entire ``settings.toml``).

--------------------------------------------------------------------------------
10. CCP Integration
--------------------------------------------------------------------------------

**10.1 Local object configuration — Bulk-Set command**

On dialog *OK*, ``AttribViewModel.changed_values()`` returns a dict of changed
attributes.  The dialog emits one CCP command:

.. code-block:: text

   set <object_hash_name> {attr1: value1, attr2: value2, ...}

This travels through ``SynariusController`` and is **undoable**.  Only changed
attributes are included.  Changes to model attributes in the local dialog are
always undoable; changes to global user settings in the ``OptionsMenuWidget``
are not (they are managed by ``ConfigController``, which has no undo stack).

**10.2 ConfigController**

The application provides a dedicated ``ConfigController`` for global
application configuration.  It shares CCP infrastructure (parser, command
dispatch, console surface) with ``SynariusController`` but operates on a
separate model root and carries **no undo stack**.  ``SynariusController``
is not modified.  Global config changes are applied through
``ConfigController`` and written to ``settings.toml`` (Section 11).

**10.3 CCP context — optional object argument**

Where a CCP command is issued within an established *object context* (e.g. a
console session that has selected or focused a specific object), the
``<object_hash_name>`` argument may be **omitted**.  The controller then
applies the command to the current context object:

.. code-block:: text

   # With explicit object:
   set my_block.gain 2.0

   # With implicit context object (same effect when context = my_block):
   set gain 2.0

Context establishment and the precise syntax for entering/leaving a context
are specified in the CCP specification (:doc:`controller_command_protocol`).
The ``lsattr`` command likewise accepts the object argument as optional when
a context object is active.

--------------------------------------------------------------------------------
11. TOML Persistence for Global Configuration
--------------------------------------------------------------------------------

.. note::

   This section applies exclusively to **global application configuration**
   (attributes where ``OptionMeta.global`` is ``True``).  Local object
   configuration — model attributes edited through local dialogs — is
   persisted via the project and model format (e.g. ``.syn`` files), not
   through the TOML mechanism described here.

**11.1 Two-file approach**

``defaults.toml``
    Ships with the application.  All supported keys with their default values.
    Read-only at runtime; schema reference and reset target.

``settings.toml``
    User-specific overrides (only keys that differ from defaults).  Written on
    *OK* in the global config dialog.  Located at
    ``platformdirs.user_config_dir("synarius") / "settings.toml"``.

At startup both files are merged; ``settings.toml`` overrides individual keys.
Settings are effective on the **next application start**.

**11.2 Reading and writing**

* Reading: ``tomllib`` (Python 3.11+ stdlib).
* Writing: ``tomli-w`` (explicit dependency).

Only stored, non-virtual attributes that differ from their default are written
to ``settings.toml``.  Virtual attributes (Section 6) are never persisted:
they carry no own persistence logic and are excluded from serialisation.

**11.3 Schema migration**

Unknown keys in ``settings.toml`` (no corresponding attribute in the current
model) are ignored and logged at WARNING level.  No migration mechanism is
required in v1.

**11.4 Reset to default**

*Single-attribute reset* — available via the context menu of every attribute
row whose key exists in ``defaults.toml`` (Section 9.3).  Removes the key
from ``settings.toml`` and reloads its value from ``defaults.toml``.  Takes
effect on the next application start.

*Group reset* — resets all attributes in one ``AttribWidget`` panel that have
a ``defaults.toml`` entry.  A confirmation dialog lists affected attributes
with current and default values before applying (Section 9.4).

*Global reset* — deletes ``settings.toml`` entirely (or replaces it with an
empty file).  A warning dialog states that all user-specific global
configuration will be permanently lost (Section 9.4).  Takes effect on the
next application start.

--------------------------------------------------------------------------------
12. Ordering and Grouping
--------------------------------------------------------------------------------

**Default:** alphabetical by ``GuiHint.display_name`` at every level (tree
nodes, section headings, attribute rows).

**Override:** ``OptionMeta.order`` (integer) opts out of alphabetical ordering
at the attribute's own level.  Lower numbers sort first.  Items without an
explicit order sort alphabetically after all ordered items.  The override
applies only to the annotated level; sub-levels default to alphabetical unless
they also carry an order value.

The same rules apply to both projections (Section 8).

--------------------------------------------------------------------------------
13. Validation and Error Feedback
--------------------------------------------------------------------------------

All validation errors — from ``value_spec``, from ``bounds`` clamping, or from
widget-level checks — are handled uniformly:

* **On input change**: immediate visual feedback (red border, inline message).
* **On OK**: *OK* button is disabled until all errors are resolved; no values
  are committed while any error is active.
* **On Cancel**: all pending changes are discarded; no CCP command is emitted.

This behaviour is identical for both projections.  An optional **Apply** button
in the global config dialog allows theme/colour changes to be previewed without
closing.

--------------------------------------------------------------------------------
14. ``lsattr`` Command Extensions
--------------------------------------------------------------------------------

``lsattr -r <object>``
    Lists attribute keys with their ``OptionMeta`` and ``GuiHint`` fields.
    Virtual attributes are listed with a ``[virtual]`` marker.  Attributes
    with no associated ``OptionMeta`` / ``GuiHint`` are annotated
    ``(no option metadata)``.

``lsattr -ra <object>``
    Synthesises ``lsattr -r`` with ordinary ``lsattr`` output: for each
    attribute the combined view shows model-side fields (value, bounds, unit,
    enum_values, docstring, exposed, writable) and metadata-side fields
    (display_name, global, global_path, order) side by side.

Both flags work on domain objects (``SynariusController``) and config objects
(``ConfigController``).  When a CCP context object is active, the
``<object>`` argument may be omitted (see Section 10.3).

--------------------------------------------------------------------------------
15. Out of Scope (v1)
--------------------------------------------------------------------------------

* **"Requires restart" flag** — not modelled in v1.
* **Per-project configuration** — architecture accommodates a third TOML layer;
  not implemented.
* **Explicit widget-type annotation** — runtime-type inference plus
  ``GuiHint.widget_type_override`` is the v1 mechanism.
* **Internationalisation** — infrastructure conventions established in
  Section 5; no translated strings in v1.
* **``StudioConfigController`` console layout** — deferred to the UI sprint.
* **``ConfigController`` console layout** — single or separate console tab;
  deferred to the UI sprint.
* **Config export / import profiles** — not in scope.
* **Detailed field lists for ``OptionMeta`` and ``GuiHint``** — roles are
  defined in this document; field-level specification is deferred to the
  implementation sprint.

--------------------------------------------------------------------------------
16. Related Documents
--------------------------------------------------------------------------------

* :doc:`attribute_dict` — ``AttributeDict`` / ``AttributeEntry`` technical reference.
* :doc:`controller_command_protocol` — CCP ``set`` command semantics.
* :doc:`attribute_path_semantics` — hierarchical attribute paths.
* :doc:`../developer/programming_guidelines` — repository boundary rules.
