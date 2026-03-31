"""Apply FMU inspection results to an :class:`~synarius_core.model.ElementaryInstance` FMU block."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from synarius_core.model import ElementaryInstance, pin_map_from_fmu_ports
from synarius_core.variable_naming import InvalidVariableNameError, validate_pin_name

from .inspection import inspect_fmu_path

_PIN_IN = frozenset({"input", "parameter"})
_PIN_OUT = frozenset({"output"})


class FmuBindError(RuntimeError):
    """Cannot bind FMU metadata onto the target object."""


def scalar_variables_to_fmu_ports(scalar_variables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build ``fmu_ports`` rows for diagram pins: inputs/parameters and outputs only."""
    ports: list[dict[str, Any]] = []
    for row in scalar_variables:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        try:
            validate_pin_name(name)
        except InvalidVariableNameError:
            continue
        causality = (row.get("causality") or "") or ""
        c = str(causality).strip().lower()
        if c in _PIN_IN:
            causality_out = "input"
        elif c in _PIN_OUT:
            causality_out = "output"
        else:
            continue
        p: dict[str, Any] = {
            "name": name,
            "causality": causality_out,
            "value_reference": row.get("value_reference"),
            "variability": row.get("variability"),
            "data_type": row.get("data_type", "float"),
        }
        for k in ("description", "unit", "start"):
            if row.get(k) is not None:
                p[k] = row[k]
        ports.append(p)
    return ports


def bind_fmu_inspection_to_elementary(
    el: ElementaryInstance,
    inspection: dict[str, Any],
    *,
    library_pin_seed: dict[str, dict[str, Any]] | None = None,
    path_override: str | None = None,
) -> None:
    """Merge ``inspection`` into ``el``\\ ``fmu`` subtree and rebuild ``pin`` from FMU ports (+ library seed).

    Preserves existing ``pin.<name>.y`` for pin names that still exist after bind.
    """
    try:
        current_fmu = el.get("fmu")
    except KeyError as exc:
        raise FmuBindError("Target has no fmu subtree (not an FMU elementary).") from exc
    if not isinstance(current_fmu, dict):
        raise FmuBindError("fmu attribute is not a mapping.")

    scalars = inspection.get("scalar_variables")
    if not isinstance(scalars, list):
        raise FmuBindError("Inspection has no scalar_variables list.")

    ports = scalar_variables_to_fmu_ports(scalars)
    port_pin = pin_map_from_fmu_ports(ports)
    lib = dict(library_pin_seed or {})
    merged_pin: dict[str, dict[str, Any]] = {**lib, **port_pin}

    try:
        old_pin = el.get("pin")
    except KeyError:
        old_pin = {}
    if isinstance(old_pin, dict):
        for pname, meta in merged_pin.items():
            prev = old_pin.get(pname)
            if isinstance(prev, dict) and prev.get("y") is not None:
                meta["y"] = prev["y"]

    new_fmu = deepcopy(current_fmu)
    new_fmu["guid"] = inspection.get("guid", new_fmu.get("guid", ""))
    new_fmu["model_identifier"] = inspection.get("model_identifier", new_fmu.get("model_identifier", ""))
    new_fmu["fmi_version"] = inspection.get("fmi_version", new_fmu.get("fmi_version", "2.0"))
    new_fmu["fmu_type"] = inspection.get("fmu_type", new_fmu.get("fmu_type", "CoSimulation"))
    for src, dst in (
        ("description", "description"),
        ("author", "author"),
        ("model_version", "model_version"),
        ("generation_tool", "generation_tool"),
        ("generation_date", "generation_date"),
    ):
        v = inspection.get(src)
        if v is not None and str(v).strip() != "":
            new_fmu[dst] = v
    if inspection.get("step_size_hint") is not None:
        new_fmu["step_size_hint"] = inspection["step_size_hint"]
    if inspection.get("start_time") is not None:
        new_fmu["start_time"] = inspection["start_time"]
    if inspection.get("stop_time") is not None:
        new_fmu["stop_time"] = inspection["stop_time"]

    vars_norm: list[dict[str, Any]] = []
    for row in scalars:
        if not isinstance(row, dict):
            continue
        entry: dict[str, Any] = dict(row)
        entry.pop("declared_type", None)
        vars_norm.append(entry)
    new_fmu["variables"] = vars_norm

    if path_override is not None and str(path_override).strip() != "":
        new_fmu["path"] = str(path_override).strip()

    el.set("fmu", new_fmu)
    el.set("pin", merged_pin)


def bind_elementary_from_fmu_path(
    el: ElementaryInstance,
    fmu_path: str,
    *,
    library_pin_seed: dict[str, dict[str, Any]] | None = None,
    set_path: bool = True,
) -> dict[str, Any]:
    """Inspect ``fmu_path`` and bind onto ``el``; if ``set_path``, update ``fmu.path``."""
    data = inspect_fmu_path(fmu_path)
    bind_fmu_inspection_to_elementary(
        el,
        data,
        library_pin_seed=library_pin_seed,
        path_override=str(data.get("path", fmu_path)) if set_path else None,
    )
    return data
