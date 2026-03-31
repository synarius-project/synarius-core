from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum
from typing import Any

SetterFunction = Callable[[Any], None]
GetterFunction = Callable[[], Any]
AttributeEntry = tuple[Any, SetterFunction | None, GetterFunction | None, bool, bool]


class AttributeDict(dict[str, AttributeEntry]):
    """Dictionary for model attributes with protocol-related metadata.

    Tuple layout per key:
    (value, setter_function, getter_function, exposed, writable)
    """

    class _Field(IntEnum):
        VALUE = 0
        SETTER = 1
        GETTER = 2
        EXPOSED = 3
        WRITABLE = 4

    def __setitem__(self, key: str, value: Any) -> None:
        entry: AttributeEntry = (value, None, None, True, False)
        super().__setitem__(key, entry)

    def set_virtual(
        self,
        key: str,
        getter: GetterFunction,
        setter: SetterFunction | None = None,
        *,
        exposed: bool = True,
        writable: bool = False,
    ) -> None:
        """Set a virtual attribute entry with getter/setter metadata."""
        entry: AttributeEntry = (None, setter, getter, exposed, writable)
        super().__setitem__(key, entry)

    def __getitem__(self, key: str) -> Any:
        entry = super().__getitem__(key)
        getter = entry[self._Field.GETTER]
        if getter is not None:
            return getter()
        return entry[self._Field.VALUE]

    def exposed(self, key: str) -> bool:
        return super().__getitem__(key)[self._Field.EXPOSED]

    def writable(self, key: str) -> bool:
        return super().__getitem__(key)[self._Field.WRITABLE]

    def allows_structural_value_replace(self, key: str) -> bool:
        """True if callers may replace the stored value of *key* via ``set_value``.

        Virtual attributes with a setter are treated as replaceable even when ``writable`` is false,
        because ``set_value`` routes through the setter.
        """
        entry = super().__getitem__(key)
        if entry[self._Field.WRITABLE]:
            return True
        return entry[self._Field.SETTER] is not None

    def virtual(self, key: str) -> bool:
        return super().__getitem__(key)[self._Field.GETTER] is not None

    def stored_value(self, key: str) -> Any:
        """Return the logical value for *key* (virtual getters run, stored values otherwise)."""
        entry = super().__getitem__(key)
        getter = entry[self._Field.GETTER]
        if getter is not None:
            return getter()
        return entry[self._Field.VALUE]

    def set_value(self, key: str, value: Any) -> None:
        """Set an attribute value respecting virtual setters and writability.

        - If a virtual setter is available, it is invoked.
        - For non-virtual entries, the stored value is updated while preserving metadata.
        - Raises KeyError for unknown keys.
        - Raises PermissionError if the entry is not writable.
        """
        entry = super().__getitem__(key)
        if not entry[self._Field.WRITABLE]:
            raise PermissionError(f"Attribute '{key}' is not writable.")

        setter = entry[self._Field.SETTER]
        if setter is not None:
            setter(value)
            return

        # Non-virtual: update the stored value without losing metadata.
        new_entry: AttributeEntry = (
            value,
            entry[self._Field.SETTER],
            entry[self._Field.GETTER],
            entry[self._Field.EXPOSED],
            entry[self._Field.WRITABLE],
        )
        super().__setitem__(key, new_entry)

