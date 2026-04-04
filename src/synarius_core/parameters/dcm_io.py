"""Minimal DCM (KONSERVIERUNG_FORMAT 2.0) import for ParaWiz and tooling.

Parses a small subset matching ``tests/testdata/parameter_formats/dcm/dcm2_minimal_all_types_once.dcm``:
``FESTWERT``, ``FESTWERTEBLOCK``, ``KENNLINIE``, ``KENNFELD``, ``STUETZSTELLENVERTEILUNG``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(slots=True)
class DcmImportSpec:
    name: str
    category: str
    values: np.ndarray
    axes: dict[int, np.ndarray] = field(default_factory=dict)


def _iter_body_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        out.append(line)
    return out


def _floats_after_keyword(tokens: list[str], kw: str) -> list[float]:
    if not tokens or tokens[0].upper() != kw.upper():
        raise ValueError(f"expected {kw}, got {tokens!r}")
    return [float(x) for x in tokens[1:]]


def parse_dcm_specs(text: str) -> list[DcmImportSpec]:
    lines = _iter_body_lines(text)
    i = 0
    specs: list[DcmImportSpec] = []
    while i < len(lines):
        parts = lines[i].split()
        if not parts:
            i += 1
            continue
        kw = parts[0].upper()
        if kw == "KONSERVIERUNG_FORMAT":
            i += 1
            continue
        if kw == "END":
            i += 1
            continue

        if kw == "FESTWERT":
            if len(parts) < 2:
                raise ValueError("FESTWERT requires a name")
            name = parts[1]
            i += 1
            wval: float | None = None
            while i < len(lines):
                tp = lines[i].split()
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "WERT":
                    if len(tp) < 2:
                        raise ValueError(f"WERT needs a value in {name!r}")
                    wval = float(tp[1])
                i += 1
            if wval is None:
                raise ValueError(f"FESTWERT {name!r} missing WERT")
            specs.append(DcmImportSpec(name, "VALUE", np.array(wval, dtype=np.float64)))
            continue

        if kw == "FESTWERTEBLOCK":
            if len(parts) < 3:
                raise ValueError("FESTWERTEBLOCK requires <name> <count>")
            name = parts[1]
            n = int(parts[2])
            i += 1
            block_vals: list[float] | None = None
            while i < len(lines):
                tp = lines[i].split()
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "WERT":
                    block_vals = _floats_after_keyword(tp, "WERT")
                i += 1
            if block_vals is None or len(block_vals) != n:
                raise ValueError(f"FESTWERTEBLOCK {name!r} expected {n} values, got {block_vals!r}")
            arr = np.asarray(block_vals, dtype=np.float64).reshape(n)
            specs.append(DcmImportSpec(name, "VALUE", arr))
            continue

        if kw == "KENNLINIE":
            if len(parts) < 3:
                raise ValueError("KENNLINIE requires <name> <count>")
            name = parts[1]
            nx = int(parts[2])
            i += 1
            stx: list[float] | None = None
            wrow: list[float] | None = None
            while i < len(lines):
                tp = lines[i].split()
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "ST/X":
                    stx = _floats_after_keyword(tp, "ST/X")
                elif tp and tp[0].upper() == "WERT":
                    wrow = _floats_after_keyword(tp, "WERT")
                i += 1
            if stx is None or wrow is None or len(stx) != nx or len(wrow) != nx:
                raise ValueError(f"KENNLINIE {name!r} invalid ST/X or WERT (expected {nx})")
            arr = np.asarray(wrow, dtype=np.float64).reshape(nx)
            ax = np.asarray(stx, dtype=np.float64).reshape(-1)
            specs.append(DcmImportSpec(name, "CURVE", arr, {0: ax}))
            continue

        if kw == "KENNFELD":
            if len(parts) < 4:
                raise ValueError("KENNFELD requires <name> <nx> <ny>")
            name = parts[1]
            nx = int(parts[2])
            ny = int(parts[3])
            i += 1
            stx: list[float] | None = None
            sty_order: list[float] = []
            rows: list[list[float]] = []
            while i < len(lines):
                tp = lines[i].split()
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "ST/X":
                    stx = _floats_after_keyword(tp, "ST/X")
                elif tp and tp[0].upper() == "ST/Y":
                    ys = _floats_after_keyword(tp, "ST/Y")
                    if len(ys) != 1:
                        raise ValueError(f"KENNFELD {name!r} ST/Y must be one float per row")
                    sty_order.append(ys[0])
                    i += 1
                    if i >= len(lines):
                        raise ValueError(f"KENNFELD {name!r} missing WERT after ST/Y")
                    wp = lines[i].split()
                    wvals = _floats_after_keyword(wp, "WERT")
                    if len(wvals) != nx:
                        raise ValueError(f"KENNFELD {name!r} WERT row length {len(wvals)} != nx {nx}")
                    rows.append(wvals)
                i += 1
            if stx is None or len(stx) != nx or len(rows) != ny:
                raise ValueError(f"KENNFELD {name!r} incomplete (nx={nx} ny={ny})")
            # values[xi, yi]: first index axis0 (X / ST/X), second axis1 (Y / ST/Y)
            mat = np.zeros((nx, ny), dtype=np.float64)
            for yi, wvals in enumerate(rows):
                for xi in range(nx):
                    mat[xi, yi] = wvals[xi]
            ax0 = np.asarray(stx, dtype=np.float64).reshape(-1)
            ax1 = np.asarray(sty_order, dtype=np.float64).reshape(-1)
            specs.append(DcmImportSpec(name, "MAP", mat, {0: ax0, 1: ax1}))
            continue

        if kw == "STUETZSTELLENVERTEILUNG":
            if len(parts) < 3:
                raise ValueError("STUETZSTELLENVERTEILUNG requires <name> <count>")
            name = parts[1]
            nx = int(parts[2])
            i += 1
            stx2: list[float] | None = None
            while i < len(lines):
                tp = lines[i].split()
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "ST/X":
                    stx2 = _floats_after_keyword(tp, "ST/X")
                i += 1
            if stx2 is None or len(stx2) != nx:
                raise ValueError(f"STUETZSTELLENVERTEILUNG {name!r} invalid ST/X")
            arr = np.asarray(stx2, dtype=np.float64).reshape(nx)
            specs.append(DcmImportSpec(name, "VALUE", arr))
            continue

        raise ValueError(f"Unsupported or unknown DCM keyword {kw!r} at line {lines[i]!r}")

    return specs


def import_dcm_for_dataset(controller: Any, data_set_ref: str, file_path: str) -> int:
    """Create :class:`ComplexInstance` CAL_PARAM children for each parsed object; return count."""
    path = Path(file_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    specs = parse_dcm_specs(text)
    ds = controller._resolve_ref(data_set_ref.strip())
    from synarius_core.model.data_model import ComplexInstance

    if not isinstance(ds, ComplexInstance) or ds.id is None:
        raise ValueError("data_set_ref must resolve to an attached ComplexInstance with id")

    parent = controller.current
    if not isinstance(parent, ComplexInstance):
        raise ValueError("controller cwd must be a ComplexInstance (e.g. parameters/data_sets)")

    rt = controller.model.parameter_runtime()
    n = 0
    for spec in specs:
        node = ComplexInstance(name=spec.name)
        controller.model.attach(node, parent=parent, reserve_existing=False, remap_ids=False)
        rt.register_cal_param_node(node, data_set_id=ds.id, category=spec.category)
        v = spec.values
        if v.ndim == 0:
            rt.repo.set_value(node.id, float(v.item()))
        else:
            rt.repo.set_value(node.id, v)
        for axis_idx, ax in spec.axes.items():
            rt.repo.set_axis_values(node.id, axis_idx, ax)
        n += 1

    return n
