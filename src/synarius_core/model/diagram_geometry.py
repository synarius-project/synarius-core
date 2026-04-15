"""
Pin positions in diagram / scene coordinates (must match synarius-studio ``dataflow_items`` layout).

Used to convert user-facing absolute ``orthogonal_bends`` to values stored relative to the
connector source pin.

Layout constants and shared helpers live in ``diagram_geometry_constants``.
"""

from __future__ import annotations

import math

from .diagram_geometry_constants import (
    ELEMENTARY_LIB_HEADER_GRAPHIC_HEIGHT_SCENE,
    _ELEMENTARY_LIB_GRAPHIC_GAP,
    _ELEMENTARY_LIB_HEADER_BAND_MIN,
    _ELEMENTARY_LIB_HEADER_GROUP_VPAD,
    _ELEMENTARY_LIB_PIN_ROW,
    _ELEMENTARY_LIB_TITLE_SUB_GAP,
    _GRID_HALF,
    _MODULE,
    _OPERATOR_SIZE,
    _PIN_STUB_SCENE,
    _UI_SCALE,
    _VARIABLE_HEIGHT,
    _VARIABLE_WIDTH,
    _approx_text_metrics,
    _block_origin_scene,
    _distributed_ys,
    _elementary_title_font_metrics_for_bar,
    _pin_layout_offset_y_model,
    _snap_half_module_scene,
    variable_diagram_block_width_scene,
)


def _variable_block_width_scene(inst: object) -> float:
    from synarius_core.model.data_model import Variable

    if isinstance(inst, Variable):
        return variable_diagram_block_width_scene(inst.name)
    return _VARIABLE_WIDTH


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
    from synarius_core.dataflow_sim._std_type_keys import STD_ARITHMETIC_OP

    if not isinstance(inst, ElementaryInstance):
        return None

    # Compact icon mode: std arithmetic ops use OPERATOR_SIZE square, same pin layout as BasicOperator.
    if inst.type_key in STD_ARITHMETIC_OP:
        ins = sorted(inst.in_pins, key=lambda p: p.name)
        outs = sorted(inst.out_pins, key=lambda p: p.name)
        bx, by = _block_origin_scene(inst)
        y0 = 0.5 * _MODULE
        y1 = _OPERATOR_SIZE - 0.5 * _MODULE
        ys_in = _distributed_ys(len(ins), y0, y1)
        ys_out = _distributed_ys(len(outs), y0, y1)
        for p, py in zip(ins, ys_in):
            if p.name == pin_name:
                return (bx - _PIN_STUB_SCENE, by + py)
        for p, py in zip(outs, ys_out):
            if p.name == pin_name:
                return (bx + _OPERATOR_SIZE + _PIN_STUB_SCENE, by + py)
        return (bx + _OPERATOR_SIZE * 0.5, by + _OPERATOR_SIZE * 0.5)

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
