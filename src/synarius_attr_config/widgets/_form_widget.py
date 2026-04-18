from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets._table_widget import AttribTableWidget


class AttribFormWidget(QWidget):
    """Form-layout equivalent of :class:`AttribTableWidget`.

    Uses a ``QGridLayout`` with the same three-column structure
    (display name | value widget | unit).  Preferred in embedded panels
    and context menus where the table chrome (headers, row lines) is
    undesirable.

    The value widgets and context-menu behaviour are identical to
    :class:`AttribTableWidget`; the implementation reuses the widget-
    building logic from that class.
    """

    def __init__(
        self,
        view_model: AttribViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model

        # Reuse AttribTableWidget only for its _make_value_widget / inference;
        # we do our own layout here.
        self._helper = AttribTableWidget.__new__(AttribTableWidget)
        self._helper._vm = view_model

        layout = QGridLayout(self)
        layout.setColumnStretch(1, 1)

        visible_keys = [k for k in view_model.keys if view_model.effective_exposed(k)]
        for row, key in enumerate(visible_keys):
            entry = view_model._entries[key][0]
            gh = view_model._entries[key][2]
            from synarius_attr_config.meta import GuiHint
            hint = gh if gh is not None else GuiHint()
            from synarius_attr_config.widgets._inference import infer_widget_type
            widget_type = infer_widget_type(entry, hint)

            name_label = QLabel(view_model.display_name(key))
            layout.addWidget(name_label, row, 0)

            value_widget = self._helper._make_value_widget(
                key, widget_type, view_model.effective_writable(key)
            )
            layout.addWidget(value_widget, row, 1)
