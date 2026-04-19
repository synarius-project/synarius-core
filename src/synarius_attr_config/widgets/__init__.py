from synarius_attr_config.widgets._form_widget import AttribFormWidget
from synarius_attr_config.widgets._inference import WidgetType, infer_widget_type
from synarius_attr_config.widgets._layout_templates import (
    DEFAULT_FORM_LAYOUT,
    DEFAULT_OPTIONS_MENU_SHELL,
    DEFAULT_TABLE_LAYOUT,
    FormLayoutTemplate,
    OptionsMenuShellTemplate,
    TableLayoutTemplate,
    apply_form_layout_template,
    apply_options_scroll_layout,
    apply_options_splitter_template,
    apply_table_layout_template,
    format_options_group_title,
)
from synarius_attr_config.widgets._options_menu import OptionsMenuWidget
from synarius_attr_config.widgets._table_widget import AttribTableWidget

__all__ = [
    "infer_widget_type",
    "WidgetType",
    "AttribTableWidget",
    "AttribFormWidget",
    "OptionsMenuWidget",
    "FormLayoutTemplate",
    "TableLayoutTemplate",
    "OptionsMenuShellTemplate",
    "DEFAULT_FORM_LAYOUT",
    "DEFAULT_TABLE_LAYOUT",
    "DEFAULT_OPTIONS_MENU_SHELL",
    "apply_form_layout_template",
    "apply_table_layout_template",
    "apply_options_splitter_template",
    "apply_options_scroll_layout",
    "format_options_group_title",
]
