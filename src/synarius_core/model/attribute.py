from __future__ import annotations

from typing import Any


class Attribute:
    """Represents a single attribute on a model object.

    The flags ``virtual``, ``exposed`` and ``writable`` are implemented
    as Python properties to allow validation or dynamic behavior later.
    """

    def __init__(
        self,
        name: str,
        value: Any,
        *,
        virtual: bool = False,
        exposed: bool = True,
        writable: bool = True,
    ) -> None:
        self.name = name
        self.value = value
        self._virtual = bool(virtual)
        self._exposed = bool(exposed)
        self._writable = bool(writable)

    @property
    def virtual(self) -> bool:
        return self._virtual

    @virtual.setter
    def virtual(self, value: bool) -> None:
        self._virtual = bool(value)

    @property
    def exposed(self) -> bool:
        return self._exposed

    @exposed.setter
    def exposed(self, value: bool) -> None:
        self._exposed = bool(value)

    @property
    def writable(self) -> bool:
        return self._writable

    @writable.setter
    def writable(self, value: bool) -> None:
        self._writable = bool(value)


