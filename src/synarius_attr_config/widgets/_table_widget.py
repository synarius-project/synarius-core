from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from synarius_attr_config.meta import GuiHint
from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets._inference import infer_widget_type

# ---------------------------------------------------------------------------
# Synarius light-blue table palette
# Mirrors RESOURCES_PANEL_BACKGROUND in synarius_studio.theme.
# ---------------------------------------------------------------------------
_ROW_BG = "#c8e3fb"
_ROW_ALT_BG = "#b4cce2"        # _ROW_BG × 0.90
_NAME_COL_BG = "#8ab0c8"       # parameter column — clearly darker than _ROW_BG
_NAME_COL_ALT_BG = "#7aa3bc"   # parameter column alternating row
_GRID_COLOR = "#9ab8cf"
_TEXT_COLOR = "#1a1a1a"
_HEADER_BG = "#353535"
_HEADER_FG = "#ffffff"
_HEADER_SEP = "#505050"
_SEL_BG = "#586cd4"
_SEL_FG = "#ffffff"

_TOOLTIP_QSS = (
    "QToolTip { color: #ffffff !important; background-color: #2b2b2b !important;"
    " border: 1px solid #5a5a5a !important; padding: 4px 6px !important; }"
)
_TABLE_QSS = (
    f"QTableWidget {{ background-color: {_ROW_BG}; alternate-background-color: {_ROW_ALT_BG};"
    f" color: {_TEXT_COLOR}; gridline-color: {_GRID_COLOR}; border: 1px solid {_GRID_COLOR}; }}"
    f"QTableWidget::item:selected {{ background-color: {_SEL_BG}; color: {_SEL_FG}; }}"
    f"QHeaderView::section {{ background-color: {_HEADER_BG}; color: {_HEADER_FG};"
    f" padding: 4px 6px; border: none; border-right: 1px solid {_HEADER_SEP}; }}"
    f" {_TOOLTIP_QSS}"
)

# QSS applied to every cell-value widget so it blends into the blue table background.
_CELL_QSS = (
    f"QWidget {{ background-color: transparent; }}"
    f"QDoubleSpinBox, QSpinBox, QLineEdit, QDateEdit {{"
    f" background-color: {_ROW_BG}; color: {_TEXT_COLOR};"
    f" border: 1px solid {_GRID_COLOR}; border-radius: 2px;"
    f" selection-background-color: {_SEL_BG}; selection-color: {_SEL_FG}; }}"
    f"QComboBox {{"
    f" background-color: {_ROW_BG}; color: {_TEXT_COLOR};"
    f" border: 1px solid {_GRID_COLOR}; border-radius: 2px; }}"
    f"QComboBox QAbstractItemView {{"
    f" background-color: {_ROW_BG}; color: {_TEXT_COLOR};"
    f" selection-background-color: {_SEL_BG}; selection-color: {_SEL_FG}; }}"
    f"QCheckBox {{ color: {_TEXT_COLOR}; }}"
    f"QRadioButton {{ color: {_TEXT_COLOR}; }}"
    f"QSlider::groove:horizontal {{"
    f" background: {_GRID_COLOR}; height: 4px; border-radius: 2px; }}"
    f"QSlider::handle:horizontal {{"
    f" background: {_SEL_BG}; width: 12px; height: 12px;"
    f" border-radius: 6px; margin: -4px 0; }}"
    f"QPushButton {{"
    f" background-color: {_ROW_ALT_BG}; color: {_TEXT_COLOR};"
    f" border: 1px solid {_GRID_COLOR}; border-radius: 2px; padding: 2px 6px; }}"
    f"QPushButton:hover {{ background-color: {_GRID_COLOR}; }}"
    f" {_TOOLTIP_QSS}"
)


def _text_for_bg(hex_bg: str) -> str:
    """Return '#000000' or '#ffffff' depending on which gives better contrast on *hex_bg*."""
    s = hex_bg.strip().removeprefix("#")
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    luminance = (r * 299 + g * 587 + b * 114) // 1000
    return "#000000" if luminance > 128 else "#ffffff"


class AttribTableWidget(QTableWidget):
    """Attribute table view backed by an :class:`AttribViewModel`.

    Three columns: *display name* | *value widget* | *unit*.

    Only attributes where ``view_model.effective_exposed(key)`` is ``True``
    are rendered.  Rows are not editable via double-click; all editing is done
    through the embedded value widgets.

    A right-click context menu on any row with a default value offers
    *Reset to default*.

    Parameters
    ----------
    view_model
        The projected attribute set to display.
    alternating_rows
        When ``True`` (default) every second row uses a slightly darker background
        and the parameter column uses its own two-tone shading.  Pass ``False`` to
        disable alternating colours.
    """

    _COL_NAME = 0
    _COL_VALUE = 1

    def __init__(
        self,
        view_model: AttribViewModel,
        alternating_rows: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._alternating_rows = alternating_rows
        self._row_keys: list[str] = []
        self._value_widgets: dict[str, QWidget] = {}

        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setAlternatingRowColors(alternating_rows)
        self.setStyleSheet(_TABLE_QSS)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().setVisible(False)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._populate()

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        visible_keys = [k for k in self._vm.keys if self._vm.effective_exposed(k)]
        self._row_keys = visible_keys
        self.setRowCount(len(visible_keys))

        for row, key in enumerate(visible_keys):
            entry = self._vm._entries[key][0]
            gh = self._vm._entries[key][2]
            hint = gh if gh is not None else GuiHint()

            name_item = QTableWidgetItem(self._vm.display_name(key))
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            name_bg = (_NAME_COL_ALT_BG if self._alternating_rows and row % 2 == 1
                       else _NAME_COL_BG)
            name_item.setBackground(QBrush(QColor(name_bg)))
            self.setItem(row, self._COL_NAME, name_item)

            widget_type = infer_widget_type(entry, hint)
            value_widget = self._make_value_widget(
                key, widget_type, self._vm.effective_writable(key)
            )
            self._value_widgets[key] = value_widget
            self.setCellWidget(row, self._COL_VALUE, value_widget)

        self.resizeRowsToContents()

    def _make_value_widget(self, key: str, widget_type: str, writable: bool) -> QWidget:
        entry = self._vm._entries[key][0]
        gh = self._vm._entries[key][2]
        value = self._vm.pending_value(key)

        w = self._build_value_widget(key, entry, gh, widget_type, writable, value)
        w.setStyleSheet(_CELL_QSS)
        return w

    def _build_value_widget(
        self,
        key: str,
        entry: Any,
        gh: GuiHint | None,
        widget_type: str,
        writable: bool,
        value: Any,
    ) -> QWidget:
        if widget_type == "checkbox":
            w = QCheckBox()
            w.setChecked(bool(value))
            w.setEnabled(writable)
            w.checkStateChanged.connect(
                lambda state, k=key: self._vm.set_pending(k, state == Qt.CheckState.Checked)
            )
            return w

        if widget_type in ("spinbox", "slider+spinbox"):
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)

            spinbox = QDoubleSpinBox()
            spinbox.setDecimals(
                gh.decimal_precision if gh and gh.decimal_precision is not None else 4
            )
            if entry.unit:
                spinbox.setSuffix(f" {entry.unit}")
            spinbox.setEnabled(writable)
            if entry.bounds is not None:
                spinbox.setMinimum(entry.bounds[0])
                spinbox.setMaximum(entry.bounds[1])
            else:
                spinbox.setMinimum(-1e18)
                spinbox.setMaximum(1e18)
            spinbox.setValue(float(value))
            spinbox.valueChanged.connect(lambda v, k=key: self._vm.set_pending(k, v))

            if widget_type == "slider+spinbox" and entry.bounds is not None:
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setEnabled(writable)
                lo, hi = entry.bounds
                slider.setMinimum(0)
                slider.setMaximum(1000)
                slider.setValue(int((float(value) - lo) / (hi - lo) * 1000))
                slider.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                slider.valueChanged.connect(
                    lambda v, k=key, _lo=lo, _hi=hi, _sb=spinbox: (
                        _sb.setValue(_lo + v / 1000.0 * (_hi - _lo))
                    )
                )
                spinbox.valueChanged.connect(
                    lambda v, k=key, _lo=lo, _hi=hi, _sl=slider: (
                        _sl.blockSignals(True),
                        _sl.setValue(int((v - _lo) / (_hi - _lo) * 1000)),
                        _sl.blockSignals(False),
                    )
                )
                hlayout.addWidget(slider)  # slider links

            hlayout.addWidget(spinbox)  # spinbox rechts
            return container

        if widget_type == "combobox":
            w = QComboBox()
            for item in (entry.enum_values or []):
                w.addItem(item)
            if value in (entry.enum_values or []):
                w.setCurrentIndex((entry.enum_values or []).index(value))
            w.setEnabled(writable)
            w.currentTextChanged.connect(lambda v, k=key: self._vm.set_pending(k, v))
            return w

        if widget_type == "radio":
            from PySide6.QtWidgets import QButtonGroup, QRadioButton
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)
            group = QButtonGroup(container)
            for i, opt in enumerate(entry.enum_values or []):
                rb = QRadioButton(opt)
                rb.setEnabled(writable)
                if opt == value:
                    rb.setChecked(True)
                rb.toggled.connect(
                    lambda checked, v=opt, k=key: self._vm.set_pending(k, v) if checked else None
                )
                group.addButton(rb, i)
                hlayout.addWidget(rb)
            return container

        if widget_type == "path_picker":
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)
            line = QLineEdit(str(value))
            line.setEnabled(writable)
            line.textChanged.connect(lambda v, k=key: self._vm.set_pending(k, v))
            btn = QPushButton("…")
            btn.setEnabled(writable)
            btn.setMaximumWidth(30)
            btn.clicked.connect(
                lambda checked, k=key, le=line: (
                    (path := QFileDialog.getOpenFileName(self, "Select file")[0]),
                    (le.setText(path) if path else None),
                )
            )
            hlayout.addWidget(line)
            hlayout.addWidget(btn)
            return container

        if widget_type == "datepicker":
            from PySide6.QtCore import QDate
            from PySide6.QtWidgets import QDateEdit
            w = QDateEdit()
            w.setEnabled(writable)
            if hasattr(value, "year"):
                w.setDate(QDate(value.year, value.month, value.day))
            w.dateChanged.connect(
                lambda d, k=key: self._vm.set_pending(
                    k, __import__("datetime").date(d.year(), d.month(), d.day())
                )
            )
            return w

        if widget_type == "color_picker":
            from PySide6.QtGui import QColor as _QColor
            from PySide6.QtWidgets import QColorDialog
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)
            btn = QPushButton()
            btn.setEnabled(writable)
            btn.setMinimumWidth(90)

            def _refresh_btn(hex_color: str, b: QPushButton = btn) -> None:
                fg = _text_for_bg(hex_color)
                b.setText(hex_color)
                b.setStyleSheet(
                    f"background-color: {hex_color}; color: {fg};"
                    f" border: 1px solid {_GRID_COLOR}; border-radius: 2px;"
                    f" padding: 2px 6px;"
                )

            _refresh_btn(str(value))

            def _pick(checked: bool = False, k: str = key, b: QPushButton = btn) -> None:
                current = _QColor(str(self._vm.pending_value(k)))
                picked = QColorDialog.getColor(current, self)
                if picked.isValid():
                    hex_color = picked.name()
                    self._vm.set_pending(k, hex_color)
                    _refresh_btn(hex_color, b)

            btn.clicked.connect(_pick)
            hlayout.addWidget(btn)
            return container

        # lineedit fallback
        w = QLineEdit(str(value))
        w.setEnabled(writable)
        w.textChanged.connect(lambda v, k=key: self._vm.set_pending(k, v))
        return w

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos: Any) -> None:
        item = self.itemAt(pos)
        if item is None:
            widget = self.indexAt(pos)
            row = widget.row()
        else:
            row = item.row()
        if row < 0 or row >= len(self._row_keys):
            return
        key = self._row_keys[row]
        menu = QMenu(self)
        if self._vm.has_default(key):
            default = self._vm.default_value(key)
            action = menu.addAction(f"Reset to default  ({default!r})")
            action.triggered.connect(lambda _checked, k=key: self._reset_to_default(k))
        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _reset_to_default(self, key: str) -> None:
        self._vm.reset_to_default(key)
        row = self._row_keys.index(key)
        entry = self._vm._entries[key][0]
        gh = self._vm._entries[key][2]
        hint = gh if gh is not None else GuiHint()
        widget_type = infer_widget_type(entry, hint)
        new_widget = self._make_value_widget(key, widget_type, self._vm.effective_writable(key))
        self._value_widgets[key] = new_widget
        self.setCellWidget(row, self._COL_VALUE, new_widget)
