from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from synarius_attr_config.meta import GuiHint
from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets._inference import infer_widget_type
from synarius_attr_config.widgets._layout_templates import (
    DEFAULT_TABLE_LAYOUT,
    TableLayoutTemplate,
    apply_table_layout_template,
)

# Variante 1: Randfarben der Value-Spalte (QSS + Fusion-Palette für Checkbox/Radio)
# stammen ausschließlich aus TableLayoutTemplate — siehe value_border_color_light /
# value_border_color_dark und DEFAULT_TABLE_LAYOUT in _layout_templates.py (keine
# separaten *_BORDER-Konstanten mehr).

# ---------------------------------------------------------------------------
# Synarius light-blue table palette
# Mirrors RESOURCES_PANEL_BACKGROUND in synarius_studio.theme.
# ---------------------------------------------------------------------------
_ROW_BG = "#c8e3fb"
_ROW_ALT_BG = "#b4cce2"        # _ROW_BG × 0.90
_NAME_COL_BG = "#8ab0c8"       # parameter column — clearly darker than _ROW_BG
_NAME_COL_ALT_BG = "#7aa3bc"   # parameter column alternating row
_GRID_COLOR = "#9ab8cf"
_INPUT_BG = "#b4cce2"          # input widget fill — toned-down variant of row background
_TEXT_COLOR = "#1a1a1a"
_HEADER_BG = "#353535"
_HEADER_FG = "#ffffff"
_HEADER_SEP = "#505050"
_SEL_BG = "#586cd4"
_SEL_FG = "#ffffff"

# ---------------------------------------------------------------------------
# Dark-style palette used in the Raster (form) view
# ---------------------------------------------------------------------------
_FORM_WIDGET_BG = "#3c3c3c"
_FORM_WIDGET_BG_HOVER = "#4a4a4a"
_FORM_TEXT = "#e8e8e8"

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

class _StyledCheckBox(QCheckBox):
    """QCheckBox with fully custom ``paintEvent``.

    Qt QSS ``::indicator`` rendering is intercepted by ``QStyleSheetStyle``
    whenever any ancestor carries a non-empty stylesheet, producing an
    unstyled white box regardless of ``setStyle(Fusion)``.  This subclass
    bypasses that by drawing the indicator entirely via ``QPainter``:
    a rounded rect with a black checkmark tick on ``_SEL_BG`` fill.
    """

    def __init__(
        self,
        border_color: str,
        dark: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from PySide6.QtGui import QColor
        self._dark = dark
        self._border = QColor(border_color)
        self._bg = QColor(_FORM_WIDGET_BG if dark else _INPUT_BG)
        self._accent = QColor(_SEL_BG)

    def paintEvent(self, event: Any) -> None:
        from PySide6.QtCore import QLineF, QRectF
        from PySide6.QtGui import QColor, QPainter, QPen
        from PySide6.QtWidgets import QStyle, QStyleOptionButton

        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        ir = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)

        checked = self.isChecked()
        use_accent = self._dark and checked
        p.setPen(QPen(self._accent if use_accent else self._border, 1))
        p.setBrush(self._accent if use_accent else self._bg)
        p.drawRoundedRect(QRectF(ir).adjusted(0.5, 0.5, -0.5, -0.5), 2.0, 2.0)

        if checked:
            x, y, w, h = ir.x(), ir.y(), ir.width(), ir.height()
            tick_color = QColor("#ffffff") if self._dark else self._border
            p.setPen(
                QPen(
                    tick_color,
                    1.5,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            p.drawLine(QLineF(x + w * 0.18, y + h * 0.52, x + w * 0.42, y + h * 0.74))
            p.drawLine(QLineF(x + w * 0.42, y + h * 0.74, x + w * 0.82, y + h * 0.24))

        p.end()


_RB_IND = 13   # indicator diameter in px
_RB_GAP = 4    # gap between indicator and text


class _StyledRadioButton(QRadioButton):
    """QRadioButton with fully custom ``paintEvent`` (see :class:`_StyledCheckBox`).

    Uses fixed indicator coordinates (no ``subElementRect``) so the indicator
    and text are positioned predictably, aligning with the ``AlignTop``
    name-column item in multi-option rows.
    """

    def __init__(
        self,
        text: str,
        border_color: str,
        dark: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        from PySide6.QtGui import QColor
        self._dark = dark
        self._border = QColor(border_color)
        self._bg = QColor(_FORM_WIDGET_BG if dark else _INPUT_BG)
        self._accent = QColor(_SEL_BG)
        self._text_color = QColor(_FORM_TEXT if dark else _TEXT_COLOR)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        fm = self.fontMetrics()
        h = max(_RB_IND, fm.height())
        w = _RB_IND + _RB_GAP + fm.horizontalAdvance(self.text()) + 4
        return QSize(w, h)

    def paintEvent(self, event: Any) -> None:
        from PySide6.QtCore import QRect, QRectF
        from PySide6.QtGui import QColor, QPainter, QPen

        h = self.height()
        iy = (h - _RB_IND) / 2  # vertically center the indicator in the widget

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)

        checked = self.isChecked()
        use_accent = self._dark and checked
        circle = QRectF(0.5, iy + 0.5, _RB_IND - 1, _RB_IND - 1)
        p.setPen(QPen(self._accent if use_accent else self._border, 1))
        p.setBrush(self._accent if use_accent else self._bg)
        p.drawEllipse(circle)

        if checked:
            dot_r = (_RB_IND - 1) * 0.30
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ffffff") if self._dark else self._border)
            p.drawEllipse(circle.center(), dot_r, dot_r)

        tx = _RB_IND + _RB_GAP
        p.setPen(QPen(self._text_color))
        p.drawText(
            QRect(tx, 0, self.width() - tx, h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )
        p.end()


def _build_cell_stylesheet(template: TableLayoutTemplate, *, dark: bool) -> str:
    """Stylesheet for value-column widgets; border colour comes from *template*.

    Checkboxes and radio buttons use :class:`_StyledCheckBox` /
    :class:`_StyledRadioButton` instead — they paint themselves entirely via
    ``QPainter``, bypassing ``QStyleSheetStyle`` indicator interference.
    """
    b = template.value_border_color_dark if dark else template.value_border_color_light
    if dark:
        bg, btn_bg, text, groove, btn_hover = (
            _FORM_WIDGET_BG, _FORM_WIDGET_BG_HOVER, _FORM_TEXT, b, b,
        )
    else:
        bg, btn_bg, text, groove, btn_hover = (
            _INPUT_BG, _ROW_ALT_BG, _TEXT_COLOR, _GRID_COLOR, _GRID_COLOR,
        )
    return (
        f"QLineEdit, QDateEdit {{"
        f" background-color: {bg}; color: {text};"
        f" border: 1px solid {b}; border-radius: 2px; margin: 1px;"
        f" selection-background-color: {_SEL_BG}; selection-color: {_SEL_FG}; }}"
        f"QDoubleSpinBox QLineEdit, QSpinBox QLineEdit {{"
        f" background-color: {bg}; color: {text}; border: none; margin: 0;"
        f" padding: 3px 0; }}"
        f"QComboBox QAbstractItemView {{"
        f" background-color: {bg}; color: {text};"
        f" selection-background-color: {_SEL_BG}; selection-color: {_SEL_FG}; }}"
        f"QLabel {{ color: {text}; }}"
        # QRadioButton / QCheckBox indicators: Fusion + per-widget palette (native check/dot).
        f"QSlider::groove:horizontal {{"
        f" background: {groove}; height: 4px; border-radius: 2px; }}"
        f"QSlider::handle:horizontal {{"
        f" background: {_SEL_BG}; width: 12px; height: 12px;"
        f" border-radius: 6px; margin: -4px 0; }}"
        f"QPushButton {{"
        f" background-color: {btn_bg}; color: {text};"
        f" border: 1px solid {b}; border-radius: 2px; padding: 2px 6px; }}"
        f"QPushButton:hover {{ background-color: {btn_hover}; }}"
        f" {_TOOLTIP_QSS}"
    )


def _make_light_palette():
    """Fully specified light palette so OS dark mode cannot leak through."""
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    _light = (
        (QPalette.ColorRole.Window, "#f0f0f0"),
        (QPalette.ColorRole.WindowText, "#000000"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, "#f0f0f0"),
        (QPalette.ColorRole.ToolTipBase, "#ffffdc"),
        (QPalette.ColorRole.ToolTipText, "#000000"),
        (QPalette.ColorRole.PlaceholderText, "#a0a0a0"),
        (QPalette.ColorRole.Text, "#000000"),
        (QPalette.ColorRole.Button, "#e0e0e0"),
        (QPalette.ColorRole.ButtonText, "#000000"),
        (QPalette.ColorRole.BrightText, "#ffffff"),
        (QPalette.ColorRole.Highlight, "#0078d4"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.Link, "#0000ff"),
        (QPalette.ColorRole.LinkVisited, "#800080"),
        (QPalette.ColorRole.Light, "#ffffff"),
        (QPalette.ColorRole.Midlight, "#e8e8e8"),
        (QPalette.ColorRole.Mid, "#a0a0a0"),
        (QPalette.ColorRole.Dark, "#a0a0a0"),
        (QPalette.ColorRole.Shadow, "#696969"),
    )
    for grp in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, color in _light:
            p.setColor(grp, role, QColor(color))
    _disabled = (
        (QPalette.ColorRole.Window, "#f0f0f0"),
        (QPalette.ColorRole.WindowText, "#808080"),
        (QPalette.ColorRole.Base, "#f0f0f0"),
        (QPalette.ColorRole.AlternateBase, "#f0f0f0"),
        (QPalette.ColorRole.Text, "#808080"),
        (QPalette.ColorRole.Button, "#e0e0e0"),
        (QPalette.ColorRole.ButtonText, "#808080"),
        (QPalette.ColorRole.Highlight, "#c0c0c0"),
        (QPalette.ColorRole.HighlightedText, "#808080"),
        (QPalette.ColorRole.Light, "#ffffff"),
        (QPalette.ColorRole.Midlight, "#e8e8e8"),
        (QPalette.ColorRole.Mid, "#a0a0a0"),
        (QPalette.ColorRole.Dark, "#a0a0a0"),
        (QPalette.ColorRole.Shadow, "#696969"),
    )
    for role, color in _disabled:
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(color))
    return p


def _make_input_palette(border_color: str | None = None):
    """Palette for Fusion value widgets in the light table theme (template border *b*)."""
    from PySide6.QtGui import QColor, QPalette

    border = border_color or DEFAULT_TABLE_LAYOUT.value_border_color_light
    p = _make_light_palette()
    _overrides = (
        (QPalette.ColorRole.Base, _INPUT_BG),
        (QPalette.ColorRole.AlternateBase, _ROW_ALT_BG),
        (QPalette.ColorRole.Window, _INPUT_BG),
        (QPalette.ColorRole.WindowText, _TEXT_COLOR),
        (QPalette.ColorRole.Text, _TEXT_COLOR),
        (QPalette.ColorRole.Button, _ROW_ALT_BG),
        (QPalette.ColorRole.ButtonText, _TEXT_COLOR),
        (QPalette.ColorRole.Highlight, _SEL_BG),
        (QPalette.ColorRole.HighlightedText, _SEL_FG),
        (QPalette.ColorRole.Light, _INPUT_BG),
        (QPalette.ColorRole.Dark, border),
        (QPalette.ColorRole.Shadow, border),
        (QPalette.ColorRole.Mid, border),
        (QPalette.ColorRole.Midlight, _ROW_BG),
    )
    for grp in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, color in _overrides:
            p.setColor(grp, role, QColor(color))
    return p


def _make_dark_input_palette(border_color: str | None = None):
    """Palette for Fusion value widgets in the dark / Raster theme."""
    from PySide6.QtGui import QColor, QPalette

    border = border_color or DEFAULT_TABLE_LAYOUT.value_border_color_dark
    p = QPalette()
    _roles = (
        (QPalette.ColorRole.Window, _FORM_WIDGET_BG),
        (QPalette.ColorRole.WindowText, _FORM_TEXT),
        (QPalette.ColorRole.Base, _FORM_WIDGET_BG),
        (QPalette.ColorRole.AlternateBase, _FORM_WIDGET_BG_HOVER),
        (QPalette.ColorRole.ToolTipBase, "#2b2b2b"),
        (QPalette.ColorRole.ToolTipText, _FORM_TEXT),
        (QPalette.ColorRole.PlaceholderText, "#909090"),
        (QPalette.ColorRole.Text, _FORM_TEXT),
        (QPalette.ColorRole.Button, _FORM_WIDGET_BG_HOVER),
        (QPalette.ColorRole.ButtonText, _FORM_TEXT),
        (QPalette.ColorRole.BrightText, "#ffffff"),
        (QPalette.ColorRole.Highlight, _SEL_BG),
        (QPalette.ColorRole.HighlightedText, _SEL_FG),
        (QPalette.ColorRole.Link, "#6080d0"),
        (QPalette.ColorRole.LinkVisited, "#9060c0"),
        (QPalette.ColorRole.Light, "#5a5a5a"),
        (QPalette.ColorRole.Midlight, _FORM_WIDGET_BG_HOVER),
        (QPalette.ColorRole.Mid, border),
        (QPalette.ColorRole.Dark, border),
        (QPalette.ColorRole.Shadow, border),
    )
    for grp in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, color in _roles:
            p.setColor(grp, role, QColor(color))
    _disabled = (
        (QPalette.ColorRole.Window, _FORM_WIDGET_BG),
        (QPalette.ColorRole.WindowText, "#707070"),
        (QPalette.ColorRole.Base, _FORM_WIDGET_BG),
        (QPalette.ColorRole.Text, "#707070"),
        (QPalette.ColorRole.Button, _FORM_WIDGET_BG),
        (QPalette.ColorRole.ButtonText, "#707070"),
        (QPalette.ColorRole.Dark, "#666666"),
        (QPalette.ColorRole.Shadow, "#666666"),
    )
    for role, color in _disabled:
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(color))
    return p


# Stylesheet applied directly to modal dialogs (QFontDialog etc.) that have no
# native OS equivalent.  Scoped to the dialog widget — does NOT affect the app.
_LIGHT_DIALOG_QSS = (
    "QDialog, QWidget { background-color: #f0f0f0; color: #000000; }"
    "QListView, QTreeView { background-color: #ffffff; color: #000000; }"
    "QLineEdit, QSpinBox, QDoubleSpinBox {"
    " background-color: #ffffff; color: #000000;"
    " border: 1px solid #aaaaaa; border-radius: 2px; }"
    "QLabel { color: #000000; background-color: transparent; }"
    "QPushButton { background-color: #e0e0e0; color: #000000;"
    " border: 1px solid #aaaaaa; border-radius: 3px; padding: 4px 12px; }"
    "QPushButton:hover { background-color: #d0d0d0; }"
    "QComboBox { background-color: #ffffff; color: #000000;"
    " border: 1px solid #aaaaaa; border-radius: 2px; }"
    "QComboBox QAbstractItemView { background-color: #ffffff; color: #000000;"
    " selection-background-color: #0078d4; selection-color: #ffffff; }"
    "QGroupBox { color: #000000; border: 1px solid #aaaaaa;"
    " border-radius: 4px; margin-top: 8px; padding-top: 4px; }"
    "QGroupBox::title { color: #000000; subcontrol-origin: margin; padding: 0 4px; }"
    "QCheckBox { color: #000000; }"
    "QScrollBar:vertical { background-color: #e0e0e0; width: 12px; }"
    "QScrollBar::handle:vertical { background-color: #aaaaaa; border-radius: 4px; }"
    "QScrollBar:horizontal { background-color: #e0e0e0; height: 12px; }"
    "QScrollBar::handle:horizontal { background-color: #aaaaaa; border-radius: 4px; }"
)


def _text_for_bg(hex_bg: str) -> str:
    """Return '#000000' or '#ffffff' depending on which gives better contrast on *hex_bg*."""
    s = hex_bg.strip().removeprefix("#")
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    luminance = (r * 299 + g * 587 + b * 114) // 1000
    return "#000000" if luminance > 128 else "#ffffff"


class AttribTableWidget(QTableWidget):
    """Attribute table view backed by an :class:`AttribViewModel`.

    Two columns: *display name* | *value widget*.

    When *title* is provided the standard column headers are hidden and
    replaced by a merged title row spanning both columns (dark header
    background), which is useful when the widget is embedded inside a
    larger panel that already carries section labels.

    Only attributes where ``view_model.effective_exposed(key)`` is ``True``
    are rendered.  Rows are not editable via double-click; all editing is done
    through the embedded value widgets.

    A right-click context menu on any row with a default value offers
    *Reset to default*.

    Parameters
    ----------
    view_model
        The projected attribute set to display.
    title
        Optional group name shown in the first column header.
        When given the header label shows the group name instead of "Attribut".
    alternating_rows
        When ``True`` (default) every second row uses a slightly darker background
        and the parameter column uses its own two-tone shading.  Pass ``False`` to
        disable alternating colours.
    layout_template
        Column labels, default widths, resize policy, **value-column margins**
        (``value_cell_margins_ltrb``), and **shared border colours**
        (``value_border_color_light`` / ``value_border_color_dark`` for spin
        boxes, line edits, check-box indicators, etc.).
        Defaults to :data:`~synarius_attr_config.widgets.DEFAULT_TABLE_LAYOUT`.
    """

    _COL_NAME = 0
    _COL_VALUE = 1

    def __init__(
        self,
        view_model: AttribViewModel,
        title: str = "",
        alternating_rows: bool = True,
        layout_template: TableLayoutTemplate | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._title = title
        self._alternating_rows = alternating_rows
        self._layout_template = layout_template or DEFAULT_TABLE_LAYOUT
        self._data_row_offset = 1 if title else 0
        self._row_keys: list[str] = []
        self._value_widgets: dict[str, QWidget] = {}

        self.setColumnCount(2)
        apply_table_layout_template(self, self._layout_template)
        self.setAlternatingRowColors(alternating_rows)
        self.setStyleSheet(_TABLE_QSS)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.verticalHeader().setVisible(False)
        if title:
            self.horizontalHeader().setVisible(False)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self._col_resize_active = False
        self._col_resize_start_x = 0
        self._col_resize_start_width = 0

        self._populate()

    def _wrap_value_cell(self, inner: QWidget) -> QWidget:
        """Apply uniform value-column insets from :attr:`_layout_template`."""
        m = self._layout_template.value_cell_margins_ltrb
        outer = QWidget()
        lay = QHBoxLayout(outer)
        lay.setContentsMargins(m[0], m[1], m[2], m[3])
        lay.setSpacing(0)
        lay.addWidget(inner, 1)
        proxy = inner.focusProxy()
        outer.setFocusProxy(proxy if proxy is not None else inner)
        return outer

    def _apply_fusion_input_theme(self, w: QWidget, *, dark: bool) -> None:
        """Fusion + cell palette so indicators use native check/dot (QSS ::indicator is unreliable)."""
        from PySide6.QtWidgets import QStyleFactory

        tpl = self._layout_template
        b = tpl.value_border_color_dark if dark else tpl.value_border_color_light
        _fus = QStyleFactory.create("Fusion")
        if _fus is not None:
            w.setStyle(_fus)
        w.setPalette(_make_dark_input_palette(b) if dark else _make_input_palette(b))

    def _apply_calendar_theme(self, cal: QWidget, *, dark: bool) -> None:
        """Apply Fusion + palette to *cal* and every internal child widget.

        QCalendarWidget contains several autonomous sub-widgets (navigation
        bar QToolButtons, year QSpinBox, QTableView for the day grid) that do
        not reliably inherit palette or style from the top-level widget.
        Iterating all children explicitly is the only robust fix.
        """
        from PySide6.QtWidgets import QStyleFactory, QWidget as _QW

        tpl = self._layout_template
        b = tpl.value_border_color_dark if dark else tpl.value_border_color_light
        pal = _make_dark_input_palette(b) if dark else _make_input_palette(b)
        fus = QStyleFactory.create("Fusion")
        for cw in [cal, *cal.findChildren(_QW)]:
            if fus is not None:
                cw.setStyle(fus)
            cw.setPalette(pal)

    # ------------------------------------------------------------------
    # Column resize via viewport drag (works even when header is hidden)
    # ------------------------------------------------------------------

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj is self.viewport():
            t = event.type()
            if t == QEvent.Type.MouseMove:
                pos = event.position().toPoint()
                col_x = self.columnViewportPosition(1)
                if self._col_resize_active:
                    dx = pos.x() - self._col_resize_start_x
                    self.setColumnWidth(
                        0,
                        max(
                            self._layout_template.min_first_column_width_px,
                            self._col_resize_start_width + dx,
                        ),
                    )
                    return True
                if abs(pos.x() - col_x) <= 4:
                    self.viewport().setCursor(Qt.CursorShape.SplitHCursor)
                else:
                    self.viewport().unsetCursor()
            elif t == QEvent.Type.MouseButtonPress:
                pos = event.position().toPoint()
                col_x = self.columnViewportPosition(1)
                if abs(pos.x() - col_x) <= 4:
                    self._col_resize_active = True
                    self._col_resize_start_x = pos.x()
                    self._col_resize_start_width = self.columnWidth(0)
                    return True
            elif t == QEvent.Type.MouseButtonRelease:
                if self._col_resize_active:
                    self._col_resize_active = False
                    self.viewport().unsetCursor()
                    return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        visible_keys = [k for k in self._vm.keys if self._vm.effective_exposed(k)]
        self._row_keys = visible_keys
        self.setRowCount(len(visible_keys) + self._data_row_offset)

        if self._title:
            title_item = QTableWidgetItem(self._title)
            title_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            title_item.setBackground(QBrush(QColor(_HEADER_BG)))
            title_item.setForeground(QBrush(QColor(_HEADER_FG)))
            f = title_item.font()
            f.setBold(True)
            title_item.setFont(f)
            self.setItem(0, 0, title_item)
            self.setSpan(0, 0, 1, 2)

        for row_idx, key in enumerate(visible_keys):
            row = row_idx + self._data_row_offset
            entry = self._vm._entries[key][0]
            gh = self._vm._entries[key][2]
            hint = gh if gh is not None else GuiHint()

            display = self._vm.display_name(key)
            modified = self._vm.is_modified(key)
            name_item = QTableWidgetItem(f"{display} *" if modified else display)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if modified:
                _f = name_item.font()
                _f.setBold(True)
                name_item.setFont(_f)
            name_bg = (_NAME_COL_ALT_BG if self._alternating_rows and row_idx % 2 == 1
                       else _NAME_COL_BG)
            name_item.setBackground(QBrush(QColor(name_bg)))
            widget_type = infer_widget_type(entry, hint)
            if widget_type == "radio":
                name_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )
            self.setItem(row, self._COL_NAME, name_item)
            value_widget = self._make_value_widget(
                key, widget_type, self._vm.effective_writable(key),
                on_change=self._update_name_star,
            )
            self._value_widgets[key] = value_widget
            self.setCellWidget(row, self._COL_VALUE, value_widget)

        self.resizeRowsToContents()

    def _make_value_widget(
        self,
        key: str,
        widget_type: str,
        writable: bool,
        dark: bool = False,
        on_change: Any = None,
    ) -> QWidget:
        entry = self._vm._entries[key][0]
        gh = self._vm._entries[key][2]
        value = self._vm.pending_value(key)

        w = self._build_value_widget(key, entry, gh, widget_type, writable, value, dark=dark, on_change=on_change)
        w = self._wrap_value_cell(w)
        if widget_type not in ("checkbox", "radio"):
            # Add top/bottom breathing room; radio keeps margin=0 for AlignTop alignment.
            lay = w.layout()
            m = lay.contentsMargins()
            lay.setContentsMargins(m.left(), 2, m.right(), 2)
        if widget_type not in ("checkbox", "radio"):
            _ss = _build_cell_stylesheet(self._layout_template, dark=dark)
            w.setStyleSheet(_ss)
            # QAbstractSpinBox / QComboBox / QDateEdit subcontrols (::up-arrow,
            # ::down-arrow, ::drop-down) only render when the stylesheet is set
            # on the concrete input widget, not just on an ancestor wrapper.
            for _cls in (QDoubleSpinBox, QComboBox):
                for _inp in w.findChildren(_cls):
                    _inp.setStyleSheet(_ss)
            from PySide6.QtWidgets import QDateEdit as _QDateEdit
            for _inp in w.findChildren(_QDateEdit):
                _inp.setStyleSheet(_ss)
        return w

    def _build_value_widget(
        self,
        key: str,
        entry: Any,
        gh: GuiHint | None,
        widget_type: str,
        writable: bool,
        value: Any,
        dark: bool = False,
        on_change: Any = None,
    ) -> QWidget:
        def _set(k: str, v: Any) -> None:
            self._vm.set_pending(k, v)
            if on_change is not None:
                on_change(k)

        if widget_type == "checkbox":
            tpl = self._layout_template
            b = tpl.value_border_color_dark if dark else tpl.value_border_color_light
            cb = _StyledCheckBox(b, dark)
            cb.setChecked(bool(value))
            cb.setEnabled(writable)
            cb.checkStateChanged.connect(
                lambda state, k=key: _set(k, state == Qt.CheckState.Checked)
            )
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)
            hlayout.addWidget(cb)
            hlayout.addStretch()
            container.setFocusProxy(cb)
            return container

        if widget_type in ("spinbox", "slider+spinbox"):
            spinbox = QDoubleSpinBox()
            spinbox.setAlignment(Qt.AlignmentFlag.AlignRight)
            spinbox.setDecimals(
                gh.decimal_precision if gh and gh.decimal_precision is not None else 4
            )
            _min_w = (
                spinbox.fontMetrics().horizontalAdvance(
                    "8" * self._layout_template.spinbox_min_contents_length
                )
                + 40  # arrows + frame
            )
            spinbox.setMinimumWidth(_min_w)
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
            spinbox.valueChanged.connect(lambda v, k=key: _set(k, v))
            self._apply_fusion_input_theme(spinbox, dark=dark)

            if widget_type == "slider+spinbox" and entry.bounds is not None:
                lo, hi = entry.bounds
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setEnabled(writable)
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
                container = QWidget()
                hlayout = QHBoxLayout(container)
                hlayout.setContentsMargins(2, 2, 2, 2)
                hlayout.addWidget(slider)
                hlayout.addWidget(spinbox)
                container.setFocusProxy(spinbox)
                return container

            return spinbox

        if widget_type == "combobox":
            w = QComboBox()
            for item in (entry.enum_values or []):
                w.addItem(item)
            if value in (entry.enum_values or []):
                w.setCurrentIndex((entry.enum_values or []).index(value))
            w.setEnabled(writable)
            w.currentTextChanged.connect(lambda v, k=key: _set(k, v))
            self._apply_fusion_input_theme(w, dark=dark)
            return w

        if widget_type == "radio":
            from PySide6.QtWidgets import QButtonGroup

            tpl = self._layout_template
            b = tpl.value_border_color_dark if dark else tpl.value_border_color_light
            from PySide6.QtWidgets import QVBoxLayout
            container = QWidget()
            vlayout = QVBoxLayout(container)
            vlayout.setContentsMargins(0, 0, 0, 0)
            vlayout.setSpacing(2)
            group = QButtonGroup(container)
            for i, opt in enumerate(entry.enum_values or []):
                rb = _StyledRadioButton(opt, b, dark)
                rb.setEnabled(writable)
                if opt == value:
                    rb.setChecked(True)
                rb.toggled.connect(
                    lambda checked, v=opt, k=key: _set(k, v) if checked else None
                )
                group.addButton(rb, i)
                vlayout.addWidget(rb)
            vlayout.addStretch(1)
            return container

        if widget_type == "path_picker":
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)
            line = QLineEdit(str(value))
            line.setEnabled(writable)
            line.textChanged.connect(lambda v, k=key: _set(k, v))
            btn = QPushButton("…")
            btn.setEnabled(writable)
            btn.setAutoDefault(False)
            btn.setMaximumWidth(30)
            btn.clicked.connect(
                lambda checked, k=key, le=line: (
                    (path := QFileDialog.getOpenFileName(le, "Select file")[0]),
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
            w.setCalendarPopup(True)
            w.setEnabled(writable)
            if hasattr(value, "year"):
                w.setDate(QDate(value.year, value.month, value.day))
            w.dateChanged.connect(
                lambda d, k=key: _set(
                    k, __import__("datetime").date(d.year(), d.month(), d.day())
                )
            )
            self._apply_fusion_input_theme(w, dark=dark)
            cal = w.calendarWidget()
            if cal is not None:
                self._apply_calendar_theme(cal, dark=dark)
            return w

        if widget_type == "color_picker":
            from PySide6.QtGui import QColor as _QColor
            from PySide6.QtWidgets import QColorDialog
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(2, 0, 0, 0)
            hlayout.setSpacing(4)

            tpl = self._layout_template
            swatch_border = (
                tpl.value_border_color_dark if dark else tpl.value_border_color_light
            )

            swatch = QLabel()
            swatch.setObjectName("colorSwatch")
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(
                f"QLabel#colorSwatch {{ background-color: {value};"
                f" border: 1px solid {swatch_border}; }}"
            )

            hex_label = QLabel(str(value))

            btn = QPushButton("…")
            btn.setEnabled(writable)
            btn.setAutoDefault(False)
            btn.setFixedWidth(28)

            def _pick(
                checked: bool = False,
                k: str = key,
                sw: QLabel = swatch,
                lb: QLabel = hex_label,
                sb: str = swatch_border,
            ) -> None:
                # parent=None → Qt uses the native OS color dialog which is
                # unaffected by the application palette.
                picked = QColorDialog.getColor(
                    _QColor(str(self._vm.pending_value(k))), None
                )
                if picked.isValid():
                    hex_color = picked.name()
                    _set(k, hex_color)
                    sw.setStyleSheet(
                        f"QLabel#colorSwatch {{ background-color: {hex_color};"
                        f" border: 1px solid {sb}; }}"
                    )
                    lb.setText(hex_color)

            btn.clicked.connect(_pick)
            hlayout.addWidget(swatch)
            hlayout.addWidget(hex_label, 1)
            hlayout.addWidget(btn)
            return container

        if widget_type == "font_picker":
            from PySide6.QtGui import QFont as _QFont
            container = QWidget()
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(2, 0, 0, 0)
            hlayout.setSpacing(4)

            font_label = QLabel(str(value))

            btn = QPushButton("…")
            btn.setEnabled(writable)
            btn.setAutoDefault(False)
            btn.setFixedWidth(28)

            def _pick_font(
                checked: bool = False,
                k: str = key,
                lb: QLabel = font_label,
            ) -> None:
                from PySide6.QtWidgets import QFontDialog
                ok, font = QFontDialog.getFont(_QFont(str(self._vm.pending_value(k))))
                if ok:
                    _set(k, font.family())
                    lb.setText(font.family())

            btn.clicked.connect(_pick_font)
            hlayout.addWidget(font_label, 1)
            hlayout.addWidget(btn)
            return container

        # lineedit fallback
        w = QLineEdit(str(value))
        w.setEnabled(writable)
        w.textChanged.connect(lambda v, k=key: _set(k, v))
        return w

    def _update_name_star(self, key: str) -> None:
        if key not in self._row_keys:
            return
        row = self._row_keys.index(key) + self._data_row_offset
        item = self.item(row, self._COL_NAME)
        if item is None:
            return
        base = self._vm.display_name(key)
        modified = self._vm.is_modified(key)
        item.setText(f"{base} *" if modified else base)
        f = item.font()
        f.setBold(modified)
        item.setFont(f)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def compact(self) -> int:
        """Set fixed height to exactly fit header + all content rows.

        Returns the pixel height applied.  Prefer letting the widget size
        itself via ``AdjustToContents`` (set in ``__init__``); call this only
        when an explicit fixed height is required by the parent layout.
        """
        hh = self.horizontalHeader()
        h = hh.sizeHint().height() if hh.isVisible() else 0
        for r in range(self.rowCount()):
            h += self.rowHeight(r)
        h += 2  # frame border
        self.setFixedHeight(h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return h

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()
        else:
            super().keyPressEvent(event)

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
        data_row = row - self._data_row_offset
        if data_row < 0 or data_row >= len(self._row_keys):
            return
        key = self._row_keys[data_row]
        menu = QMenu(self)
        if self._vm.has_default(key):
            default = self._vm.default_value(key)
            action = menu.addAction(f"Reset to default  ({default!r})")
            action.triggered.connect(lambda _checked, k=key: self._reset_to_default(k))
        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _reset_to_default(self, key: str) -> None:
        self._vm.reset_to_default(key)
        row = self._row_keys.index(key) + self._data_row_offset
        entry = self._vm._entries[key][0]
        gh = self._vm._entries[key][2]
        hint = gh if gh is not None else GuiHint()
        widget_type = infer_widget_type(entry, hint)
        new_widget = self._make_value_widget(
            key, widget_type, self._vm.effective_writable(key),
            on_change=self._update_name_star,
        )
        self._value_widgets[key] = new_widget
        self.setCellWidget(row, self._COL_VALUE, new_widget)
        self._update_name_star(key)
