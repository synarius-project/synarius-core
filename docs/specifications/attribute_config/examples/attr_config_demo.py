"""
Attribute Configuration and Options Management — demonstration script.

Demonstrates both forms of configuration described in the concept
(docs/specifications/attribute_config/concept.rst):

  1. Local per-object configuration via AttribTableWidget in a QDialog,
     producing a CCP bulk-set command on OK.
  2. Global application configuration via OptionsMenuWidget, persisting the
     result to a temporary settings.toml.
  3. A TOML persistence round-trip: write → reload → verify.

Usage::

    python attr_config_demo.py

Requirements: PySide6 >= 6.0.0, tomli-w
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
from synarius_attr_config.widgets import AttribTableWidget, OptionsMenuWidget

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
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

    options_widget = OptionsMenuWidget(global_entries, persistence)
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
