..
   Synarius — Attribute Configuration and Options Management — Architecture Design v0.2.

================================================================================
Attribute Configuration and Options Management — Architecture Design
================================================================================

:Status: Technical Reference
:Version: 0.2
:Concept: :doc:`concept`

This document translates the principles and constraints in the concept into a
concrete module and class structure.  It specifies the package layout, class
inventory, public API sketches, and the data flows for both projections.

--------------------------------------------------------------------------------
1. Package Layout
--------------------------------------------------------------------------------

**1.1 ``synarius_attr_config`` — options management module**

``synarius_attr_config`` is a new Python package that depends on
``synarius_core`` and optionally on ``PySide6`` (Layer 4 only).  The package
is organised in **four explicit layers** with a strict one-direction import
rule: each layer may only import from layers above it.

.. code-block:: text

   synarius_attr_config/
       __init__.py                  # top-level re-exports (Layers 1–3)
       │
       meta/                        # Layer 1 — data structures
       │   __init__.py              #   exports: OptionMeta, GuiHint
       │   _meta.py                 #   no Qt, no file I/O; depends only on stdlib
       │
       projection/                  # Layer 2 — attribute projection
       │   __init__.py              #   exports: AttribViewModel, RegistryOverlayStore
       │   _view_model.py           #   no Qt; depends on Layer 1 + synarius_core
       │   _registry.py             #   no Qt; depends on Layer 1 + stdlib
       │
       persistence/                 # Layer 3 — TOML persistence
       │   __init__.py              #   exports: TomlPersistenceLayer
       │   _toml.py                 #   no Qt; depends on Layer 1 + tomllib + tomli-w
       │
       widgets/                     # Layer 4 — Qt GUI (PySide6 required)
           __init__.py              #   exports: AttribTableWidget, AttribFormWidget,
           │                        #            OptionsMenuWidget
           _inference.py            #   widget-type inference (pure function)
           _table_widget.py         #   AttribTableWidget (QTableWidget-based)
           _form_widget.py          #   AttribFormWidget (QGridLayout-based)
           _options_menu.py         #   OptionsMenuWidget (QTreeView + stacked panels)

**Layer import rule**: a module in Layer *n* must not import from Layer *n+1*
or higher.  In particular, ``persistence/`` must never import from
``widgets/``; ``projection/`` must never import from ``persistence/``.

A consumer that needs only metadata introspection can depend on
``synarius_attr_config.meta`` alone — no Qt, no file I/O.
A consumer that needs config persistence but no GUI can depend on Layers 1–3.
Only consumers that render dialogs need Layer 4.

All public names from Layers 1–3 are additionally re-exported from
``synarius_attr_config.__init__`` for convenience.

**1.2 Consuming application (e.g. ``synarius_studio``)**

Application-specific wiring stays in the consuming application and is not part
of the options management module:

.. code-block:: text

   synarius_studio/
       config/
           __init__.py
           _controller.py        # ConfigController (no undo stack)
           defaults.toml         # ships with application; schema reference
       _options_window.py        # OptionsMenuWidget integration in main window

--------------------------------------------------------------------------------
2. Dependency Graph
--------------------------------------------------------------------------------

**2.1 Cross-package dependencies**

.. code-block:: text

   ┌──────────────────────────────────────┐
   │           synarius_core              │
   │  AttributeEntry  AttributeDict       │
   │  value_spec      AttributePath       │
   └────────────────────┬─────────────────┘
                        │ depended on by
                        ▼
   ┌──────────────────────────────────────┐
   │        synarius_attr_config          │
   │   (Layers 1–4, see Section 1.1)      │
   └────────────────────┬─────────────────┘
                        │ consumed by
                        ▼
   ┌──────────────────────────────────────┐
   │        synarius_studio               │
   │  ConfigController (Layer 5: app)     │
   │  defaults.toml / settings.toml paths │
   │  app-specific OptionMeta/GuiHint     │
   └──────────────────────────────────────┘

The outer dependency direction is strictly top-down.  ``synarius_core`` has
no import dependency on ``synarius_attr_config``; ``synarius_attr_config``
has no import dependency on ``synarius_studio``.

**2.2 Internal layer dependencies (within ``synarius_attr_config``)**

.. code-block:: text

   synarius_core  ──────────────────────────────────────────┐
         │                                                   │
         ▼                                                   │
   Layer 1: meta/            OptionMeta, GuiHint             │
         │                                                   │
         ├──────────────────────────────────────────────┐   │
         ▼                                              ▼   ▼
   Layer 2: projection/      AttribViewModel        Layer 3: persistence/
            RegistryOverlayStore                    TomlPersistenceLayer
         │                        │                         │
         └────────────────────────┴─────────────────────────┘
                                  │
                                  ▼
                      Layer 4: widgets/           (PySide6 required)
                      AttribTableWidget
                      AttribFormWidget
                      OptionsMenuWidget

Layers 2 and 3 are independent of each other; neither imports the other.
Layer 4 imports from all three lower layers.  No upward imports are
permitted.

--------------------------------------------------------------------------------
3. Class Inventory
--------------------------------------------------------------------------------

.. list-table::
   :widths: 28 18 54
   :header-rows: 1

   * - Class
     - Module
     - Responsibility
   * - ``OptionMeta``
     - Layer 1 ``synarius_attr_config.meta``
     - Configuration role: ``global_``, ``global_path``, ``local``, ``order``,
       ``exposed_override``, ``gui_writable_override``.  No Qt or file I/O
       dependency.
   * - ``GuiHint``
     - Layer 1 ``synarius_attr_config.meta``
     - Presentation hints: ``display_name``, ``widget_type_override``,
       ``decimal_precision``.  Never consulted outside the rendering pipeline.
   * - ``AttribViewModel``
     - Layer 2 ``synarius_attr_config.projection``
     - Projected attribute set for one dialog scope.  Tracks original/pending
       values; runs bounds/enum/value_spec validation; generates
       ``changed_values()``; reset helpers; no Qt dependency.
   * - ``RegistryOverlayStore``
     - Layer 2 ``synarius_attr_config.projection``
     - Loads TOML registry; applies i18n overlays; validates orphan keys; emits
       warnings only; no Qt dependency.
   * - ``TomlPersistenceLayer``
     - Layer 3 ``synarius_attr_config.persistence``
     - Merges defaults.toml + settings.toml at load time; delta writes;
       resets by key removal (never writes default values); no Qt dependency.
   * - ``infer_widget_type``
     - Layer 4 ``synarius_attr_config.widgets``
     - Pure function ``(entry, hint) → WidgetType``; implements the full
       inference table from concept Section 9.1.
   * - ``AttribTableWidget``
     - Layer 4 ``synarius_attr_config.widgets``
     - ``QTableWidget`` with three columns (display name | value widget | unit);
       right-click context menu with per-attribute reset.
   * - ``AttribFormWidget``
     - Layer 4 ``synarius_attr_config.widgets``
     - ``QGridLayout``-based equivalent; preferred in embedded panels.
   * - ``OptionsMenuWidget``
     - Layer 4 ``synarius_attr_config.widgets``
     - ``QTreeWidget`` (left) + ``QScrollArea`` with stacked
       ``AttribTableWidget`` panels (right); per-group and global reset.
   * - ``ConfigController``
     - consuming app (Layer 5)
     - Dedicated interface for user-preference attributes; CCP syntax only by
       convention; no undo stack, no project context, no simulation semantics.

--------------------------------------------------------------------------------
4. Class API Sketches
--------------------------------------------------------------------------------

**4.1 ``OptionMeta``**

.. code-block:: python

   from dataclasses import dataclass, field

   @dataclass
   class OptionMeta:
       global_: bool = False
       global_path: str = ""
       local: bool = True
       order: int | None = None
       exposed_override: bool | None = None
       gui_writable_override: bool | None = None

``global_path`` uses forward-slash notation: ``"Simulation/Solver/ODE"``.
Depth is the number of path components (concept Section 9.4).

**4.2 ``GuiHint``**

.. code-block:: python

   @dataclass
   class GuiHint:
       display_name: str = ""
       widget_type_override: str | None = None
       decimal_precision: int | None = None

``widget_type_override`` values: ``"checkbox"``, ``"combobox"``,
``"radio"``, ``"spinbox"``, ``"slider+spinbox"``, ``"color_picker"``,
``"path_picker"``, ``"datepicker"``, ``"lineedit"``.

**4.3 ``AttribViewModel``**

.. code-block:: python

   class AttribViewModel:
       def __init__(
           self,
           entries: list[tuple[str, AttributeEntry, OptionMeta | None, GuiHint | None]],
           persistence: TomlPersistenceLayer | None = None,
           registry: RegistryOverlayStore | None = None,
       ) -> None: ...

       # --- change tracking ---
       def set_pending(self, key: str, value: object) -> None: ...
       def revert_pending(self, key: str) -> None: ...
       def changed_values(self) -> dict[str, object]: ...
       def has_pending_changes(self) -> bool: ...

       # --- validation ---
       def validate(self, key: str) -> ValidationResult: ...
       def has_errors(self) -> bool: ...

       # --- reset ---
       def reset_to_default(self, key: str) -> None: ...
       def reset_group(self, keys: list[str]) -> None: ...
       def default_value(self, key: str) -> object | None: ...

       # --- display ---
       def display_name(self, key: str) -> str: ...
       def effective_exposed(self, key: str) -> bool: ...
       def effective_writable(self, key: str) -> bool: ...

**4.4 ``TomlPersistenceLayer``**

.. code-block:: python

   class TomlPersistenceLayer:
       def __init__(self, defaults_path: Path, settings_path: Path) -> None: ...

       def load(self) -> dict[str, object]: ...
       def write(self, changes: dict[str, object]) -> None: ...

       def reset_attribute(self, key: str) -> None:
           """Remove key from settings.toml (never writes default value)."""

       def reset_group(self, keys: list[str]) -> None:
           """Remove override keys for the group; delegates to reset_attribute per key.
           Does NOT write default values — preserves the delta semantics of
           settings.toml: absent key = use default, present key = user override."""

       def reset_all(self) -> None:
           """Delete settings.toml entirely; subsequent load() returns defaults only."""

       def default_value(self, key: str) -> object | None: ...
       def has_default(self, key: str) -> bool: ...

**4.5 ``RegistryOverlayStore``**

.. code-block:: python

   class RegistryOverlayStore:
       def load(self, path: Path) -> None: ...
       def display_name(
           self,
           obj_type: str,
           attr_key: str,
           lang: str = "en",
       ) -> str | None: ...
       def validate_against(
           self,
           known_pairs: set[tuple[str, str]],
       ) -> None: ...

``validate_against()`` emits a ``logging.WARNING`` for each orphan key; it
does not raise.

**4.6 ``ConfigController``** (consuming application)

``ConfigController`` is not a variant of ``SynariusController``.  It is a
dedicated interface for user-preference attributes.  The following table makes
the boundary explicit:

.. list-table::
   :widths: 50 50
   :header-rows: 1

   * - ``SynariusController``
     - ``ConfigController``
   * - Undo stack present
     - No undo stack
   * - Model root: simulation graph
     - Model root: global-config ``AttributeDict``
   * - Project and file context
     - No project context
   * - Commands affect simulation state
     - Commands affect user preferences only
   * - Changes written to ``.syn`` on save
     - Changes written to ``settings.toml`` on OK
   * - Routing: determined by CCP context object
     - Routing: determined by CCP context object

The only relationship to ``SynariusController`` is:

* **Shared command syntax** — ``ConfigController.execute_command()`` accepts
  the same CCP ``set`` / ``get`` / ``lsattr`` text format.
* **Shared console surface** — the same console widget dispatches to either
  controller based on the active CCP context.

The implementations are separate objects.  No runtime state or infrastructure
is shared between the two controller instances.

.. code-block:: python

   class ConfigController:
       def __init__(
           self,
           persistence: TomlPersistenceLayer,
           global_attrib_root: AttributeDict,
       ) -> None: ...

       def apply(self, changes: dict[str, object]) -> None: ...
       def reset_attribute(self, key: str) -> None: ...
       def reset_group(self, keys: list[str]) -> None: ...
       def reset_all(self) -> None: ...

       def execute_command(self, command_text: str) -> str:
           """Accept CCP set/get/lsattr syntax; route to global_attrib_root.
           Never touches SynariusController or the simulation model graph."""

--------------------------------------------------------------------------------
5. Data Flow: Local Object Configuration
--------------------------------------------------------------------------------

.. code-block:: text

   User double-clicks canvas element
             │
             ▼
   LocalConfigDialog.__init__()
     ┌─────────────────────────────────────────────────────────┐
     │  projection: attrs where effective_exposed(key) == True  │
     │                                                          │
     │  AttribViewModel(entries=local_projection,               │
     │                  persistence=None,                       │
     │                  registry=registry_store)                │
     │                                                          │
     │  AttribTableWidget(view_model)                           │
     └─────────────────────────────────────────────────────────┘
             │
             │  user edits values → set_pending(key, value)
             │  validation runs → red border / inline error
             │
             │  OK pressed (only if not has_errors())
             ▼
   changed = view_model.changed_values()
             │
             ▼
   cmd = f"set {object_hash_name} {changed!r}"
             │
             ▼
   SynariusController.execute_command(cmd)
             │  ← undoable, writes to undo stack
             ▼
   AttributeDict.set_bulk(changed)
             │
             ▼
   .syn file updated on next project save

**Cancel path**: ``view_model.revert_pending()`` for all keys; no CCP command
is emitted; no undo stack entry created.

--------------------------------------------------------------------------------
6. Data Flow: Global Application Configuration
--------------------------------------------------------------------------------

.. code-block:: text

   User opens Options menu (e.g. Edit → Options…)
             │
             ▼
   OptionsMenuWidget.__init__()
     ┌──────────────────────────────────────────────────────────────┐
     │  projection: attrs where OptionMeta.global_ == True          │
     │  grouped by OptionMeta.global_path (QTreeView left pane)     │
     │                                                              │
     │  per tree node:                                              │
     │    AttribViewModel(entries=group_projection,                 │
     │                    persistence=toml_layer,                   │
     │                    registry=registry_store)                  │
     │    AttribTableWidget(view_model)  → stacked in right pane    │
     └──────────────────────────────────────────────────────────────┘
             │
             │  user edits → set_pending / validate
             │
             │  OK pressed (only if not has_errors() across all groups)
             ▼
   for each group_vm with group_vm.has_pending_changes():
       ConfigController.apply(group_vm.changed_values())
             │
             ▼
   TomlPersistenceLayer.write(changes)
       writes only delta keys to settings.toml
             │
             (changes effective on next application start)

**Reset flows:**

.. code-block:: text

   Per-attribute reset (context menu on row):
     view_model.reset_to_default(key)
     → TomlPersistenceLayer.reset_attribute(key)
     → removes key from settings.toml

   Per-group reset (context menu on AttribWidget panel):
     confirmation dialog showing all affected attrs (current override → default)
     → view_model.reset_group(keys_with_defaults)
     → TomlPersistenceLayer.reset_group(keys_with_defaults)
     → removes override keys from settings.toml  [NOT: writes default values]

   Global reset (toolbar / menu action):
     warning dialog (no attribute detail)
     → TomlPersistenceLayer.reset_all()
     → settings.toml deleted or replaced with empty file

--------------------------------------------------------------------------------
7. Virtual Attribute Wiring
--------------------------------------------------------------------------------

``AttributeDict`` is extended with a ``virtual: bool`` per-entry flag.  The
options management module registers virtual entries for ``OptionMeta`` and
``GuiHint`` fields through a registration helper:

.. code-block:: python

   # internal helper — not public API
   def _register_virtual_attrs(
       attr_dict: AttributeDict,
       attr_key: str,
       option_meta: OptionMeta,
       gui_hint: GuiHint,
   ) -> None:
       """Register read-through virtual attributes for OptionMeta and GuiHint
       fields on the given AttributeDict entry."""

Virtual entries created by this helper:

.. list-table::
   :widths: 36 20 44
   :header-rows: 1

   * - Virtual attribute key
     - Writable
     - Backing source
   * - ``<key>.__display_name``
     - No
     - ``GuiHint.display_name``
   * - ``<key>.__global``
     - No
     - ``OptionMeta.global_``
   * - ``<key>.__global_path``
     - No
     - ``OptionMeta.global_path``
   * - ``<key>.__order``
     - Yes (declared)
     - ``OptionMeta.order``
   * - ``<key>.__widget_type_override``
     - Yes (declared)
     - ``GuiHint.widget_type_override``

Read-only virtual attributes are never rendered as editable widgets.
Writable virtual attributes follow widget-type inference normally.
No virtual attribute is persisted (concept Section 6, rule 1).

--------------------------------------------------------------------------------
8. Threading Considerations
--------------------------------------------------------------------------------

All widget classes must be created and accessed on the Qt main thread.
``AttribViewModel``, ``TomlPersistenceLayer``, and ``RegistryOverlayStore``
carry no Qt dependency and may be constructed on any thread, but mutation
from multiple threads is not supported — callers must serialise access.

``TomlPersistenceLayer.write()`` performs synchronous file I/O on the calling
thread.  The file size is expected to be small (< 1 KB); no async wrapper is
required in v1.

--------------------------------------------------------------------------------
9. Related Documents
--------------------------------------------------------------------------------

* :doc:`concept` — architectural principles and constraints.
* :doc:`implementation_plan` — phased work sequence and example script.
* :doc:`../attribute_dict` — ``AttributeDict`` / ``AttributeEntry`` reference.
* :doc:`../controller_command_protocol` — CCP ``set`` command semantics.
