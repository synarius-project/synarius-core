"""Registry mapping ``type_key`` strings to :class:`~synarius_core.plugins.element_types.ElementTypeHandler` instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synarius_core.plugins.element_types import ElementTypeHandler


class ElementTypeRegistry:
    """Authoritative ``type_key → ElementTypeHandler`` map (built from loaded plugins)."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, ElementTypeHandler] = {}

    def clear(self) -> None:
        self._handlers.clear()

    def register(self, handler: ElementTypeHandler) -> None:
        from synarius_core.plugins.element_types import ElementTypeHandler as _ETH

        if not isinstance(handler, _ETH):
            raise TypeError(f"Expected ElementTypeHandler, got {type(handler)!r}")
        self._register_one(handler.type_key, handler)
        for alias in handler.handler_aliases:
            self._register_one(alias, handler)

    def _register_one(self, key: str, handler: ElementTypeHandler) -> None:
        if not key:
            raise ValueError("Empty type_key for handler registration.")
        if key in self._handlers:
            raise ValueError(
                f"Duplicate element type registration for {key!r} "
                f"(existing={type(self._handlers[key]).__name__!r}, new={type(handler).__name__!r})."
            )
        self._handlers[key] = handler

    def get(self, type_key: str) -> ElementTypeHandler | None:
        return self._handlers.get(type_key)

    def __contains__(self, type_key: str) -> bool:
        return type_key in self._handlers

    def registered_keys(self) -> frozenset[str]:
        return frozenset(self._handlers.keys())
