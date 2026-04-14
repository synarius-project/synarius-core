from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from synarius_core.variable_naming import validate_pin_name


class PinDirection(str, Enum):
    IN = "IN"
    OUT = "OUT"


class PinDataType(str, Enum):
    FLOAT = "float"


@dataclass(slots=True)
class Pin:
    name: str
    direction: PinDirection
    data_type: PinDataType


def _pin_map_from_legacy(
    *,
    pin: dict[str, dict[str, Any]] | None,
    in_pins: Iterable[Pin] | None,
    out_pins: Iterable[Pin] | None,
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if pin:
        for pname, meta in pin.items():
            validate_pin_name(pname)
            merged[pname] = dict(meta)
    if in_pins:
        for p in in_pins:
            merged[p.name] = {
                "direction": p.direction.value,
                "data_type": p.data_type.value,
                "y": None,
            }
    if out_pins:
        for p in out_pins:
            merged[p.name] = {
                "direction": p.direction.value,
                "data_type": p.data_type.value,
                "y": None,
            }
    return merged


def pin_map_from_library_ports(ports: list[tuple[str, str, str]]) -> dict[str, dict[str, Any]]:
    """Build ``pin`` entries from FMF ``libraryDescription`` port tuples (kind, name, type)."""
    out: dict[str, dict[str, Any]] = {}
    for kind, pname, typ in ports:
        if not pname:
            continue
        validate_pin_name(pname)
        k = (kind or "").lower()
        if k in ("in", "input"):
            direction = PinDirection.IN.value
        elif k in ("out", "output"):
            direction = PinDirection.OUT.value
        else:
            direction = PinDirection.IN.value
        dt = str(typ or PinDataType.FLOAT.value).lower()
        if dt in ("real", "float", "double"):
            data_type = PinDataType.FLOAT.value
        elif dt in ("int", "integer"):
            data_type = "int"
        elif dt == "bool":
            data_type = "bool"
        elif dt == "string":
            data_type = "string"
        else:
            data_type = PinDataType.FLOAT.value
        out[pname] = {"direction": direction, "data_type": data_type, "y": None}
    return out


def _normalize_fmu_variable_rows(raw_list: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Build persisted ``fmu.variables`` list: FMI-like scalar metadata (name, value_reference, causality, …)."""
    out: list[dict[str, Any]] = []
    for raw in raw_list or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        row: dict[str, Any] = {"name": name}
        vr = raw.get("value_reference")
        if vr is not None:
            try:
                row["value_reference"] = int(vr)
            except (TypeError, ValueError):
                row["value_reference"] = vr
        for key in ("causality", "variability"):
            if key in raw and raw[key] is not None and raw[key] != "":
                row[key] = str(raw[key]).strip().lower()
        for key in ("data_type", "description", "unit", "declared_type"):
            if key in raw and raw[key] is not None and raw[key] != "":
                row[key] = raw[key]
        for key in ("initial", "start"):
            if key in raw:
                row[key] = raw[key]
        for k, v in raw.items():
            if k in row or k == "name":
                continue
            row[k] = v
        out.append(row)
    return out


def pin_map_from_fmu_ports(ports: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in ports or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        validate_pin_name(name)
        causality = str(raw.get("causality", "")).lower()
        direction = PinDirection.OUT.value if causality in ("output",) else PinDirection.IN.value
        row: dict[str, Any] = {
            "direction": direction,
            "data_type": str(raw.get("data_type", PinDataType.FLOAT.value)),
            "y": raw.get("y", None),
        }
        for k, v in raw.items():
            if k in ("name", "causality", "direction", "data_type", "y"):
                continue
            row[k] = v
        out[name] = row
    return out


def _shallow_nested_pin_copy(pmap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(k): dict(v) for k, v in pmap.items() if isinstance(v, dict)}
