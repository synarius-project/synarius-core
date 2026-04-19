from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets._layout_templates import (
    DEFAULT_FORM_LAYOUT,
    DEFAULT_TABLE_LAYOUT,
    FormLayoutTemplate,
    TableLayoutTemplate,
    apply_form_layout_template,
)
from synarius_attr_config.widgets._table_widget import AttribTableWidget, _FORM_TEXT


class AttribFormWidget(QWidget):
    """Form-layout equivalent of :class:`AttribTableWidget`.

    Uses a ``QGridLayout`` with a two-column structure
    (display name | value widget).  Preferred in embedded panels
    and context menus where the table chrome (headers, row lines) is
    undesirable.

    The value widgets are identical to :class:`AttribTableWidget`;
    the implementation reuses the widget-building logic from that class.

    Parameters
    ----------
    view_model
        The projected attribute set to display.
    dark
        When ``True`` value widgets use the dark-style QSS
        (template-driven, see :class:`~synarius_attr_config.widgets.TableLayoutTemplate`)
        and labels are rendered with light text so
        the form blends into a dark application palette.
    layout_template
        Grid column widths / stretch for the name | value columns.
        Defaults to :data:`~synarius_attr_config.widgets.DEFAULT_FORM_LAYOUT`.
    cell_chrome_template
        Margins and border colours for value widgets (shared with
        :class:`AttribTableWidget`). Defaults to
        :data:`~synarius_attr_config.widgets.DEFAULT_TABLE_LAYOUT`.
    """

    def __init__(
        self,
        view_model: AttribViewModel,
        dark: bool = False,
        layout_template: FormLayoutTemplate | None = None,
        cell_chrome_template: TableLayoutTemplate | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._dark = dark
        self._layout_template = layout_template or DEFAULT_FORM_LAYOUT
        self._name_labels: dict[str, QLabel] = {}

        # Reuse AttribTableWidget only for its _make_value_widget / inference;
        # we do our own layout here.
        self._helper = AttribTableWidget.__new__(AttribTableWidget)
        self._helper._vm = view_model
        self._helper._layout_template = cell_chrome_template or DEFAULT_TABLE_LAYOUT

        layout = QGridLayout(self)
        apply_form_layout_template(layout, self._layout_template)

        visible_keys = [k for k in view_model.keys if view_model.effective_exposed(k)]
        for row, key in enumerate(visible_keys):
            entry = view_model._entries[key][0]
            gh = view_model._entries[key][2]
            from synarius_attr_config.meta import GuiHint
            hint = gh if gh is not None else GuiHint()
            from synarius_attr_config.widgets._inference import infer_widget_type
            widget_type = infer_widget_type(entry, hint)

            display = view_model.display_name(key)
            modified = view_model.is_modified(key)
            name_label = QLabel(f"{display} *" if modified else display)
            if modified:
                _f = name_label.font()
                _f.setBold(True)
                name_label.setFont(_f)
            if dark:
                name_label.setStyleSheet(f"color: {_FORM_TEXT};")
            self._name_labels[key] = name_label
            lt = self._layout_template
            layout.addWidget(name_label, row, lt.name_column)

            value_widget = self._helper._make_value_widget(
                key, widget_type, view_model.effective_writable(key), dark=dark,
                on_change=self._update_name_star,
            )
            layout.addWidget(value_widget, row, lt.value_column)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()
        else:
            super().keyPressEvent(event)

    def _update_name_star(self, key: str) -> None:
        label = self._name_labels.get(key)
        if label is None:
            return
        base = self._vm.display_name(key)
        modified = self._vm.is_modified(key)
        label.setText(f"{base} *" if modified else base)
        f = label.font()
        f.setBold(modified)
        label.setFont(f)
        if self._dark:
            label.setStyleSheet(f"color: {_FORM_TEXT};")
