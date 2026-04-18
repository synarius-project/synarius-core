from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

SetterFunction = Callable[[Any], None]
GetterFunction = Callable[[], Any]


@dataclasses.dataclass(frozen=True)
class AttributeEntry:
    """Immutable metadata record for one model attribute slot.

    Fields
    ------
    value
        Stored value for non-virtual attributes; ``None`` and ignored when the
        entry is virtual (i.e. *getter* is not ``None``).
    setter / getter
        Callable contracts for virtual attributes; ``None`` for stored entries.
    exposed
        Whether the attribute is visible via the public protocol surface
        (``lsattr``, CCP introspection).  Defaults to ``True``.
    writable
        Whether :meth:`~AttributeDict.set_value` (or ``BaseObject.set``) may
        overwrite this attribute.  Defaults to ``False``.
    value_spec
        Optional callable ``(Any) -> Any`` that **validates and returns** the
        canonical stored value at the write boundary.  ``None`` means no
        automatic boundary check (legacy / polymorphic keys).

        **Hard rule:** ``value_spec`` MUST be ``None`` whenever *setter* is not
        ``None`` — the setter IS the write contract for virtual attributes.
        :meth:`~AttributeDict.set_value` does NOT run ``value_spec`` on the
        virtual path.
    """

    value: Any = None
    setter: SetterFunction | None = None
    getter: GetterFunction | None = None
    exposed: bool = True
    writable: bool = False
    value_spec: Callable[[Any], Any] | None = None
    bounds: tuple[float, float] | None = None
    unit: str = ""
    enum_values: list[str] | None = None
    docstring: str = ""

    def __post_init__(self) -> None:
        if self.setter is not None and self.value_spec is not None:
            raise ValueError(
                "Virtual attributes (setter is not None) must not carry value_spec. "
                f"Got value_spec={self.value_spec!r}. The setter is the write contract."
            )

    @classmethod
    def stored(
        cls,
        value: Any,
        *,
        exposed: bool = True,
        writable: bool = False,
        value_spec: Callable[[Any], Any] | None = None,
        bounds: tuple[float, float] | None = None,
        unit: str = "",
        enum_values: list[str] | None = None,
        docstring: str = "",
    ) -> AttributeEntry:
        """Create a stored (non-virtual) attribute entry."""
        return cls(
            value=value,
            exposed=exposed,
            writable=writable,
            value_spec=value_spec,
            bounds=bounds,
            unit=unit,
            enum_values=enum_values,
            docstring=docstring,
        )

    @classmethod
    def virtual(
        cls,
        getter: GetterFunction,
        setter: SetterFunction | None = None,
        *,
        exposed: bool = True,
        writable: bool = False,
    ) -> AttributeEntry:
        """Create a virtual attribute entry backed by *getter* / *setter* callables."""
        return cls(getter=getter, setter=setter, exposed=exposed, writable=writable)


def _as_entry(raw: object) -> AttributeEntry:
    """Normalise a raw dict value to an :class:`AttributeEntry`.

    During the adapter window, direct ``dict.__setitem__`` bypass writes may
    still produce legacy 5-tuples ``(value, setter, getter, exposed, writable)``.
    This helper accepts both forms so that all :class:`AttributeDict` methods
    work uniformly with :class:`AttributeEntry` objects.

    Once all bypass write sites have been migrated, this function will only
    ever receive :class:`AttributeEntry` instances and the fast-path ``isinstance``
    check will always win.
    """
    if isinstance(raw, AttributeEntry):
        return raw
    # Legacy 5-tuple: (value, setter, getter, exposed, writable)
    value, setter, getter, exposed, writable = raw  # type: ignore[misc]
    return AttributeEntry(value=value, setter=setter, getter=getter, exposed=exposed, writable=writable)


class AttributeDict(dict[str, AttributeEntry]):
    """Dictionary for model attributes with protocol-related metadata.

    Each entry is an :class:`AttributeEntry` frozen dataclass holding the
    stored value (or virtual getter/setter) together with access-control
    metadata (``exposed``, ``writable``, optional ``value_spec``).

    Write boundary
    --------------
    :meth:`set_value` is the **canonical write path** for stored attributes.
    It enforces writability, runs ``value_spec`` (if present), and persists the
    new value via ``dataclasses.replace`` — preserving all metadata.

    Direct ``dict.__setitem__`` bypasses (needed when full metadata must be
    set at construction time) MUST supply an :class:`AttributeEntry` instance
    using the factory helpers :meth:`~AttributeEntry.stored` or
    :meth:`~AttributeEntry.virtual`.
    """

    def __setitem__(self, key: str, value: Any) -> None:
        """Convenience write: stores *value* as an exposed, non-writable entry."""
        super().__setitem__(key, AttributeEntry.stored(value, exposed=True, writable=False))

    def set_virtual(
        self,
        key: str,
        getter: GetterFunction,
        setter: SetterFunction | None = None,
        *,
        exposed: bool = True,
        writable: bool = False,
    ) -> None:
        """Register a virtual attribute entry backed by *getter* / *setter* callables."""
        super().__setitem__(key, AttributeEntry.virtual(getter, setter, exposed=exposed, writable=writable))

    def __getitem__(self, key: str) -> Any:
        entry = _as_entry(super().__getitem__(key))
        if entry.getter is not None:
            return entry.getter()
        return entry.value

    def exposed(self, key: str) -> bool:
        return _as_entry(super().__getitem__(key)).exposed

    def writable(self, key: str) -> bool:
        return _as_entry(super().__getitem__(key)).writable

    def allows_structural_value_replace(self, key: str) -> bool:
        """True if callers may replace the stored value of *key* via :meth:`set_value`.

        Virtual attributes with a setter are treated as replaceable even when ``writable``
        is false, because :meth:`set_value` routes through the setter.
        """
        entry = _as_entry(super().__getitem__(key))
        if entry.writable:
            return True
        return entry.setter is not None

    def virtual(self, key: str) -> bool:
        return _as_entry(super().__getitem__(key)).getter is not None

    def stored_value(self, key: str) -> Any:
        """Return the logical value for *key* (virtual getters run, stored values returned directly)."""
        entry = _as_entry(super().__getitem__(key))
        if entry.getter is not None:
            return entry.getter()
        return entry.value

    def set_value(self, key: str, value: Any) -> None:
        """Set an attribute value respecting virtual setters, writability, and ``value_spec``.

        - **Virtual path** (``setter`` is not ``None``): invokes the setter; ``value_spec``
          is not run — the setter is the full write contract.
        - **Stored path**: runs ``value_spec`` (if present) then updates the stored value
          via ``dataclasses.replace``, preserving all metadata.
        - Raises ``KeyError`` for unknown keys.
        - Raises ``PermissionError`` if the entry is not writable.
        """
        entry = _as_entry(super().__getitem__(key))
        if not entry.writable:
            raise PermissionError(f"Attribute '{key}' is not writable.")

        if entry.setter is not None:
            # Virtual path: setter is the full write contract; do not run value_spec.
            entry.setter(value)
            return

        # Non-virtual path: run value_spec (if present), then persist.
        if entry.value_spec is not None:
            value = entry.value_spec(value)

        super().__setitem__(key, dataclasses.replace(entry, value=value))
