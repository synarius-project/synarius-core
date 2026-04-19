from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptionMeta:
    """Configuration role and structural placement of an :class:`AttributeEntry`.

    Describes *where* and *whether* an attribute participates in local and global
    configuration dialogs.  Must not contain any display or editor details —
    those belong exclusively in :class:`GuiHint`.

    Attributes
    ----------
    global_
        True if the attribute appears in the global application-configuration
        dialog (``OptionsMenuWidget``).
    global_path
        Forward-slash path used to build the options-menu tree, e.g.
        ``"Simulation/Solver"``.  Depth equals the number of path components.
        Ignored when ``global_`` is ``False``.
    local
        True if the attribute appears in per-object local configuration dialogs.
    order
        Integer sort key within the attribute's group.  Lower values sort first.
        ``None`` → alphabetical by display name after all ordered items.
    exposed_override
        When set, overrides ``AttributeEntry.exposed`` for GUI projection only.
        Has no effect on validation, simulation, or CCP semantics.  The
        underlying ``AttributeEntry.exposed`` value is never modified.
    gui_writable_override
        When set, overrides ``AttributeEntry.writable`` for the GUI widget only.
        ``True`` forces an editable widget; ``False`` forces a read-only widget.
    """

    global_: bool = False
    global_path: str = ""
    local: bool = True
    order: int | None = None
    exposed_override: bool | None = None
    gui_writable_override: bool | None = None


@dataclass
class GuiHint:
    """Presentation and editor hints for an :class:`AttributeEntry`.

    Describes *how* an attribute value is displayed and edited.  Never consulted
    for decisions outside the rendering pipeline.

    Attributes
    ----------
    display_name
        English label shown as the row header in attribute dialogs.  This is the
        sole string that the optional i18n registry may translate.
    widget_type_override
        When set, bypasses the automatic widget-type inference and forces a
        specific widget.  Valid values: ``"checkbox"``, ``"combobox"``,
        ``"radio"``, ``"spinbox"``, ``"slider+spinbox"``, ``"color_picker"``,
        ``"path_picker"``, ``"datepicker"``, ``"lineedit"``.
    decimal_precision
        Preferred number of decimal places for numeric spin-box widgets.
        ``None`` → framework default (typically 2).
    """

    display_name: str = ""
    widget_type_override: str | None = None
    decimal_precision: int | None = None
