"""Declarative layout templates for attribute-configuration Qt widgets.

The widgets still build concrete ``QWidget`` / layout instances in code; these
dataclasses centralise **geometry and chrome** (margins, stretches, tab labels,
splitter sizes) so layouts can be copied, tested, and customised without hunting
through imperative ``set*`` calls scattered across multiple files.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHeaderView,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
)


@dataclass(frozen=True)
class FormLayoutTemplate:
    """Two-column grid: display name (left) | value widget (right)."""

    name_column: int = 0
    value_column: int = 1
    name_column_min_width_px: int = 150
    value_column_stretch: int = 1


@dataclass(frozen=True)
class TableLayoutTemplate:
    """Column chrome for :class:`~synarius_attr_config.widgets.AttribTableWidget`."""

    header_labels: tuple[str, str] = ("Attribut", "Wert")
    first_column_width_px: int = 150
    min_first_column_width_px: int = 40
    stretch_last_section: bool = True
    first_column_resize_mode: QHeaderView.ResizeMode = field(
        default_factory=lambda: QHeaderView.ResizeMode.Interactive
    )
    #: Outer ``QMargins`` (left, top, right, bottom) for **all** value widgets in
    #: the second column (applied via a wrapper ``QWidget``), matching the
    #: previous ad-hoc checkbox inset.
    value_cell_margins_ltrb: tuple[int, int, int, int] = (6, 0, 0, 0)
    #: Border colour shared by spin-boxes, combo-boxes, line edits, buttons in
    #: the value column (light table theme), and :class:`QCheckBox` indicators.
    #: (Variante 1: canonical source for value-column borders; see _table_widget.)
    value_border_color_light: str = "#4a7a9a"
    #: Same as :attr:`value_border_color_light` for the dark / Raster theme.
    value_border_color_dark: str = "#5a5a5a"
    #: Minimum edit-field width of numeric spin-boxes expressed as a character
    #: count.  The widget builder converts this to pixels via
    #: ``QFontMetrics.horizontalAdvance`` so the width scales with the font.
    #: Qt renders the suffix (unit) on top of this minimum, so the spinbox
    #: always has room for ``spinbox_min_contents_length`` digits *plus* the unit.
    spinbox_min_contents_length: int = 12


@dataclass(frozen=True)
class OptionsMenuShellTemplate:
    """Shell around :class:`~synarius_attr_config.widgets.OptionsMenuWidget`.

    Describes tabs, splitter behaviour, scroll-area padding, and how group
    paths are formatted into human-readable titles.
    """

    tab_label_table: str = "Tabelle"
    tab_label_form: str = "Raster"
    splitter_sizes: tuple[int, int] = (200, 400)
    splitter_stretch_tree: int = 1
    splitter_stretch_content: int = 2
    scroll_contents_margins_ltrb: tuple[int, int, int, int] = (4, 4, 4, 4)
    scroll_vertical_spacing: int = 8
    form_panel_title_spacing: int = 2
    form_panel_path_separator: str = " › "
    tree_header_hidden: bool = True
    form_title_size_policy_h: QSizePolicy.Policy = field(
        default_factory=lambda: QSizePolicy.Policy.Expanding
    )
    form_title_size_policy_v: QSizePolicy.Policy = field(
        default_factory=lambda: QSizePolicy.Policy.Minimum
    )


DEFAULT_FORM_LAYOUT = FormLayoutTemplate()
DEFAULT_TABLE_LAYOUT = TableLayoutTemplate()
DEFAULT_OPTIONS_MENU_SHELL = OptionsMenuShellTemplate()


def apply_form_layout_template(
    layout: QGridLayout, template: FormLayoutTemplate = DEFAULT_FORM_LAYOUT
) -> None:
    layout.setColumnMinimumWidth(template.name_column, template.name_column_min_width_px)
    layout.setColumnStretch(template.value_column, template.value_column_stretch)


def apply_table_layout_template(
    table: QTableWidget, template: TableLayoutTemplate = DEFAULT_TABLE_LAYOUT
) -> None:
    """Apply header labels and column sizing to a configured ``QTableWidget``."""
    if not isinstance(table, QTableWidget):
        raise TypeError("expected QTableWidget")
    table.setHorizontalHeaderLabels(list(template.header_labels))
    hh = table.horizontalHeader()
    hh.setStretchLastSection(template.stretch_last_section)
    hh.setSectionResizeMode(0, template.first_column_resize_mode)
    table.setColumnWidth(0, template.first_column_width_px)


def format_options_group_title(path: str, shell: OptionsMenuShellTemplate) -> str:
    """Turn ``Simulation/Löser`` into a single-line title using *shell* separators."""
    return path.replace("/", shell.form_panel_path_separator)


def apply_options_splitter_template(
    splitter: QSplitter, shell: OptionsMenuShellTemplate = DEFAULT_OPTIONS_MENU_SHELL
) -> None:
    splitter.setOrientation(Qt.Orientation.Horizontal)
    splitter.setStretchFactor(0, shell.splitter_stretch_tree)
    splitter.setStretchFactor(1, shell.splitter_stretch_content)
    splitter.setSizes(list(shell.splitter_sizes))


def apply_options_scroll_layout(
    layout: QVBoxLayout, shell: OptionsMenuShellTemplate = DEFAULT_OPTIONS_MENU_SHELL
) -> None:
    m = shell.scroll_contents_margins_ltrb
    layout.setContentsMargins(m[0], m[1], m[2], m[3])
    layout.setSpacing(shell.scroll_vertical_spacing)
