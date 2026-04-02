"""
Pin positions in diagram / scene coordinates (must match synarius-studio ``dataflow_items`` layout).

Used to convert user-facing absolute ``orthogonal_bends`` to values stored relative to the
connector source pin.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import time

_UI_SCALE = 70.0 / 100.0
_MODULE = 15.0 * _UI_SCALE
_REF_PIN_MOD = 19.0
_PIN_TRI_SCALE = 2.0
# Must match synarius-studio ``dataflow_items.PIN_LINE_LENGTH`` (15/19 of MODULE).
_PIN_LINE_LENGTH = _MODULE * (15.0 / _REF_PIN_MOD)
_PIN_TRI_DEPTH = _MODULE * (6.0 / _REF_PIN_MOD) * _PIN_TRI_SCALE
_GRID_HALF = _MODULE * 0.5
_PIN_STUB_RAW = _PIN_LINE_LENGTH + _PIN_TRI_DEPTH
# Half-module–aligned stub (matches studio ``PIN_STUB_OUTER_REACH``).
_PIN_STUB_SCENE = max(
    _PIN_TRI_DEPTH + 1e-9,
    round(_PIN_STUB_RAW / _GRID_HALF) * _GRID_HALF,
)
# Pin-row pitch for multi-pin elementary lib blocks; must match synarius-studio ``dataflow_items.ELEMENTARY_LIB_PIN_ROW``.
_ELEMENTARY_LIB_PIN_ROW = _MODULE * 1.52
# Header band for multi-pin elementary library blocks (FMU, future lib types); not FMU-specific.
_ELEMENTARY_LIB_HEADER_BAND_MIN = _MODULE * 1.38
_ELEMENTARY_LIB_TITLE_SUB_GAP = _MODULE * 0.1
_ELEMENTARY_LIB_GRAPHIC_GAP = _MODULE * 0.12
_ELEMENTARY_LIB_HEADER_GROUP_VPAD = _MODULE * 0.24
# Optional square header graphic below title (studio ``FmuBlockItem`` / same family); keep in sync when enabling.
ELEMENTARY_LIB_HEADER_GRAPHIC_HEIGHT_SCENE = 0.0
_VARIABLE_WIDTH = 6.0 * _MODULE
_VARIABLE_HEIGHT = 2.0 * _MODULE
_OPERATOR_SIZE = 3.0 * _MODULE


def _agent_debug_log_ccbe80(*, run_id: str, hypothesis_id: str, message: str, data: dict[str, object]) -> None:
    #region agent log
    try:
        payload = {
            "sessionId": "ccbe80",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": "diagram_geometry.py:import_phase",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with Path("debug-ccbe80.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    #endregion


_agent_debug_log_ccbe80(
    run_id="pre-fix",
    hypothesis_id="H_STALE_MODULE",
    message="diagram_geometry_module_loaded",
    data={
        "module_file": __file__,
        "python": sys.version.split()[0],
        "has_graphic_height_symbol": "ELEMENTARY_LIB_HEADER_GRAPHIC_HEIGHT_SCENE" in globals(),
        "graphic_height_value": float(ELEMENTARY_LIB_HEADER_GRAPHIC_HEIGHT_SCENE),
    },
)


def _approx_text_metrics(name: str, pixel_size: float) -> tuple[float, float]:
    """Approximate Qt label (width, height) in scene pixels for sans-serif Medium."""
    if not name:
        return (float(pixel_size), pixel_size * 1.18)
    adv = 0.58 * pixel_size
    w = 0.0
    for ch in name:
        if ch.isascii() and ch.isdigit():
            w += adv * 0.62
        elif ch.isascii() and ch in "ijl1|.!,:;'":
            w += adv * 0.32
        elif ch.isascii() and ch in "mwMW%@":
            w += adv * 1.12
        elif ch.isascii() and ch.isupper():
            w += adv * 0.85
        else:
            w += adv * 1.05
    h = pixel_size * 1.18
    return (max(w, adv * 0.5), h)


def variable_diagram_block_width_scene(name: str) -> float:
    """Scene-pixel width of a variable block (>= default); widens when the name needs horizontal space.

    Kept in sync with synarius-studio ``VariableBlockItem`` layout (margins + font sizing by height).
    """
    margin_h = max(1.0, _VARIABLE_HEIGHT * 0.08)
    tol_w = max(1.0, _VARIABLE_HEIGHT * 0.06)
    inner_h = _VARIABLE_HEIGHT - 2.0 * margin_h
    lo, hi = 4, max(6, int(_VARIABLE_HEIGHT * 3.0))
    best = 4
    while lo <= hi:
        mid = (lo + hi) // 2
        _tw, th = _approx_text_metrics(name, float(mid))
        if th <= inner_h:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    ps = max(4, best)
    tw, _th = _approx_text_metrics(name, float(ps))
    need = tw + 2.0 * tol_w
    return max(_VARIABLE_WIDTH, need * 1.04)


def _variable_block_width_scene(inst: object) -> float:
    from synarius_core.model.data_model import Variable

    if isinstance(inst, Variable):
        return variable_diagram_block_width_scene(inst.name)
    return _VARIABLE_WIDTH


def _block_origin_scene(inst: object) -> tuple[float, float]:
    return (float(inst.x) * _UI_SCALE, float(inst.y) * _UI_SCALE)


def _pin_layout_offset_y_model(inst: object, pin_name: str) -> float | None:
    get = getattr(inst, "get", None)
    if not callable(get):
        return None
    try:
        y = get(f"pin.{pin_name}.y")
    except KeyError:
        return None
    if y is None:
        return None
    try:
        return float(y)
    except (TypeError, ValueError):
        return None


def variable_pin_diagram_xy(inst: object, pin_name: str) -> tuple[float, float]:
    bx, by = _block_origin_scene(inst)
    cy = _VARIABLE_HEIGHT / 2.0
    dy = _pin_layout_offset_y_model(inst, pin_name)
    if dy is not None:
        cy += dy * _UI_SCALE
    w = _variable_block_width_scene(inst)
    if pin_name == "out":
        return (
            bx + w + _PIN_STUB_SCENE,
            by + cy,
        )
    if pin_name in ("in",):
        return (
            bx - _PIN_STUB_SCENE,
            by + cy,
        )
    raise ValueError(f"Unknown variable pin {pin_name!r}")


def _distributed_ys(n: int, y0: float, y1: float) -> list[float]:
    if n <= 0:
        return []
    if n == 1:
        return [(y0 + y1) * 0.5]
    return [y0 + (y1 - y0) * i / (n - 1) for i in range(n)]


def _snap_half_module_scene(v: float) -> float:
    return round(v / _GRID_HALF) * _GRID_HALF


def _elementary_title_font_metrics_for_bar(title: str) -> tuple[int, float, float]:
    """Chosen pixel size and (width, height) for the title line (same search as studio header font)."""
    margin_h = max(1.0, _VARIABLE_HEIGHT * 0.08)
    tol_w = max(1.0, _VARIABLE_HEIGHT * 0.06)
    inner_h = _VARIABLE_HEIGHT - 2.0 * margin_h
    inner_w = 999.0
    lo, hi = 4, max(6, int(_VARIABLE_HEIGHT * 3.0))
    best = 4
    while lo <= hi:
        mid = (lo + hi) // 2
        _tw, th = _approx_text_metrics(title, float(mid))
        if th <= inner_h and _tw <= inner_w - 2.0 * tol_w:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    ps = max(4, best)
    tw, t_h = _approx_text_metrics(title, float(ps))
    return ps, tw, t_h


def elementary_lib_header_height_scene(title: str, subtitle: str, graphic_h: float = 0.0) -> float:
    """
    Height of the multi-pin elementary library block header band. The **primary title** uses the
    same vertical centering idea as ``VariableBlockItem`` inside this band; subtitle and optional
    graphic sit below, so the band may grow to keep ``(header_h - title_h)/2 - nudge + stack <= header_h``.
    """
    _ps, _tw, title_h = _elementary_title_font_metrics_for_bar(title)
    text_stack = title_h
    if subtitle.strip():
        ps2 = max(7, int(_MODULE * 0.78))
        _sw, sub_h = _approx_text_metrics(subtitle.strip()[:28], float(ps2))
        text_stack += _ELEMENTARY_LIB_TITLE_SUB_GAP + sub_h
    gap_tg = _ELEMENTARY_LIB_GRAPHIC_GAP if graphic_h > 0.0 else 0.0
    stack_h = text_stack + gap_tg + float(graphic_h)
    # Header must fit ``ly + stack_h <= header_h`` with ``ly = (header_h - title_h)/2 - nudge``
    # (same idea as VariableBlockItem: primary title vertically centered in the header band).
    nudge = 0.1 * title_h
    min_for_title_centered = max(0.0, 2.0 * stack_h - title_h - 2.0 * nudge) + 2.0
    return max(
        _ELEMENTARY_LIB_HEADER_BAND_MIN,
        stack_h + _ELEMENTARY_LIB_HEADER_GROUP_VPAD,
        min_for_title_centered,
    )


def _elementary_title_bar_inner_width_scene(title: str, subtitle: str) -> float:
    """Match synarius-studio elementary block inner width (title + optional sub-label)."""
    _ps, tw, _th = _elementary_title_font_metrics_for_bar(title)
    if subtitle.strip():
        ps2 = max(7, int(_MODULE * 0.78))
        sw, _ = _approx_text_metrics(subtitle.strip()[:28], float(ps2))
        tw = max(tw, sw)
    return max(4.8 * _MODULE, tw + _MODULE * 1.4)


def elementary_lib_block_pin_diagram_xy(inst: object, pin_name: str) -> tuple[float, float] | None:
    """Elementary library block pins (multi in/out); mirrors ``FmuBlockItem`` / studio layout."""
    from synarius_core.model.data_model import ElementaryInstance, elementary_diagram_subtitle_for_geometry

    if not isinstance(inst, ElementaryInstance):
        return None
    ins = sorted(inst.in_pins, key=lambda p: p.name)
    outs = sorted(inst.out_pins, key=lambda p: p.name)
    n_in, n_out = len(ins), len(outs)
    pin_rows = max(n_in, n_out, 1)

    sub = elementary_diagram_subtitle_for_geometry(inst)

    inner_w = _elementary_title_bar_inner_width_scene(inst.name, sub)
    header_h = elementary_lib_header_height_scene(inst.name, sub, ELEMENTARY_LIB_HEADER_GRAPHIC_HEIGHT_SCENE)
    pin_area_h = max(_ELEMENTARY_LIB_PIN_ROW, pin_rows * _ELEMENTARY_LIB_PIN_ROW)
    block_h_raw = header_h + pin_area_h + _MODULE * 0.55
    min_bw = inner_w + _MODULE * 2.4
    block_w = max(min_bw, math.ceil(min_bw / _GRID_HALF) * _GRID_HALF)
    block_h = max(block_h_raw, math.ceil(block_h_raw / _GRID_HALF) * _GRID_HALF)

    bx, by = _block_origin_scene(inst)
    y0 = header_h + _ELEMENTARY_LIB_PIN_ROW * 0.35
    y1 = header_h + pin_area_h - _ELEMENTARY_LIB_PIN_ROW * 0.35
    ys_in = [_snap_half_module_scene(y) for y in _distributed_ys(n_in, y0, y1)]
    ys_out = [_snap_half_module_scene(y) for y in _distributed_ys(n_out, y0, y1)]

    for p, py in zip(ins, ys_in):
        if p.name == pin_name:
            return (
                bx - _PIN_STUB_SCENE,
                by + py,
            )
    for p, py in zip(outs, ys_out):
        if p.name == pin_name:
            return (
                bx + block_w + _PIN_STUB_SCENE,
                by + py,
            )
    return (bx + block_w * 0.5, by + block_h * 0.5)


def operator_pin_diagram_xy(inst: object, pin_name: str) -> tuple[float, float]:
    bx, by = _block_origin_scene(inst)
    dy = _pin_layout_offset_y_model(inst, pin_name)
    dy_scene = 0.0 if dy is None else dy * _UI_SCALE
    if pin_name == "out":
        oy = 1.5 * _MODULE + dy_scene
        return (
            bx + _OPERATOR_SIZE + _PIN_STUB_SCENE,
            by + oy,
        )
    if pin_name == "in1":
        iy = 0.5 * _MODULE + dy_scene
        return (
            bx - _PIN_STUB_SCENE,
            by + iy,
        )
    if pin_name == "in2":
        iy = 2.5 * _MODULE + dy_scene
        return (
            bx - _PIN_STUB_SCENE,
            by + iy,
        )
    if pin_name in ("in",):
        return operator_pin_diagram_xy(inst, "in1")
    raise ValueError(f"Unknown operator pin {pin_name!r}")


def instance_source_pin_diagram_xy(instance: object, source_pin: str) -> tuple[float, float] | None:
    """Return the source-pin attachment point for diagram blocks, or ``None``."""
    from synarius_core.model.data_model import BasicOperator, ElementaryInstance, Variable

    pin = source_pin or "out"
    if isinstance(instance, Variable):
        return variable_pin_diagram_xy(instance, pin)
    if isinstance(instance, BasicOperator):
        return operator_pin_diagram_xy(instance, pin)
    if isinstance(instance, ElementaryInstance):
        return elementary_lib_block_pin_diagram_xy(instance, pin)
    return None


def connector_source_pin_diagram_xy(model: object, connector: object) -> tuple[float, float] | None:
    from synarius_core.model.data_model import Connector

    if not isinstance(connector, Connector):
        return None
    src = model.find_by_id(connector.source_instance_id)
    if src is None:
        return None
    return instance_source_pin_diagram_xy(src, connector.source_pin)


def connector_target_pin_diagram_xy(model: object, connector: object) -> tuple[float, float] | None:
    from synarius_core.model.data_model import Connector

    if not isinstance(connector, Connector):
        return None
    tgt = model.find_by_id(connector.target_instance_id)
    if tgt is None:
        return None
    return instance_source_pin_diagram_xy(tgt, connector.target_pin)


# Backward-compatible name (same layout as multi-pin elementary / FMU blocks).
elementary_fmu_pin_diagram_xy = elementary_lib_block_pin_diagram_xy
