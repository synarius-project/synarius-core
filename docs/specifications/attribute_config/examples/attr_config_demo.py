"""
Attribute Configuration and Options Management — demonstration script.

Demonstrates both forms of configuration described in the concept
(docs/specifications/attribute_config/concept.rst):

  1. Local per-object configuration via AttribTableWidget in a QDialog,
     producing a CCP bulk-set command on OK.
  2. Global application configuration via OptionsMenuWidget, persisting the
     result to a temporary settings.toml.
  3. A TOML persistence round-trip: write → reload → verify.

This script uses *stub implementations* of synarius_attr_config classes
because the package does not exist yet.  Each stub class implements exactly
the interface specified in the architecture document
(docs/specifications/attribute_config/architecture.rst).  When the real
package is available, replace the stub imports with::

    from synarius_attr_config import OptionMeta, GuiHint, AttribViewModel, TomlPersistenceLayer
    from synarius_attr_config.widgets import AttribTableWidget, OptionsMenuWidget

Usage::

    python attr_config_demo.py

Requirements: PySide6 >= 6.0.0, tomli-w
"""
from __future__ import annotations

import logging
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Stub: synarius_core.AttributeEntry
# ---------------------------------------------------------------------------

@dataclass
class AttributeEntry:
    value: Any
    exposed: bool = True
    writable: bool = True
    bounds: tuple[float, float] | None = None
    unit: str = ""
    enum_values: list[str] | None = None
    docstring: str = ""
    virtual: bool = False


# ---------------------------------------------------------------------------
# Stub: synarius_attr_config._meta
# ---------------------------------------------------------------------------

@dataclass
class OptionMeta:
    global_: bool = False
    global_path: str = ""
    local: bool = True
    order: int | None = None
    exposed_override: bool | None = None
    gui_writable_override: bool | None = None


@dataclass
class GuiHint:
    display_name: str = ""
    widget_type_override: str | None = None
    decimal_precision: int | None = None


# ---------------------------------------------------------------------------
# Stub: synarius_attr_config._persistence.TomlPersistenceLayer
# ---------------------------------------------------------------------------

class TomlPersistenceLayer:
    def __init__(self, defaults_path: Path, settings_path: Path) -> None:
        self._defaults_path = defaults_path
        self._settings_path = settings_path

    def load(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        settings: dict[str, Any] = {}
        if self._defaults_path.exists():
            defaults = tomllib.loads(self._defaults_path.read_text("utf-8"))
        if self._settings_path.exists():
            settings = tomllib.loads(self._settings_path.read_text("utf-8"))
        return {**defaults, **settings}

    def write(self, changes: dict[str, Any]) -> None:
        import tomli_w
        existing: dict[str, Any] = {}
        if self._settings_path.exists():
            existing = tomllib.loads(self._settings_path.read_text("utf-8"))
        existing.update(changes)
        self._settings_path.write_bytes(tomli_w.dumps(existing).encode())

    def reset_attribute(self, key: str) -> None:
        import tomli_w
        if not self._settings_path.exists():
            return
        data = tomllib.loads(self._settings_path.read_text("utf-8"))
        data.pop(key, None)
        self._settings_path.write_bytes(tomli_w.dumps(data).encode())

    def reset_all(self) -> None:
        if self._settings_path.exists():
            self._settings_path.unlink()

    def has_default(self, key: str) -> bool:
        if not self._defaults_path.exists():
            return False
        return key in tomllib.loads(self._defaults_path.read_text("utf-8"))

    def default_value(self, key: str) -> Any | None:
        if not self._defaults_path.exists():
            return None
        return tomllib.loads(self._defaults_path.read_text("utf-8")).get(key)


# ---------------------------------------------------------------------------
# Stub: synarius_attr_config._view_model.AttribViewModel
# ---------------------------------------------------------------------------

class ValidationResult:
    def __init__(self, ok: bool, message: str = "") -> None:
        self.ok = ok
        self.message = message


class AttribViewModel:
    def __init__(
        self,
        entries: list[tuple[str, AttributeEntry, OptionMeta | None, GuiHint | None]],
        persistence: TomlPersistenceLayer | None = None,
    ) -> None:
        self._entries = {key: (entry, om, gh) for key, entry, om, gh in entries}
        self._original: dict[str, Any] = {k: v.value for k, (v, _, _) in self._entries.items()}
        self._pending: dict[str, Any] = dict(self._original)
        self._persistence = persistence

    def set_pending(self, key: str, value: Any) -> None:
        self._pending[key] = value

    def revert_pending(self, key: str) -> None:
        self._pending[key] = self._original[key]

    def changed_values(self) -> dict[str, Any]:
        return {k: v for k, v in self._pending.items() if v != self._original[k]}

    def has_pending_changes(self) -> bool:
        return bool(self.changed_values())

    def validate(self, key: str) -> ValidationResult:
        entry = self._entries[key][0]
        value = self._pending[key]
        if entry.bounds and isinstance(value, (int, float)):
            lo, hi = entry.bounds
            if not (lo <= value <= hi):
                return ValidationResult(False, f"{value} not in [{lo}, {hi}]")
        if entry.enum_values and value not in entry.enum_values:
            return ValidationResult(False, f"{value!r} not in {entry.enum_values}")
        return ValidationResult(True)

    def has_errors(self) -> bool:
        return any(not self.validate(k).ok for k in self._pending)

    def reset_to_default(self, key: str) -> None:
        if self._persistence and self._persistence.has_default(key):
            self._pending[key] = self._persistence.default_value(key)
            self._persistence.reset_attribute(key)

    def display_name(self, key: str) -> str:
        gh = self._entries[key][2]
        if gh and gh.display_name:
            return gh.display_name
        return key

    def effective_exposed(self, key: str) -> bool:
        entry, om, _ = self._entries[key]
        if om and om.exposed_override is not None:
            return om.exposed_override
        return entry.exposed

    def effective_writable(self, key: str) -> bool:
        entry, om, _ = self._entries[key]
        if om and om.gui_writable_override is not None:
            return om.gui_writable_override
        return entry.writable


# ---------------------------------------------------------------------------
# Stub: widget-type inference
# ---------------------------------------------------------------------------

def _infer_widget_type(entry: AttributeEntry, hint: GuiHint) -> str:
    if hint.widget_type_override:
        return hint.widget_type_override
    if entry.enum_values:
        return "radio" if len(entry.enum_values) <= 3 else "combobox"
    if isinstance(entry.value, bool):
        return "checkbox"
    if isinstance(entry.value, (int, float)):
        return "slider+spinbox" if entry.bounds else "spinbox"
    return "lineedit"


# ---------------------------------------------------------------------------
# Stub: AttribTableWidget (PySide6)
# ---------------------------------------------------------------------------

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSlider, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt


class AttribTableWidget(QWidget):
    """Stub implementation of the AttribTableWidget concept class.

    Three-column layout: display name | value widget | unit.
    """

    def __init__(self, view_model: AttribViewModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._value_widgets: dict[str, QWidget] = {}
        layout = QGridLayout(self)
        layout.setColumnStretch(1, 1)

        for row, key in enumerate(view_model._entries):
            if not view_model.effective_exposed(key):
                continue
            entry, om, gh = view_model._entries[key]
            widget_type = _infer_widget_type(entry, gh or GuiHint())

            name_label = QLabel(view_model.display_name(key))
            layout.addWidget(name_label, row, 0)

            value_widget = self._make_value_widget(key, entry, widget_type, view_model.effective_writable(key))
            self._value_widgets[key] = value_widget
            layout.addWidget(value_widget, row, 1)

            unit_label = QLabel(entry.unit)
            layout.addWidget(unit_label, row, 2)

    def _make_value_widget(
        self,
        key: str,
        entry: AttributeEntry,
        widget_type: str,
        writable: bool,
    ) -> QWidget:
        if widget_type == "checkbox":
            w = QCheckBox()
            w.setChecked(bool(entry.value))
            w.setEnabled(writable)
            w.stateChanged.connect(lambda state, k=key: self._vm.set_pending(k, bool(state)))
            return w
        if widget_type in ("slider+spinbox", "spinbox"):
            w = QDoubleSpinBox()
            if entry.bounds:
                w.setMinimum(entry.bounds[0])
                w.setMaximum(entry.bounds[1])
            w.setValue(float(entry.value))
            w.setEnabled(writable)
            w.valueChanged.connect(lambda v, k=key: self._vm.set_pending(k, v))
            return w
        if widget_type == "combobox":
            w = QComboBox()
            for item in (entry.enum_values or []):
                w.addItem(item)
            idx = (entry.enum_values or []).index(entry.value) if entry.value in (entry.enum_values or []) else 0
            w.setCurrentIndex(idx)
            w.setEnabled(writable)
            w.currentTextChanged.connect(lambda v, k=key: self._vm.set_pending(k, v))
            return w
        w = QLineEdit(str(entry.value))
        w.setEnabled(writable)
        w.textChanged.connect(lambda v, k=key: self._vm.set_pending(k, v))
        return w


# ---------------------------------------------------------------------------
# Stub: OptionsMenuWidget (PySide6)
# ---------------------------------------------------------------------------

class OptionsMenuWidget(QWidget):
    """Stub implementation of the OptionsMenuWidget concept class.

    Left: QTreeWidget built from OptionMeta.global_path.
    Right: stacked AttribTableWidget per tree node.
    """

    def __init__(
        self,
        global_entries: list[tuple[str, AttributeEntry, OptionMeta, GuiHint]],
        persistence: TomlPersistenceLayer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._persistence = persistence
        self._group_vms: dict[str, AttribViewModel] = {}

        # Group entries by global_path
        groups: dict[str, list] = {}
        for key, entry, om, gh in global_entries:
            groups.setdefault(om.global_path or "(root)", []).append((key, entry, om, gh))

        for path, entries in groups.items():
            self._group_vms[path] = AttribViewModel(entries, persistence=persistence)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(splitter)

        # Left: tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        tree_nodes: dict[str, QTreeWidgetItem] = {}
        for path in sorted(groups):
            parts = path.split("/")
            parent_item = None
            for depth, part in enumerate(parts):
                node_key = "/".join(parts[: depth + 1])
                if node_key not in tree_nodes:
                    item = QTreeWidgetItem([part])
                    if parent_item is None:
                        self._tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    item.setData(0, Qt.ItemDataRole.UserRole, path if depth == len(parts) - 1 else None)
                    tree_nodes[node_key] = item
                parent_item = tree_nodes[node_key]
        self._tree.expandAll()
        splitter.addWidget(self._tree)

        # Right: scroll area with stacked table widgets
        right = QScrollArea()
        right.setWidgetResizable(True)
        right_container = QWidget()
        self._right_layout = QVBoxLayout(right_container)
        right.setWidget(right_container)
        splitter.addWidget(right)

        # Show first group by default
        self._current_table: AttribTableWidget | None = None
        self._path_to_table: dict[str, AttribTableWidget] = {}
        for path, vm in self._group_vms.items():
            table = AttribTableWidget(vm)
            self._path_to_table[path] = table
            self._right_layout.addWidget(table)
            table.hide()
        if self._path_to_table:
            first = next(iter(self._path_to_table))
            self._path_to_table[first].show()
            self._current_table = self._path_to_table[first]

        self._tree.currentItemChanged.connect(self._on_tree_selection)

    def _on_tree_selection(self, current: QTreeWidgetItem, _previous: QTreeWidgetItem) -> None:
        path = current.data(0, Qt.ItemDataRole.UserRole)
        if path and path in self._path_to_table:
            if self._current_table:
                self._current_table.hide()
            self._current_table = self._path_to_table[path]
            self._current_table.show()

    def all_view_models(self) -> list[AttribViewModel]:
        return list(self._group_vms.values())


# ---------------------------------------------------------------------------
# Demo model object
# ---------------------------------------------------------------------------

ENTRIES: list[tuple[str, AttributeEntry, OptionMeta, GuiHint]] = [
    (
        "gain",
        AttributeEntry(value=1.0, exposed=True, writable=True, bounds=(0.0, 100.0), unit=""),
        OptionMeta(global_=True, global_path="Simulation/Solver", local=True, order=1),
        GuiHint(display_name="Gain", decimal_precision=4),
    ),
    (
        "offset",
        AttributeEntry(value=0.0, exposed=True, writable=True, bounds=(-50.0, 50.0), unit="m"),
        OptionMeta(global_=False, local=True),
        GuiHint(display_name="Offset"),
    ),
    (
        "model_name",
        AttributeEntry(value="default_model", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Model", local=True),
        GuiHint(display_name="Model Name"),
    ),
    (
        "enabled",
        AttributeEntry(value=True, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Solver", local=True, order=0),
        GuiHint(display_name="Solver Enabled"),
    ),
    (
        "integration_method",
        AttributeEntry(
            value="RK4",
            exposed=True,
            writable=True,
            enum_values=["Euler", "RK2", "RK4", "RK45", "LSODA"],
        ),
        OptionMeta(global_=True, global_path="Simulation/Solver", local=True, order=2),
        GuiHint(display_name="Integration Method"),
    ),
]


# ---------------------------------------------------------------------------
# Demo: local configuration dialog
# ---------------------------------------------------------------------------

def run_local_config_demo(parent: QWidget | None = None) -> None:
    """Show a local config dialog for the demo object and print the CCP command."""
    local_entries = [(k, e, om, gh) for k, e, om, gh in ENTRIES if om.local]
    vm = AttribViewModel(local_entries)

    dialog = QDialog(parent)
    dialog.setWindowTitle("Local Configuration — demo_block_1")
    layout = QVBoxLayout(dialog)

    table = AttribTableWidget(vm)
    layout.addWidget(table)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        changes = vm.changed_values()
        if changes:
            ccp_cmd = f"set demo_block_1 {changes!r}"
            print(f"\n[Local config] CCP command:\n  {ccp_cmd}")
        else:
            print("\n[Local config] No changes; no CCP command emitted.")
    else:
        print("\n[Local config] Cancelled.")


# ---------------------------------------------------------------------------
# Demo: global options menu
# ---------------------------------------------------------------------------

def run_global_options_demo(
    persistence: TomlPersistenceLayer,
    parent: QWidget | None = None,
) -> None:
    """Show the global OptionsMenuWidget and persist changes to settings.toml."""
    global_entries = [(k, e, om, gh) for k, e, om, gh in ENTRIES if om.global_]

    dialog = QDialog(parent)
    dialog.setWindowTitle("Global Options")
    dialog.resize(700, 400)
    layout = QVBoxLayout(dialog)

    options_widget = OptionsMenuWidget(global_entries, persistence=persistence)
    layout.addWidget(options_widget)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        any_changes = False
        for vm in options_widget.all_view_models():
            changes = vm.changed_values()
            if changes:
                persistence.write(changes)
                print(f"\n[Global options] Persisted: {changes}")
                any_changes = True
        if not any_changes:
            print("\n[Global options] No changes.")
    else:
        print("\n[Global options] Cancelled.")


# ---------------------------------------------------------------------------
# Demo: TOML persistence round-trip
# ---------------------------------------------------------------------------

def run_persistence_roundtrip(tmp_dir: Path) -> None:
    """Write settings, reload, verify values match — no GUI required."""
    print("\n[Persistence round-trip]")
    defaults = {"gain": 1.0, "enabled": True, "integration_method": "RK4", "model_name": "default_model"}
    defaults_path = tmp_dir / "defaults.toml"
    settings_path = tmp_dir / "settings.toml"

    import tomli_w
    defaults_path.write_bytes(tomli_w.dumps(defaults).encode())

    layer = TomlPersistenceLayer(defaults_path, settings_path)
    layer.write({"gain": 5.0, "integration_method": "RK45"})

    reloaded = layer.load()
    assert reloaded["gain"] == 5.0, f"Expected 5.0, got {reloaded['gain']}"
    assert reloaded["integration_method"] == "RK45"
    assert reloaded["enabled"] is True   # from defaults
    print(f"  Reloaded settings: {reloaded}")

    layer.reset_attribute("gain")
    after_reset = layer.load()
    assert after_reset["gain"] == 1.0, f"Expected 1.0 after reset, got {after_reset['gain']}"
    print(f"  After reset_attribute('gain'): gain = {after_reset['gain']}")

    layer.reset_all()
    after_full_reset = layer.load()
    assert after_full_reset == defaults, f"Expected defaults, got {after_full_reset}"
    print("  After reset_all(): settings match defaults.")
    print("[Persistence round-trip] PASSED")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Persistence round-trip (no GUI)
        run_persistence_roundtrip(tmp_dir)

        # GUI demos
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        import tomli_w
        defaults = {
            "gain": 1.0,
            "enabled": True,
            "integration_method": "RK4",
            "model_name": "default_model",
        }
        defaults_path = tmp_dir / "defaults.toml"
        settings_path = tmp_dir / "settings.toml"
        defaults_path.write_bytes(tomli_w.dumps(defaults).encode())
        persistence = TomlPersistenceLayer(defaults_path, settings_path)

        print("\n--- Demo 1: Local configuration dialog ---")
        run_local_config_demo()

        print("\n--- Demo 2: Global options menu ---")
        run_global_options_demo(persistence)

        print("\nDone.")


if __name__ == "__main__":
    main()
