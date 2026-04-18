from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
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

from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets._inference import infer_widget_type

# Synarius light-blue table palette (mirrors RESOURCES_PANEL_BACKGROUND in synarius_studio.theme).
_ROW_BG = "#c8e3fb"
_ROW_ALT_BG = "#b4cce2"   # _ROW_BG scaled ×0.90
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


class AttribTableWidget(QTableWidget):
    """Attribute table view backed by an :class:`AttribViewModel`.

    Three columns: *display name* | *value widget* | *unit*.

    Only attributes where ``view_model.effective_exposed(key)`` is ``True``
    are rendered.  Rows are not editable via double-click; all editing is done
    through the embedded value widgets.

    A right-click context menu on any row with a default value offers
    *Reset to default*.
    """

    _COL_NAME = 0
    _COL_VALUE = 1
    _COL_UNIT = 2

    def __init__(
        self,
        view_model: AttribViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._row_keys: list[str] = []
        self._value_widgets: dict[str, QWidget] = {}

        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Parameter", "Value", "Unit"])
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionResizeMode(
            self._COL_VALUE,
            self.horizontalHeader().ResizeMode.Stretch,
        )
        self.horizontalHeader().setSectionResizeMode(
            self._COL_UNIT,
            self.horizontalHeader().ResizeMode.ResizeToContents,
        )
        self.setAlternatingRowColors(True)
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
            hint = gh if gh is not None else __import__(
                "synarius_attr_config.meta", fromlist=["GuiHint"]
            ).GuiHint()

            name_item = QTableWidgetItem(self._vm.display_name(key))
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.setItem(row, self._COL_NAME, name_item)

            widget_type = infer_widget_type(entry, hint)
            value_widget = self._make_value_widget(
                key, widget_type, self._vm.effective_writable(key)
            )
            self._value_widgets[key] = value_widget
            self.setCellWidget(row, self._COL_VALUE, value_widget)

            unit_item = QTableWidgetItem(self._vm.unit(key))
            unit_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.setItem(row, self._COL_UNIT, unit_item)

        self.resizeRowsToContents()

    def _make_value_widget(self, key: str, widget_type: str, writable: bool) -> QWidget:
        entry = self._vm._entries[key][0]
        gh = self._vm._entries[key][2]
        value = self._vm.pending_value(key)

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
                    (
                        path := QFileDialog.getOpenFileName(self, "Select file")[0]
                    ),
                    (le.setText(path) if path else None),
                )
            )
            hlayout.addWidget(line)
            hlayout.addWidget(btn)
            return container

        # datepicker
        if widget_type == "datepicker":
            from PySide6.QtWidgets import QDateEdit
            from PySide6.QtCore import QDate
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
        hint = gh if gh is not None else __import__(
            "synarius_attr_config.meta", fromlist=["GuiHint"]
        ).GuiHint()
        widget_type = infer_widget_type(entry, hint)
        new_widget = self._make_value_widget(key, widget_type, self._vm.effective_writable(key))
        self._value_widgets[key] = new_widget
        self.setCellWidget(row, self._COL_VALUE, new_widget)
