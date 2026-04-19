"""
Attribute Configuration and Options Management — demonstration script.

Demonstrates both forms of configuration described in the concept
(docs/specifications/attribute_config/concept.rst):

  1. Local per-object configuration: both AttribTableWidget and AttribFormWidget
     shown in tabs, producing a CCP bulk-set command on OK.
  2. Global application configuration: OptionsMenuWidget with all widget types
     across multiple groups (Löser, Modell, Farben, Schrift, Zeitreihe),
     shown in two variants — table panels and form/grid panels.
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
from datetime import date
from pathlib import Path

from synarius_core.model.attribute_dict import AttributeEntry
from synarius_attr_config.meta import GuiHint, OptionMeta
from synarius_attr_config.persistence import TomlPersistenceLayer
from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets import AttribTableWidget, AttribFormWidget, OptionsMenuWidget

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QStyleFactory,
    QTabWidget,  # used in run_local_config_demo
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Local-config entries  (shown in Demo 1)
# ---------------------------------------------------------------------------

ENTRIES: list[tuple[str, AttributeEntry, OptionMeta, GuiHint]] = [
    (
        "gain",
        AttributeEntry.stored(1.0, exposed=True, writable=True, bounds=(0.0, 100.0)),
        OptionMeta(local=True, order=0),
        GuiHint(display_name="Gain", decimal_precision=4),
    ),
    (
        "offset",
        AttributeEntry.stored(0.0, exposed=True, writable=True, bounds=(-50.0, 50.0), unit="m"),
        OptionMeta(local=True, order=1),
        GuiHint(display_name="Offset"),
    ),
    (
        "enabled",
        AttributeEntry.stored(True, exposed=True, writable=True),
        OptionMeta(local=True, order=2),
        GuiHint(display_name="Enabled"),
    ),
    (
        "integration_method",
        AttributeEntry.stored(
            "RK4",
            exposed=True,
            writable=True,
            enum_values=["Euler", "RK2", "RK4", "RK45", "LSODA"],
        ),
        OptionMeta(local=True, order=3),
        GuiHint(display_name="Integration Method"),
    ),
    (
        "label",
        AttributeEntry.stored("block_1", exposed=True, writable=True),
        OptionMeta(local=True, order=4),
        GuiHint(display_name="Label"),
    ),
]


# ---------------------------------------------------------------------------
# Global-options entries  (shown in Demo 2 — all widget types, 5 groups)
# ---------------------------------------------------------------------------

GLOBAL_ENTRIES: list[tuple[str, AttributeEntry, OptionMeta, GuiHint]] = [

    # ---- Simulation / Löser -----------------------------------------------
    (
        "solver_enabled",
        AttributeEntry.stored(True, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Löser", order=0),
        GuiHint(display_name="Aktiviert"),
    ),
    (
        "step_size",
        AttributeEntry.stored(0.001, exposed=True, writable=True,
                              bounds=(0.00001, 1.0), unit="s"),
        OptionMeta(global_=True, global_path="Simulation/Löser", order=1),
        GuiHint(display_name="Schrittweite", decimal_precision=6),
    ),
    (
        "tolerance",
        AttributeEntry.stored(1e-6, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Löser", order=2),
        GuiHint(display_name="Toleranz", decimal_precision=9),
    ),
    (
        "integration_method",
        AttributeEntry.stored(
            "RK4",
            exposed=True,
            writable=True,
            enum_values=["Euler", "RK2", "RK4", "RK45", "LSODA"],
        ),
        OptionMeta(global_=True, global_path="Simulation/Löser", order=3),
        GuiHint(display_name="Integrationsverfahren"),
    ),
    (
        "integration_order",
        AttributeEntry.stored(
            "4", exposed=True, writable=True, enum_values=["1", "2", "4"],
        ),
        OptionMeta(global_=True, global_path="Simulation/Löser", order=4),
        GuiHint(display_name="Ordnung"),
    ),

    # ---- Simulation / Modell ----------------------------------------------
    (
        "model_name",
        AttributeEntry.stored("default_model", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Modell", order=0),
        GuiHint(display_name="Modellname"),
    ),
    (
        "model_path",
        AttributeEntry.stored(
            Path("/models/default.syn"), exposed=True, writable=True,
        ),
        OptionMeta(global_=True, global_path="Simulation/Modell", order=1),
        GuiHint(display_name="Modelldatei"),
    ),
    (
        "description",
        AttributeEntry.stored("Standard-Konfiguration", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Simulation/Modell", order=2),
        GuiHint(display_name="Beschreibung"),
    ),

    # ---- Darstellung / Farben ---------------------------------------------
    (
        "canvas_bg",
        AttributeEntry.stored("#f0f3f5", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Darstellung/Farben", order=0),
        GuiHint(display_name="Hintergrund", widget_type_override="color_picker"),
    ),
    (
        "grid_color",
        AttributeEntry.stored("#cccccc", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Darstellung/Farben", order=1),
        GuiHint(display_name="Rasterlinien", widget_type_override="color_picker"),
    ),
    (
        "selection_color",
        AttributeEntry.stored("#586cd4", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Darstellung/Farben", order=2),
        GuiHint(display_name="Selektion", widget_type_override="color_picker"),
    ),

    # ---- Darstellung / Schrift --------------------------------------------
    (
        "font_family",
        AttributeEntry.stored("Segoe UI", exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Darstellung/Schrift", order=0),
        GuiHint(display_name="Schriftart", widget_type_override="font_picker"),
    ),
    (
        "font_size",
        AttributeEntry.stored(10, exposed=True, writable=True, bounds=(6, 24), unit="pt"),
        OptionMeta(global_=True, global_path="Darstellung/Schrift", order=1),
        GuiHint(display_name="Schriftgröße"),
    ),

    # ---- Export / Zeitreihe -----------------------------------------------
    (
        "export_start",
        AttributeEntry.stored(date(2025, 1, 1), exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Export/Zeitreihe", order=0),
        GuiHint(display_name="Von"),
    ),
    (
        "export_end",
        AttributeEntry.stored(date(2025, 12, 31), exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Export/Zeitreihe", order=1),
        GuiHint(display_name="Bis"),
    ),
    (
        "export_path",
        AttributeEntry.stored(Path("/export/results"), exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Export/Zeitreihe", order=2),
        GuiHint(display_name="Ausgabepfad"),
    ),

    # ---- Erweitert / Numerik  (Tiefe 2) -----------------------------------
    (
        "num_basis_type",
        AttributeEntry.stored(
            "explizit", exposed=True, writable=True,
            enum_values=["explizit", "implizit", "semi-implizit"],
        ),
        OptionMeta(global_=True, global_path="Erweitert/Numerik", order=0),
        GuiHint(display_name="Basistyp"),
    ),
    (
        "num_max_steps",
        AttributeEntry.stored(10000, exposed=True, writable=True, bounds=(100, 1_000_000)),
        OptionMeta(global_=True, global_path="Erweitert/Numerik", order=1),
        GuiHint(display_name="Max. Schritte"),
    ),
    (
        "num_event_detect",
        AttributeEntry.stored(True, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Erweitert/Numerik", order=2),
        GuiHint(display_name="Ereigniserkennung"),
    ),

    # ---- Erweitert / Numerik / Integration  (Tiefe 3) ---------------------
    (
        "int_step_control",
        AttributeEntry.stored(True, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration", order=0),
        GuiHint(display_name="Schrittweiten-Kontrolle"),
    ),
    (
        "int_dense_output",
        AttributeEntry.stored(False, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration", order=1),
        GuiHint(display_name="Dichte Ausgabe"),
    ),
    (
        "int_safety_factor",
        AttributeEntry.stored(0.9, exposed=True, writable=True, bounds=(0.1, 1.0)),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration", order=2),
        GuiHint(display_name="Sicherheitsfaktor", decimal_precision=2),
    ),

    # ---- Erweitert / Numerik / Integration / Adams  (Tiefe 4) -------------
    (
        "adams_order",
        AttributeEntry.stored(
            "4", exposed=True, writable=True, enum_values=["1", "2", "3", "4", "5", "6"],
        ),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration/Adams", order=0),
        GuiHint(display_name="Ordnung"),
    ),
    (
        "adams_predictor",
        AttributeEntry.stored(
            "ABM", exposed=True, writable=True,
            enum_values=["ABM", "Milne", "Hamming"],
        ),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration/Adams", order=1),
        GuiHint(display_name="Prädiktor-Typ"),
    ),
    (
        "adams_startup",
        AttributeEntry.stored(
            "RK4", exposed=True, writable=True, enum_values=["Euler", "RK2", "RK4"],
        ),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration/Adams", order=2),
        GuiHint(display_name="Startverfahren"),
    ),

    # ---- Erweitert / Numerik / Integration / Adams / Korrektoren  (Tiefe 5)
    (
        "corr_iter_max",
        AttributeEntry.stored(3, exposed=True, writable=True, bounds=(1, 20)),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration/Adams/Korrektoren",
                   order=0),
        GuiHint(display_name="Max. Iterationen"),
    ),
    (
        "corr_tol",
        AttributeEntry.stored(1e-8, exposed=True, writable=True),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration/Adams/Korrektoren",
                   order=1),
        GuiHint(display_name="Toleranz", decimal_precision=10),
    ),
    (
        "corr_mode",
        AttributeEntry.stored(
            "PECE", exposed=True, writable=True, enum_values=["P", "PE", "PEC", "PECE"],
        ),
        OptionMeta(global_=True, global_path="Erweitert/Numerik/Integration/Adams/Korrektoren",
                   order=2),
        GuiHint(display_name="Modus"),
    ),
]


# ---------------------------------------------------------------------------
# Demo 1: local configuration dialog
# ---------------------------------------------------------------------------

def run_local_config_demo(parent: QWidget | None = None) -> None:
    """Show a local config dialog with table and form views; print the CCP command on OK."""
    vm = AttribViewModel(ENTRIES)

    dialog = QDialog(parent)
    dialog.setWindowTitle("Local Configuration — demo_block_1")
    layout = QVBoxLayout(dialog)

    tabs = QTabWidget()
    table_widget = AttribTableWidget(vm)
    tabs.addTab(table_widget, "Tabelle")
    tabs.addTab(AttribFormWidget(vm, dark=True), "Formular")
    layout.addWidget(tabs)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    dialog.adjustSize()
    dialog.resize(420, dialog.sizeHint().height())
    dialog.setMaximumHeight(dialog.sizeHint().height())

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
# Demo 2: global options — all widget types, two panel variants
# ---------------------------------------------------------------------------

def run_global_options_demo(
    persistence: TomlPersistenceLayer,
    parent: QWidget | None = None,
) -> None:
    """Show global options: 5 groups, all widget types."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("Global Options")
    dialog.resize(800, 600)
    layout = QVBoxLayout(dialog)

    options = OptionsMenuWidget(GLOBAL_ENTRIES, persistence)
    layout.addWidget(options)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        changes: dict = {}
        for vm in options.all_view_models():
            changes.update(vm.changed_values())
        if changes:
            persistence.write(changes)
            print(f"\n[Global options] Persisted: {changes}")
        else:
            print("\n[Global options] No changes.")
    else:
        print("\n[Global options] Cancelled.")


# ---------------------------------------------------------------------------
# Demo 3: TOML persistence round-trip (no GUI)
# ---------------------------------------------------------------------------

def run_persistence_roundtrip(tmp_dir: Path) -> None:
    """Write settings, reload, verify values match — no GUI required."""
    print("\n[Persistence round-trip]")
    defaults = {
        "gain": 1.0,
        "enabled": True,
        "integration_method": "RK4",
        "label": "block_1",
    }
    defaults_path = tmp_dir / "defaults.toml"
    settings_path = tmp_dir / "settings.toml"

    import tomli_w
    defaults_path.write_bytes(tomli_w.dumps(defaults).encode())

    layer = TomlPersistenceLayer(defaults_path, settings_path)
    layer.write({"gain": 5.0, "integration_method": "RK45"})

    reloaded = layer.load()
    assert reloaded["gain"] == 5.0, f"Expected 5.0, got {reloaded['gain']}"
    assert reloaded["integration_method"] == "RK45"
    assert reloaded["enabled"] is True
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

        run_persistence_roundtrip(tmp_dir)

        app = QApplication.instance() or QApplication(sys.argv)
        _apply_synarius_theme(app)

        import tomli_w
        defaults = {
            "solver_enabled": True,
            "step_size": 0.001,
            "tolerance": 1e-6,
            "integration_method": "RK4",
            "integration_order": "4",
            "model_name": "default_model",
            "description": "Standard-Konfiguration",
            "canvas_bg": "#f0f3f5",
            "grid_color": "#cccccc",
            "selection_color": "#586cd4",
            "font_family": "Segoe UI",
            "font_size": 10,
            "export_start": date(2025, 1, 1),
            "export_end": date(2025, 12, 31),
            "num_basis_type": "explizit",
            "num_max_steps": 10000,
            "num_event_detect": True,
            "int_step_control": True,
            "int_dense_output": False,
            "int_safety_factor": 0.9,
            "adams_order": "4",
            "adams_predictor": "ABM",
            "adams_startup": "RK4",
            "corr_iter_max": 3,
            "corr_tol": 1e-8,
            "corr_mode": "PECE",
        }
        defaults_path = tmp_dir / "global_defaults.toml"
        settings_path = tmp_dir / "global_settings.toml"
        defaults_path.write_bytes(tomli_w.dumps(defaults).encode())
        persistence = TomlPersistenceLayer(defaults_path, settings_path)

        print("\n--- Demo 1: Local configuration dialog ---")
        run_local_config_demo()

        print("\n--- Demo 2: Global options (all widget types) ---")
        run_global_options_demo(persistence)

        print("\nDone.")


if __name__ == "__main__":
    main()
