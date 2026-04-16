from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from .attribute_dict import AttributeEntry
from .attribute_path import split_attribute_path
from .base import BaseObject
from .complex_instance import ComplexInstance
from .element_type import ModelElementType
from .geometry import Point2D, Size2D


class Signal(BaseObject):
    """Logical signal/measurement channel metadata object.

    Time-series ownership and storage are managed by the parent container
    (e.g. ``stimuli`` or ``recording``); this object exposes per-channel
    metadata through ``attribute_dict``.
    """

    def __init__(
        self,
        *,
        name: str,
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model_element_type=ModelElementType.MODEL_SIGNAL,
            obj_id=obj_id,
            parent=parent,
        )


class VariableMappingEntry(BaseObject):
    """One mapping row in ``variables_db``: variable name -> mapped stimuli signal.

    ``mapped_signal`` is owned by the model's ``VariableNameRegistry``; ``get``/``set`` on that key
    delegate to ``Model`` when attached. ``Model`` syncs the row via ``_mirror_mapped_signal_from_registry``.
    """

    def __init__(
        self,
        *,
        variable_name: str,
        mapped_signal: str = "None",
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=variable_name,
            model_element_type=ModelElementType.MODEL_VARIABLE_MAPPING,
            obj_id=obj_id,
            parent=parent,
        )
        dict.__setitem__(self.attribute_dict, "variable_name", AttributeEntry.stored(variable_name, writable=False))
        dict.__setitem__(self.attribute_dict, "mapped_signal", AttributeEntry.stored(mapped_signal, writable=True))

    def _mirror_mapped_signal_from_registry(self, signal: str) -> None:
        """Update stored ``mapped_signal`` from the SQL registry without writing the registry again."""
        text = signal if (signal and str(signal).strip() not in {"", "None"}) else "None"
        dict.__setitem__(self.attribute_dict, "mapped_signal", AttributeEntry.stored(text, writable=True))
        self._touch()

    def get(self, key: str) -> Any:
        parts = split_attribute_path(key)
        if len(parts) == 1 and parts[0] == "mapped_signal":
            model = self.get_root_model()
            if model is not None:
                return model.variable_mapped_signal(self.name)
        return super().get(key)

    def set(self, key: str, value: Any) -> None:
        parts = split_attribute_path(key)
        if len(parts) == 1 and parts[0] == "mapped_signal":
            model = self.get_root_model()
            if model is None:
                raise ValueError("VariableMappingEntry must be attached to a model to set mapped_signal")
            signal = None if value in ("None", "", None) else str(value)
            model.set_variable_mapped_signal(self.name, signal)
            return
        super().set(key, value)


class VariableDatabase(ComplexInstance):
    """Container for variable-name keyed mapping entries."""

    def __init__(
        self,
        *,
        name: str = "variables_db",
        children: Iterable[BaseObject] | None = None,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            children=children,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        self.attribute_dict["type"] = ModelElementType.MODEL_VARIABLE_DATABASE.value

    def entry_for_name(self, variable_name: str) -> VariableMappingEntry | None:
        key = variable_name.strip()
        for child in self.children:
            if isinstance(child, VariableMappingEntry) and child.name == key:
                return child
        return None


class SignalContainer(ComplexInstance):
    """Container for ``Signal`` children and their time-series data.

    The container owns the sample storage for all descendant signals; signals
    themselves only carry metadata. Storage layout and lifecycle policies
    (e.g. run-based recording reset) are implemented here.
    """

    def __init__(
        self,
        *,
        name: str,
        children: Iterable[BaseObject] | None = None,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
        model_element_type: ModelElementType = ModelElementType.MODEL_MEASUREMENTS,
    ) -> None:
        super().__init__(
            name=name,
            children=children,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        # Override the container's logical type (ComplexInstance sets MODEL_COMPLEX).
        self.attribute_dict["type"] = model_element_type.value
        # Internal storage for time-series per signal hash_name.
        # Each entry maps to a tuple (t_values, y_values), both as plain Python lists.
        self._series_store: dict[str, tuple[list[float], list[float]]] = {}

    # ---- signal / data API ---------------------------------------------------

    def clear_all_series(self) -> None:
        """Drop all stored samples for all signals in this container."""
        self._series_store.clear()

    def clear_series(self, signal: Signal) -> None:
        """Drop stored samples for a single signal."""
        self._series_store.pop(signal.hash_name, None)

    def set_series(
        self,
        signal: Signal,
        t_values: Iterable[float],
        y_values: Iterable[float],
    ) -> None:
        """Replace the full time-series for ``signal``.

        Callers are responsible for monotonically increasing ``t_values`` and
        length matching between ``t_values`` and ``y_values``.
        """
        t_list = [float(v) for v in t_values]
        y_list = [float(v) for v in y_values]
        if len(t_list) != len(y_list):
            raise ValueError("t_values and y_values must have the same length.")
        self._series_store[signal.hash_name] = (t_list, y_list)

    def append_samples(
        self,
        signal: Signal,
        t_new: Iterable[float],
        y_new: Iterable[float],
        *,
        max_points: int | None = None,
    ) -> None:
        """Append new samples to an existing series, with optional truncation."""
        t_add = [float(v) for v in t_new]
        y_add = [float(v) for v in y_new]
        if not t_add:
            return
        if len(t_add) != len(y_add):
            raise ValueError("t_new and y_new must have the same length.")

        old = self._series_store.get(signal.hash_name)
        if old is None:
            t_all, y_all = t_add, y_add
        else:
            t_old, y_old = old
            t_all = list(t_old) + t_add
            y_all = list(y_old) + y_add

        if max_points is not None and max_points > 0 and len(t_all) > max_points:
            start = len(t_all) - max_points
            t_all = t_all[start:]
            y_all = y_all[start:]

        self._series_store[signal.hash_name] = (t_all, y_all)

    def get_series(self, signal: Signal) -> tuple[list[float], list[float]]:
        """Return copies of the stored series for a signal (t, y)."""
        pair = self._series_store.get(signal.hash_name)
        if pair is None:
            return ([], [])
        t, y = pair
        return (list(t), list(y))
