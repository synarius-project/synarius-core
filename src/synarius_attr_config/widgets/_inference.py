from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from synarius_core.model.attribute_dict import AttributeEntry
from synarius_attr_config.meta import GuiHint

WidgetType = Literal[
    "radio",
    "combobox",
    "checkbox",
    "slider+spinbox",
    "spinbox",
    "color_picker",
    "path_picker",
    "datepicker",
    "lineedit",
]


def infer_widget_type(entry: AttributeEntry, hint: GuiHint) -> WidgetType:
    """Select the appropriate widget type for *entry* / *hint*.

    Precedence (concept Section 9.1):

    1. ``GuiHint.widget_type_override`` — explicit caller override.
    2. ``enum_values`` present with ≤ 3 members → radio buttons.
    3. ``enum_values`` present with > 3 members → combo box.
    4. ``bool`` value → checkbox.  (Must precede ``int`` check; bool ⊂ int.)
    5. Numeric value with ``bounds`` → slider + spin-box.
    6. Numeric value without ``bounds`` → spin-box.
    7. ``pathlib.Path`` value → file/path picker.
    8. ``date`` / ``datetime`` value → date picker.
    9. Fallback → plain text input (``lineedit``).
    """
    if hint.widget_type_override is not None:
        return hint.widget_type_override  # type: ignore[return-value]

    value = entry.getter() if entry.getter is not None else entry.value

    if entry.enum_values is not None:
        return "radio" if len(entry.enum_values) <= 3 else "combobox"

    if isinstance(value, bool):
        return "checkbox"

    if isinstance(value, (int, float)):
        return "slider+spinbox" if entry.bounds is not None else "spinbox"

    if isinstance(value, Path):
        return "path_picker"

    if isinstance(value, (date, datetime)):
        return "datepicker"

    return "lineedit"
