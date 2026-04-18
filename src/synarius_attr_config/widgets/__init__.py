from synarius_attr_config.widgets._form_widget import AttribFormWidget
from synarius_attr_config.widgets._inference import WidgetType, infer_widget_type
from synarius_attr_config.widgets._options_menu import OptionsMenuWidget
from synarius_attr_config.widgets._table_widget import AttribTableWidget

__all__ = [
    "infer_widget_type",
    "WidgetType",
    "AttribTableWidget",
    "AttribFormWidget",
    "OptionsMenuWidget",
]
