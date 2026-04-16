"""Connector domain object: source/target pins and orthogonal bend routing.

``_orthogonal_bends`` stores bend coordinates *relative* to the source-pin position
(even indices = x-offset from sx, odd indices = y-offset from sy).  The virtual attribute
``orthogonal_bends`` exposes and accepts absolute scene coordinates; the setter converts via
``connector_source_pin_diagram_xy`` from ``diagram_geometry``.

For the full storage format, the trailing-y stripping rule, and the dual-path invariant that
must be maintained between this module and ``synarius-studio/diagram/dataflow_items.py``, see
``synarius-studio/docs/developer/connector_rendering.rst``.
"""
from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from .base import BaseObject
from .complex_instance import ComplexInstance
from .connector_routing import (
    auto_orthogonal_bends,
    bends_absolute_to_relative,
    bends_relative_to_absolute,
    canonicalize_absolute_bends,
    encode_bends_from_polyline,
    polyline_for_endpoints,
    simplify_axis_aligned_polyline,
)
from .element_type import ModelElementType


class Connector(BaseObject):
    def __init__(
        self,
        *,
        name: str,
        source_instance_id: UUID,
        source_pin: str,
        target_instance_id: UUID,
        target_pin: str,
        directed: bool = True,
        orthogonal_bends: Iterable[float] | None = None,
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model_element_type=ModelElementType.MODEL_CONNECTOR,
            obj_id=obj_id,
            parent=parent,
        )
        self.source_instance_id = source_instance_id
        self.source_pin = source_pin
        self.target_instance_id = target_instance_id
        self.target_pin = target_pin
        self.directed = directed
        self._orthogonal_bends: list[float] = [float(x) for x in (orthogonal_bends or ())]
        self.attribute_dict.set_virtual(
            "orthogonal_bends",
            getter=self._get_orthogonal_bends_virtual,
            setter=self._set_orthogonal_bends,
            writable=True,
        )

    def _get_orthogonal_bends_virtual(self) -> list[float]:
        """Expose absolute diagram coordinates (CLI / lsattr); internal storage is source-relative."""
        model = self.get_root_model()
        if model is None or not self._orthogonal_bends:
            return list(self._orthogonal_bends)
        from synarius_core.model.diagram_geometry import connector_source_pin_diagram_xy

        xy = connector_source_pin_diagram_xy(model, self)
        if xy is None:
            return list(self._orthogonal_bends)
        sx, sy = xy
        return bends_relative_to_absolute(sx, sy, self._orthogonal_bends)

    def _set_orthogonal_bends(self, value: Any) -> None:
        if value is None:
            self._orthogonal_bends = []
            self._touch()
            return
        if isinstance(value, str):
            parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
            abs_list = [float(p) for p in parts]
        elif isinstance(value, (list, tuple)):
            abs_list = [float(x) for x in value]
        else:
            raise TypeError("orthogonal_bends expects list/tuple of numbers or comma-separated string.")
        model = self.get_root_model()
        from synarius_core.model.diagram_geometry import (
            connector_source_pin_diagram_xy,
            connector_target_pin_diagram_xy,
        )

        xy_src = connector_source_pin_diagram_xy(model, self) if model is not None else None
        xy_tgt = connector_target_pin_diagram_xy(model, self) if model is not None else None
        if xy_src is not None and xy_tgt is not None:
            sx, sy = xy_src
            tx, ty = xy_tgt
            abs_list = canonicalize_absolute_bends(sx, sy, tx, ty, abs_list)
            # Strip trailing y-coordinate: the final approach y is always derived from the
            # target pin's ty by the routing finish functions, so storing it explicitly is
            # redundant and causes extra visible steps on imprecise placement.
            if len(abs_list) >= 2 and len(abs_list) % 2 == 0:
                abs_list = abs_list[:-1]
            self._orthogonal_bends = bends_absolute_to_relative(sx, sy, abs_list)
        elif xy_src is not None:
            sx, sy = xy_src
            self._orthogonal_bends = bends_absolute_to_relative(sx, sy, abs_list)
        else:
            self._orthogonal_bends = abs_list
        self._touch()

    def polyline_xy(
        self,
        source_xy: tuple[float, float],
        target_xy: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Scene/model-space vertices for current ``orthogonal_bends`` (or auto layout)."""
        sx, sy = source_xy
        tx, ty = target_xy
        if not self._orthogonal_bends:
            return polyline_for_endpoints(sx, sy, tx, ty, [])
        abs_b = bends_relative_to_absolute(sx, sy, self._orthogonal_bends)
        return polyline_for_endpoints(sx, sy, tx, ty, abs_b)

    def materialize_default_bends(self, source_xy: tuple[float, float], target_xy: tuple[float, float]) -> None:
        """If bends are empty, set default H–V–H bends when geometry needs a knee."""
        if self._orthogonal_bends:
            return
        sx, sy = source_xy
        tx, ty = target_xy
        b = auto_orthogonal_bends(sx, sy, tx, ty)
        if b:
            self._orthogonal_bends = bends_absolute_to_relative(sx, sy, b)
            self._touch()

    def apply_polyline(self, poly: list[tuple[float, float]], source_xy: tuple[float, float], target_xy: tuple[float, float]) -> None:
        """Replace bends from a full orthogonal polyline S→T."""
        sx, sy = source_xy
        tx, ty = target_xy
        sim = simplify_axis_aligned_polyline([(float(x), float(y)) for x, y in poly])
        try:
            enc = encode_bends_from_polyline(sx, sy, tx, ty, sim)
        except ValueError:
            enc = []
        if enc:
            enc = canonicalize_absolute_bends(sx, sy, tx, ty, enc)
        self._orthogonal_bends = bends_absolute_to_relative(sx, sy, enc) if enc else []
        self._touch()

    def validate_endpoints(self) -> bool:
        return bool(self.source_pin) and bool(self.target_pin)
