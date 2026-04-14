from __future__ import annotations

from enum import Enum
from typing import Any, Iterable
from uuid import UUID

from synarius_core.variable_naming import validate_pin_name

from .base import LocatableInstance
from .complex_instance import ComplexInstance
from .element_type import ModelElementType
from .geometry import Point2D, Size2D
from .pin_helpers import (
    Pin,
    PinDataType,
    PinDirection,
    _normalize_fmu_variable_rows,
    _pin_map_from_legacy,
    pin_map_from_fmu_ports,
)


class BasicOperatorType(str, Enum):
    PLUS = "+"
    MINUS = "-"
    MULTIPLY = "*"
    DIVIDE = "/"


class ElementaryInstance(LocatableInstance):
    def __init__(
        self,
        *,
        name: str,
        type_key: str,
        model_element_type: ModelElementType = ModelElementType.MODEL_ELEMENTARY,
        pin: dict[str, dict[str, Any]] | None = None,
        in_pins: Iterable[Pin] | None = None,
        out_pins: Iterable[Pin] | None = None,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model_element_type=model_element_type,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        self.type_key = type_key
        merged = _pin_map_from_legacy(pin=pin, in_pins=in_pins, out_pins=out_pins)
        dict.__setitem__(self.attribute_dict, "pin", (merged, None, None, True, True))
        self._install_default_pins_for_element()

    def _install_default_pins_for_element(self) -> None:
        """Populate built-in pins for leaf diagram element types (override in subclasses)."""
        return

    def _pins_filtered(self, direction: PinDirection) -> list[Pin]:
        pmap = self.get("pin")
        out: list[Pin] = []
        for pname, meta in sorted(pmap.items(), key=lambda kv: kv[0]):
            if meta.get("direction") == direction.value:
                dt_raw = meta.get("data_type", PinDataType.FLOAT.value)
                try:
                    dt = PinDataType(dt_raw)
                except ValueError:
                    dt = PinDataType.FLOAT
                out.append(Pin(name=pname, direction=direction, data_type=dt))
        return out

    @property
    def in_pins(self) -> list[Pin]:
        return self._pins_filtered(PinDirection.IN)

    @property
    def out_pins(self) -> list[Pin]:
        return self._pins_filtered(PinDirection.OUT)


DEFAULT_FMU_LIBRARY_TYPE_KEY = "std.FmuCoSimulation"
"""Default ``type_key`` for FMU co-simulation blocks (FMF library element when bundled)."""


def elementary_diagram_subtitle_for_geometry(inst: object) -> str:
    """Optional second line under the block title (``diagram.subtitle``), for width/pin alignment.

    Any library elementary may set ``diagram.subtitle``. FMU blocks also populate it from
    ``model_identifier`` at creation time. Older instances without ``diagram.subtitle`` still
    fall back to ``fmu.model_identifier`` so geometry matches existing diagrams.
    """
    if not isinstance(inst, ElementaryInstance):
        return ""
    try:
        v = inst.get("diagram.subtitle")
        if isinstance(v, str) and v.strip():
            return v.strip()[:28]
    except (KeyError, TypeError, ValueError):
        pass
    try:
        mid = inst.get("fmu.model_identifier")
        if isinstance(mid, str) and mid.strip():
            return mid.strip()[:28]
    except (KeyError, TypeError, ValueError):
        pass
    return ""


def elementary_fmu_block(
    *,
    name: str,
    type_key: str,
    fmu_path: str,
    fmi_version: str,
    fmu_type: str,
    guid: str = "",
    model_identifier: str = "",
    fmu_description: str = "",
    fmu_author: str = "",
    fmu_model_version: str = "",
    fmu_generation_tool: str = "",
    fmu_generation_date: str = "",
    step_size_hint: float | None = None,
    tolerance: float | None = None,
    start_time: float | None = None,
    stop_time: float | None = None,
    fmu_ports: list[dict[str, Any]] | None = None,
    fmu_variables: list[dict[str, Any]] | None = None,
    pin: dict[str, dict[str, Any]] | None = None,
    fmu_extra_meta: dict[str, Any] | None = None,
    library_pin_seed: dict[str, dict[str, Any]] | None = None,
    in_pins: Iterable[Pin] | None = None,
    out_pins: Iterable[Pin] | None = None,
    position: Point2D | tuple[float, float] = (0.0, 0.0),
    size: Size2D = Size2D(1.0, 1.0),
    obj_id: UUID | None = None,
    parent: ComplexInstance | None = None,
) -> ElementaryInstance:
    """Diagram block carrying FMU configuration under the ``fmu`` attribute subtree (``MODEL.ELEMENTARY``).

    * ``fmu_ports`` — defines diagram :attr:`pin` entries (connector endpoint names, direction, ``value_reference``, …).
    * ``fmu_variables`` — optional full variable catalog under ``fmu.variables`` (FMI scalar metadata); diagram wires
      use **the same** ``name`` strings as in :attr:`pin` / ``fmu_ports`` when a port maps to an FMU variable.
    """
    port_pin = pin_map_from_fmu_ports(fmu_ports)
    explicit_pin = {str(k): dict(v) for k, v in (pin or {}).items()}
    for pname in explicit_pin:
        validate_pin_name(pname)
    seed = {**dict(library_pin_seed or {}), **port_pin, **explicit_pin}
    merged_for_ctor: dict[str, dict[str, Any]] | None = seed if seed else None
    el = ElementaryInstance(
        name=name,
        type_key=type_key,
        pin=merged_for_ctor,
        in_pins=in_pins,
        out_pins=out_pins,
        position=position,
        size=size,
        obj_id=obj_id,
        parent=parent,
    )
    fmu_body: dict[str, Any] = {
        "path": fmu_path,
        "fmi_version": fmi_version,
        "fmu_type": fmu_type,
        "guid": guid,
        "model_identifier": model_identifier,
        "description": fmu_description,
        "author": fmu_author,
        "model_version": fmu_model_version,
        "generation_tool": fmu_generation_tool,
        "generation_date": fmu_generation_date,
        "step_size_hint": step_size_hint,
        "tolerance": tolerance,
        "start_time": start_time,
        "stop_time": stop_time,
        "extra_meta": dict(fmu_extra_meta or {}),
        "variables": _normalize_fmu_variable_rows(fmu_variables),
    }
    dict.__setitem__(el.attribute_dict, "fmu", (fmu_body, None, None, True, True))
    if isinstance(model_identifier, str) and model_identifier.strip():
        dict.__setitem__(
            el.attribute_dict,
            "diagram",
            ({"subtitle": model_identifier.strip()[:28]}, None, None, True, True),
        )
    return el
