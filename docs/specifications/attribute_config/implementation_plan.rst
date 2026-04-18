..
   Synarius — Attribute Configuration and Options Management — Implementation Plan v0.1.

================================================================================
Attribute Configuration and Options Management — Implementation Plan
================================================================================

:Status: Implementation Plan
:Version: 0.1
:Concept: :doc:`concept`
:Architecture: :doc:`architecture`

This document sequences the implementation into phases, defines acceptance
criteria for each phase, and provides a runnable example script that can be
used to test both forms of configuration end-to-end.

--------------------------------------------------------------------------------
1. Prerequisites
--------------------------------------------------------------------------------

Before any implementation work begins, the following must be in place:

* ``synarius_core`` ``AttributeEntry`` and ``AttributeDict`` are stable and
  have their ``virtual`` flag mechanism defined (required for Phase 2).
* ``tomli-w`` is declared as an explicit dependency of ``synarius_attr_config``.
* ``PySide6 >= 6.0.0`` is available in the target environment for Phase 4+.
* The ``synarius_attr_config`` package skeleton (``__init__.py``, ``widgets/``
  sub-package) is committed to the repository.

--------------------------------------------------------------------------------
2. Phase 1 — Data Structures (no GUI dependency)
--------------------------------------------------------------------------------

**Deliverables**

* ``OptionMeta`` dataclass in ``_meta.py`` with all fields from architecture
  Section 4.1.
* ``GuiHint`` dataclass in ``_meta.py`` with all fields from architecture
  Section 4.2.
* Public re-exports from ``synarius_attr_config.__init__``.

**Acceptance criteria**

* Both dataclasses are constructible with only keyword arguments.
* Default-constructed instances carry the documented default values.
* ``OptionMeta`` and ``GuiHint`` are importable as
  ``from synarius_attr_config import OptionMeta, GuiHint``.
* A ``mypy --strict`` pass produces no errors on the two files.

**Unit tests**

.. code-block:: python

   def test_option_meta_defaults():
       om = OptionMeta()
       assert om.global_ is False
       assert om.local is True
       assert om.order is None
       assert om.exposed_override is None

   def test_gui_hint_defaults():
       gh = GuiHint()
       assert gh.display_name == ""
       assert gh.widget_type_override is None

   def test_option_meta_and_gui_hint_have_no_shared_fields():
       om_fields = {f.name for f in fields(OptionMeta)}
       gh_fields = {f.name for f in fields(GuiHint)}
       assert om_fields.isdisjoint(gh_fields), "roles must be strictly disjoint"

--------------------------------------------------------------------------------
3. Phase 2 — Virtual Attribute Infrastructure
--------------------------------------------------------------------------------

**Deliverables**

* ``AttributeEntry.virtual: bool`` flag in ``synarius_core`` (default
  ``False``; ``True`` for entries registered by the virtual-attribute helper).
* Internal helper ``_register_virtual_attrs()`` in ``synarius_attr_config``
  (architecture Section 7).
* ``lsattr -r`` and ``lsattr -ra`` CCP command extensions in
  ``SynariusController`` (concept Section 14).

**Acceptance criteria**

* ``lsattr -r <object>`` lists all virtual attributes with ``[virtual]``
  marker.
* Reading a virtual attribute returns the current value of the backing
  ``OptionMeta`` / ``GuiHint`` field.
* Writing a writable virtual attribute (e.g. ``__order``) updates the backing
  object in-place; re-reading the virtual attribute returns the new value.
* Writing a read-only virtual attribute raises ``AttributeError``.
* No virtual attribute appears in the ``.syn`` serialisation of the owning
  object.
* No virtual attribute participates in undo history.

**Unit tests**

.. code-block:: python

   def test_virtual_read_through(sample_attr_dict, sample_option_meta):
       # After registering virtual attrs, reading __display_name returns
       # the GuiHint value, not a copy.
       attr_dict["gain.__display_name"] == sample_gui_hint.display_name

   def test_virtual_write_delegates(sample_attr_dict, sample_option_meta):
       attr_dict["gain.__order"] = 5
       assert sample_option_meta.order == 5

   def test_virtual_not_in_syn_serialisation(sample_object):
       data = sample_object.to_syn_dict()
       assert not any(k.startswith("__") for k in data)

--------------------------------------------------------------------------------
4. Phase 3 — AttribViewModel and Persistence Layer
--------------------------------------------------------------------------------

**Deliverables**

* ``AttribViewModel`` in ``projection/_view_model.py`` (full public API from
  architecture Section 4.3).
* ``TomlPersistenceLayer`` in ``persistence/_toml.py`` (full public API from
  architecture Section 4.4).
* Public re-exports from ``synarius_attr_config.projection.__init__``,
  ``synarius_attr_config.persistence.__init__``, and
  ``synarius_attr_config.__init__``.

**Acceptance criteria**

* ``changed_values()`` returns only attributes whose pending value differs from
  the original value.
* ``has_errors()`` returns ``True`` if and only if at least one attribute fails
  ``value_spec`` or ``bounds`` validation.
* ``reset_to_default(key)`` reverts the pending value to the value from
  ``defaults.toml``; if the key is absent from ``defaults.toml``, raises
  ``KeyError``.
* ``TomlPersistenceLayer.write()`` writes only the delta (changed keys) to
  ``settings.toml`` using ``tomli-w``.
* ``TomlPersistenceLayer.reset_attribute(key)`` removes the key from
  ``settings.toml``; it does **not** write the default value into
  ``settings.toml``.
* ``TomlPersistenceLayer.reset_group(keys)`` removes all listed keys from
  ``settings.toml`` by calling ``reset_attribute`` per key; does not write
  any default values.
* ``TomlPersistenceLayer.reset_all()`` deletes ``settings.toml`` entirely;
  a subsequent ``load()`` returns only defaults.
* All ``TomlPersistenceLayer`` methods handle a missing ``settings.toml``
  gracefully (no exception; treated as empty overrides).

**Unit tests**

.. code-block:: python

   def test_changed_values_only_changed(tmp_path):
       persistence = make_persistence(tmp_path)
       vm = make_view_model(persistence=persistence)
       vm.set_pending("gain", 2.0)
       assert vm.changed_values() == {"gain": 2.0}
       assert "offset" not in vm.changed_values()

   def test_persistence_delta_write(tmp_path):
       layer = TomlPersistenceLayer(
           defaults_path=tmp_path / "defaults.toml",
           settings_path=tmp_path / "settings.toml",
       )
       layer.write({"gain": 3.0})
       data = tomllib.loads((tmp_path / "settings.toml").read_text())
       assert data == {"gain": 3.0}

   def test_persistence_reset_all(tmp_path):
       layer = make_persistence_with_settings(tmp_path)
       layer.reset_all()
       merged = layer.load()
       assert merged == layer.load()   # equals defaults only

--------------------------------------------------------------------------------
5. Phase 4 — Widget Classes
--------------------------------------------------------------------------------

**Deliverables**

* ``_infer_widget_type(entry, hint) → WidgetType`` in ``widgets/_inference.py``
  implementing the full precedence table (concept Section 9.1).
* ``AttribTableWidget`` in ``widgets/_table_widget.py``.
* ``AttribFormWidget`` in ``widgets/_form_widget.py``.
* ``OptionsMenuWidget`` in ``widgets/_options_menu.py``.
* Public re-exports from ``synarius_attr_config.widgets.__init__``.

**Acceptance criteria**

* Widget type inference: ``bool`` → checkbox (must be tested before ``int``);
  ``float`` with bounds → slider+spinbox; ``Enum`` with ≤ 3 members → radio;
  ``Enum`` with > 3 members → combobox.
* ``AttribTableWidget`` renders three columns: display name (from
  ``GuiHint.display_name`` via ``AttribViewModel.display_name()``), value
  widget (from inference), unit (from ``AttributeEntry.unit``).
* Right-click context menu on a row with a ``defaults.toml`` entry shows
  *Reset to default*; action calls ``view_model.reset_to_default(key)``.
* ``OptionsMenuWidget`` tree nodes are built from ``OptionMeta.global_path``
  components; selecting a node displays the corresponding
  ``AttribTableWidget`` in the right pane.
* OK button in any dialog backed by ``AttribViewModel`` is disabled while
  ``has_errors()`` is ``True``.

**Manual smoke test**

Run the example script (Section 8) and verify that:

1. The local dialog opens, shows correct display names, widgets, and units.
2. Editing a value within bounds enables OK; entering an out-of-bounds value
   shows a red border and disables OK.
3. The options menu tree matches the ``global_path`` structure; selecting a
   node switches the right panel.
4. Clicking *Reset to default* in the context menu reverts the value visually.

--------------------------------------------------------------------------------
6. Phase 5 — RegistryOverlayStore
--------------------------------------------------------------------------------

**Deliverables**

* ``RegistryOverlayStore`` in ``_registry.py`` (full public API from
  architecture Section 4.5).

**Acceptance criteria**

* Loading a valid TOML file with ``display_name`` overrides causes
  ``AttribViewModel.display_name(key)`` to return the overlay value.
* A missing registry file emits a ``WARNING`` log message and does not raise.
* ``validate_against()`` emits one ``WARNING`` per orphan key (key present in
  registry but not in the supplied ``known_pairs`` set).
* ``validate_against()`` emits no warnings when all keys match.

**Unit tests**

.. code-block:: python

   def test_registry_overlay_display_name(tmp_path):
       reg = RegistryOverlayStore()
       reg.load(write_registry_toml(tmp_path, {"MyObj.gain": {"en": "Factor"}}))
       assert reg.display_name("MyObj", "gain", "en") == "Factor"

   def test_registry_missing_file_warns(tmp_path, caplog):
       reg = RegistryOverlayStore()
       with caplog.at_level(logging.WARNING):
           reg.load(tmp_path / "nonexistent.toml")
       assert any("nonexistent" in r.message for r in caplog.records)

   def test_registry_orphan_warns(tmp_path, caplog):
       reg = RegistryOverlayStore()
       reg.load(write_registry_toml(tmp_path, {"Unknown.foo": {"en": "Bar"}}))
       with caplog.at_level(logging.WARNING):
           reg.validate_against({("MyObj", "gain")})
       assert any("orphan" in r.message.lower() for r in caplog.records)

--------------------------------------------------------------------------------
7. Phase 6 — ConfigController and Integration
--------------------------------------------------------------------------------

**Deliverables**

* ``ConfigController`` in ``synarius_studio/config/_controller.py`` (not in
  ``synarius_attr_config``; consuming-application responsibility).
* ``defaults.toml`` skeleton committed to ``synarius_studio/config/``.
* ``OptionsMenuWidget`` integrated into the Studio main window.
* End-to-end test using the example script (Section 8).

**Acceptance criteria**

* Editing a global option in the ``OptionsMenuWidget``, confirming with OK, and
  restarting the application loads the persisted value from ``settings.toml``.
* Cancelling the dialog leaves ``settings.toml`` unchanged.
* ``ConfigController.reset_all()`` deletes ``settings.toml``; next start loads
  defaults.
* ``lsattr -r`` in the CCP console of a running Studio instance lists global
  config attributes with ``[virtual]`` markers where applicable.
* The example script (Section 8) runs without error and exits cleanly.

--------------------------------------------------------------------------------
8. Example Script
--------------------------------------------------------------------------------

The runnable example script is located at:

   :doc:`examples/attr_config_demo`

It demonstrates:

* Creating stub model objects with ``AttributeEntry``, ``OptionMeta``, and
  ``GuiHint`` definitions.
* Opening a **local configuration dialog** (``AttribTableWidget`` in a
  ``QDialog``) and generating the resulting CCP ``set`` command.
* Opening the **global options menu** (``OptionsMenuWidget``) and writing the
  result to a temporary ``settings.toml``.
* A round-trip persistence test: write settings, reload, verify values match.

The script can be run in isolation after ``pip install synarius_attr_config
PySide6``:

.. code-block:: shell

   python docs/specifications/attribute_config/examples/attr_config_demo.py

.. toctree::
   :hidden:

   examples/attr_config_demo

--------------------------------------------------------------------------------
9. Test Strategy Summary
--------------------------------------------------------------------------------

.. list-table::
   :widths: 20 20 60
   :header-rows: 1

   * - Phase
     - Test type
     - Coverage target
   * - 1
     - Unit
     - ``OptionMeta`` / ``GuiHint`` construction, defaults, field disjointness
   * - 2
     - Unit
     - Virtual attribute read/write/delegation; absence from ``.syn``
   * - 3
     - Unit
     - ``AttribViewModel`` change tracking, validation, reset; persistence
       delta write and reset
   * - 4
     - Manual smoke + unit
     - Widget type inference (all branches); dialog OK/Cancel/reset flows
   * - 5
     - Unit
     - Registry overlay, missing file, orphan validation
   * - 6
     - Integration
     - End-to-end: edit → persist → reload; example script clean exit

No mocking of ``AttributeDict`` or ``TomlPersistenceLayer`` is used in
integration tests — real instances with temporary files are required (see
programming guidelines: integration tests must use real dependencies).

--------------------------------------------------------------------------------
10. Related Documents
--------------------------------------------------------------------------------

* :doc:`concept` — architectural principles and constraints.
* :doc:`architecture` — package structure and data-flow diagrams.
* :doc:`../attribute_dict` — ``AttributeDict`` / ``AttributeEntry`` reference.
* :doc:`../controller_command_protocol` — CCP ``set`` command semantics.
