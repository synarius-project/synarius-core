..
   Synarius — Attribute Configuration and Options Management, concept.

================================================================================
Attribute Configuration and Options Management — Concept
================================================================================

:Status: Concept (pre-specification)
:Version: 0.1
:Scope: synarius-core model layer; synarius-studio GUI layer

--------------------------------------------------------------------------------
1. Overview and Motivation
--------------------------------------------------------------------------------

Model objects in Synarius carry attributes stored in ``AttributeDict``.  A
subset of these attributes constitutes *user-facing configuration*: values that
the user actively inspects and changes through GUI dialogs rather than through
direct CCP scripting.

This concept defines:

* Which attribute metadata belongs in the **core model layer** (synarius-core),
* Which presentation metadata belongs in the **Studio GUI layer**
  (synarius-studio / synarius-apps),
* A shared **GUI-generation mechanism** that renders configuration dialogs from
  attribute metadata, reused for both per-object local config and app-wide
  global config,
* **CCP-based data transmission** so that configuration changes travel through
  the standard command path,
* **TOML-based persistence** for app-wide global configuration.

--------------------------------------------------------------------------------
2. Repository Boundary
--------------------------------------------------------------------------------

The Synarius repository boundary rule (*simulation logic in synarius-core;
Studio and Apps handle UI and integration only*) applies directly to this
mechanism:

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Belongs in **synarius-core**
     - Belongs in **synarius-studio / synarius-apps**
   * - ``tooltip`` — docstring-like attribute description
     - Display names (human-readable labels)
   * - Validation limits: ``min_value``, ``max_value``, ``step``
     - Internationalization (BCP 47, ICU MessageFormat, gettext)
   * - Enum member ordering and identity (stored values)
     - Widget type selection and rendering
   * - ``value_spec`` boundary contracts
     - Config-dialog layout and grouping
   * - Schema-migration log messages
     - TOML persistence layer

The defining test: if the information is needed to *validate or simulate
correctly*, it belongs in core.  If it is only needed to *display or translate*
the value, it belongs in Studio.

--------------------------------------------------------------------------------
3. Two Configuration Domains
--------------------------------------------------------------------------------

The mechanism covers two distinct but structurally similar domains:

**3.1 Local object configuration**

Per-instance settings that describe one specific model element (e.g. the display
colour of a particular ``Variable`` block, the axis labels of one ``DataViewer``).

* Stored in the model — persisted via the ``.syn`` file.
* Changes are transmitted as CCP ``set`` commands, which go through the command
  history and are therefore **undoable**.
* Dialog pattern mirrors ``StimulationDialog``: on *OK*, the dialog emits a list
  of CCP ``set <obj>.<attr> <value>`` lines that the host executes.

**3.2 Global application configuration**

App-wide preferences not tied to any particular model instance (e.g. default
simulation step size, UI theme, default file paths).

* Stored in a TOML file in the user's configuration directory.
* Changes are applied directly via ``AttributeDict.set_value`` and written to
  TOML; they are **not undoable** (consistent with all mainstream applications).
* Dialog structure uses the same widget-generation mechanism as 3.1 but writes
  to the TOML backend on *OK*.

Both domains share:

* the same attribute metadata fields (Section 4),
* the same widget-type inference rules (Section 6),
* the same validation feedback pattern (Section 8),
* the same ordering / grouping rules (Section 9).

The difference is purely in the write path and the persistence backend.

--------------------------------------------------------------------------------
4. Core-Side Attribute Metadata (``AttributeEntry`` extensions)
--------------------------------------------------------------------------------

The following fields are added to or clarified in ``AttributeEntry``.  All are
optional and have ``None`` as default so that existing code is unaffected.

**4.1 ``tooltip: str | None``**

A short English description of the attribute, analogous to a docstring.  It is
factual and implementation-neutral ("Maximum allowed engine speed in rev/min"),
not a GUI label.  ``None`` means no tooltip is shown.

Rationale: a tooltip describes *what the attribute is*, which is a core-model
concern, not a presentation concern.

**4.2 ``min_value: float | None`` / ``max_value: float | None`` / ``step: float | None``**

Inclusive lower/upper bound and suggested increment for numeric attributes.
These constrain *valid values* — they are therefore part of the model contract,
not a UI choice.  ``None`` means unbounded / no suggested step.

Consistency requirement: when a ``value_spec`` is also present, the limits and
the ``value_spec`` must agree.  The ``value_spec`` is normative; the numeric
limits are informative hints for widget clamping and are not enforced
independently.

**4.3 ``enum_choices: tuple[tuple[str, Any], ...] | None``**

An ordered sequence of ``(stored_value, display_hint)`` pairs defining a
closed enumeration.  ``stored_value`` is the canonical value written to the
model; ``display_hint`` is an English fallback label (Studio may override it
with a translated label from its registry).

Ordering of ``enum_choices`` is significant: it defines the canonical display
order.  The Studio layer must not reorder it.

``None`` means the attribute is not enumerated.

.. note::

   Existing ``value_spec`` callables that enforce an enumeration must be kept in
   sync with ``enum_choices``.  There is intentionally no automatic coupling:
   the spec is the normative source of truth; ``enum_choices`` is the
   introspectable annotation.

--------------------------------------------------------------------------------
5. Studio-Side Presentation Metadata
--------------------------------------------------------------------------------

**5.1 Display-Name Registry**

Studio maintains a text-based registry mapping
``(object_type_key, attribute_key)`` to a display name.  The registry is
human-editable (plain text or a minimal TOML/INI structure) and is the primary
extension point for internationalisation.

Default fallback: if no entry is found for the current language, the English
entry is used.  If no English entry is found, the raw attribute key is displayed.

**5.2 Internationalisation Infrastructure**

The registry is designed to accommodate future internationalisation without
requiring structural changes.  Conventions adopted from the start:

* Language tags follow **BCP 47** (e.g. ``en``, ``de``, ``de-CH``).
* All stored strings are **Unicode** (UTF-8 in files).
* Plural forms and grammatical agreement use **ICU MessageFormat** syntax when
  needed.
* Physical storage of translations uses the **gettext** ``PO``/``MO`` format or
  a TOML file with BCP 47 keys — decision deferred to the internationalisation
  sprint.

No internationalisation work is required in v1; the infrastructure choice is
made now to avoid costly retrofits.

**5.3 Widget Type Inference (see Section 6)**

Widget selection is a Studio concern and is described in Section 6.

--------------------------------------------------------------------------------
6. Widget Type Inference
--------------------------------------------------------------------------------

The Studio widget factory selects a widget for each attribute entry using the
following precedence:

1. **Explicit type annotation** (optional ``attr_widget_type`` field, deferred):
   if a lightweight type system for attributes is introduced in a future sprint,
   it takes priority.

2. **Runtime type of** ``entry.value`` **plus metadata:**

   .. list-table::
      :widths: 40 60
      :header-rows: 1

      * - Condition
        - Widget
      * - ``enum_choices`` is not ``None``, ``len <= 3``
        - Radio buttons (vertical)
      * - ``enum_choices`` is not ``None``, ``len > 3``
        - Drop-down (``QComboBox``)
      * - ``isinstance(value, bool)``
        - Checkbox (``QCheckBox``)
      * - ``isinstance(value, (int, float))`` and ``min_value`` and ``max_value`` set
        - Input field + slider (``QDoubleSpinBox`` + ``QSlider``)
      * - ``isinstance(value, (int, float))``
        - Spin-box with direct entry and validation (``QDoubleSpinBox``)
      * - Value is a colour (specific type TBD)
        - Colour picker (``QColorDialog``)
      * - Value is a ``pathlib.Path`` or path string (heuristic)
        - File/path picker (``QFileDialog`` inline button)
      * - Value is a date / datetime
        - Date picker (``QDateEdit``)
      * - All other types
        - Plain text input (``QLineEdit``) with ``value_spec``-based validation

3. **Fallback:** plain text input (``QLineEdit``).

``bool`` must be tested before ``int`` because in Python ``bool`` is a subclass
of ``int``.

--------------------------------------------------------------------------------
7. CCP Integration
--------------------------------------------------------------------------------

**7.1 Local object configuration**

On dialog *OK*, the dialog collects all changed attribute values and emits a
``list[str]`` of CCP commands:

.. code-block:: text

   set <object_hash_name>.<attribute_key> <value>

The host executes these commands through the standard controller path.  The
resulting command-history entries are undoable in the normal way.

This pattern is identical to ``StimulationDialog.protocol_commands()``.

**7.2 Global application configuration**

Global configuration changes do not travel through the model controller.  They
are applied directly via ``AttributeDict.set_value`` and written to TOML
immediately on *OK*.

Whether a dedicated Studio-side controller (separate from ``SynariusController``)
is introduced to manage global config is **deferred**.  If introduced, it would
receive its own CCP-like surface without undo semantics; refactoring
``SynariusController`` would be a prerequisite.  Until then, direct
``set_value`` calls are used.

--------------------------------------------------------------------------------
8. TOML Persistence for Global Configuration
--------------------------------------------------------------------------------

**8.1 File layout — two-file approach**

Two TOML files manage global configuration:

``defaults.toml``
    Ships with the application.  Contains all supported keys with their default
    values.  Read-only at runtime; the user never edits this file directly.
    This file also serves as the authoritative schema reference.

``settings.toml``
    User-specific overrides.  Contains only keys that differ from the defaults.
    Written by the application on every *OK* in the global config dialog.
    Located at ``platformdirs.user_config_dir("synarius") / "settings.toml"``.

At startup the application merges both files: ``defaults.toml`` is loaded
first, then ``settings.toml`` overrides individual keys.  The user can reset to
defaults by deleting ``settings.toml``.

**8.2 Reading and writing**

* Reading: Python 3.11+ ``tomllib`` (stdlib).  For Python < 3.11 the
  ``tomllib`` backport (``tomli``) is used.
* Writing: ``tomli-w`` (explicit dependency, avoids hand-rolled serialisation).

Only **stored** (non-virtual, non-getter-only) attributes that differ from their
default are written to ``settings.toml``.  Virtual attributes with a getter but
no setter are excluded from persistence.

**8.3 Schema migration**

When ``settings.toml`` is loaded and a key is present that does not correspond
to any known attribute in the current model:

* The key is **ignored**.
* A **warning is written to the application log** identifying the unknown key
  and its value, so that the user or a developer can act on it.

No automatic rename mapping or version-field is required in v1.  If systematic
migration becomes necessary, a ``[migration]`` section in ``defaults.toml`` can
be added in a future sprint.

--------------------------------------------------------------------------------
9. Ordering and Grouping
--------------------------------------------------------------------------------

**Default order:** alphabetical by display name at every level (pages, groups,
sections, parameters within a section).

**Override:** explicit integer rank annotations in the Studio display-name
registry allow any level to opt out of alphabetical order.  The override applies
to the annotated level only; sub-levels default to alphabetical unless they also
carry an override.

The same ordering rules apply to both local and global config dialogs.

--------------------------------------------------------------------------------
10. Validation and Error Feedback
--------------------------------------------------------------------------------

All validation errors — whether from ``value_spec`` raising a ``TypeError`` /
``ValueError`` or from limit checks — are handled uniformly:

* The offending widget is highlighted (e.g. red border).
* A human-readable message is shown inline in the dialog (below the widget or in
  a status bar area).
* The value is **not** committed to the model or to TOML.
* The *OK* button is disabled until all errors are resolved.

This behaviour is identical for local and global config dialogs.  The validation
message is taken from the exception text; ``value_spec`` authors should provide
clear, user-facing messages.

--------------------------------------------------------------------------------
11. Out of Scope (v1)
--------------------------------------------------------------------------------

The following topics are explicitly deferred to later sprints:

* **"Requires restart" flag** — not modelled in v1.
* **Per-project configuration** (config stored next to the ``.syn`` file) —
  architecture is designed to accommodate it (additional TOML layer between
  defaults and user settings), but not implemented.
* **Lightweight attribute type system** — the runtime-type inference in
  Section 6 is the v1 mechanism; a richer type annotation field may be added
  in a future sprint.
* **Internationalisation** — infrastructure conventions established in Section 5;
  no translated strings in v1.
* **Config export / import profiles** — not in scope.
* **Dedicated Studio-side CCP controller** — deferred; see Section 7.2.

--------------------------------------------------------------------------------
12. Related Documents
--------------------------------------------------------------------------------

* :doc:`attribute_dict` — ``AttributeDict`` / ``AttributeEntry`` technical reference.
* :doc:`controller_command_protocol` — CCP ``set`` command semantics.
* :doc:`attribute_path_semantics` — hierarchical attribute paths.
* :doc:`../developer/programming_guidelines` — repository boundary rules.
