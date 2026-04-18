"""
Attribute Configuration and Options Management — demonstration script.

Demonstrates both forms of configuration described in the concept
(docs/specifications/attribute_config/concept.rst):

  1. Local per-object configuration: both AttribTableWidget and AttribFormWidget
     shown in tabs, producing a CCP bulk-set command on OK.
  2. Global application configuration: OptionsMenuWidget plus both flat views
     in tabs, persisting the result to a temporary settings.toml.
  3. A TOML persistence round-trip: write → reload → verify.

Usage::

    python attr_config_demo.py

Requirements: PySide6 >= 6.0.0, tomli-w
Optional: synarius-studio (for the standard dark palette)
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

from synarius_core.model.attribute_dict import AttributeEntry
from synarius_attr_config.meta import GuiHint, OptionMeta
from synarius_attr_config.persistence import TomlPersistenceLayer
from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets import AttribFormWidget, AttribTableWidget, OptionsMenuWidget

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QStyleFactory,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Demo model entries
# ---------------------------------------------------------------------------

ENTRIES: list[tuple[str, AttributeEntry, OptionMeta, GuiHint]] = [
    (
        "gain",
        AttributeEntry.stored(1.0, exposed=True, writable=True, bounds=(0.0, 100.0)),
        OptionMeta(global_=True, global_path="Simulation/Solver", local=True, order=1),
        GuiHint(display_name="Gain", decimal_precision=4),
    ),
    (
        "offset",
        AttributeEntry.stored(0.0, exposed=True, writable=True, bounds=(-50.0, 50.0), unit="m"),
        OptionMeta(global_=False, local=True),
        GuiHint(display_name="Offset"),
    ),
    (
        "model_name",
        AttributeEntry.stored("default_model", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Model", local=True),
        GuiHint(display_name="Model Name"),
    ),
    (
        "enabled",
        AttributeEntry.stored(True, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Solver", local=True, order=0),
        GuiHint(display_name="Solver Enabled"),
    ),
    (
        "integration_method",
        AttributeEntry.stored(
            "RK4",
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
    """Show a local config dialog with table and form views; print the CCP command on OK."""
    local_entries = [(k, e, om, gh) for k, e, om, gh in ENTRIES if om.local]
    vm = AttribViewModel(local_entries)

    dialog = QDialog(parent)
    dialog.setWindowTitle("Local Configuration — demo_block_1")
    dialog.resize(550, 300)
    layout = QVBoxLayout(dialog)

    tabs = QTabWidget()
    tabs.addTab(AttribTableWidget(vm), "Tabelle")
    tabs.addTab(AttribFormWidget(vm), "Formular")
    layout.addWidget(tabs)

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
    """Show global options in three tabs: Optionsmenü, Tabelle, Formular."""
    global_entries = [(k, e, om, gh) for k, e, om, gh in ENTRIES if om.global_]
    # Shared vm for the flat views (Tabelle + Formular); OptionsMenuWidget manages its own vms.
    vm_flat = AttribViewModel(global_entries, persistence=persistence)

    dialog = QDialog(parent)
    dialog.setWindowTitle("Global Options")
    dialog.resize(750, 480)
    layout = QVBoxLayout(dialog)

    tabs = QTabWidget()
    options_widget = OptionsMenuWidget(global_entries, persistence)
    tabs.addTab(options_widget, "Optionsmenü")
    tabs.addTab(AttribTableWidget(vm_flat), "Tabelle")
    tabs.addTab(AttribFormWidget(vm_flat), "Formular")
    layout.addWidget(tabs)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        # Collect changes from the active view; prefer flat vm, supplement from OptionsMenuWidget.
        changes: dict = dict(vm_flat.changed_values())
        for vm in options_widget.all_view_models():
            for k, v in vm.changed_values().items():
                changes.setdefault(k, v)
        if changes:
            persistence.write(changes)
            print(f"\n[Global options] Persisted: {changes}")
        else:
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

def _apply_synarius_theme(app: QApplication) -> None:
    """Apply the standard Synarius dark palette (Fusion + synarius_studio theme)."""
    app.setStyle(QStyleFactory.create("Fusion"))
    try:
        from synarius_studio.theme import apply_dark_palette
        apply_dark_palette(app)
    except ImportError:
        pass


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Persistence round-trip (no GUI)
        run_persistence_roundtrip(tmp_dir)

        # GUI demos
        app = QApplication.instance() or QApplication(sys.argv)
        _apply_synarius_theme(app)

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
