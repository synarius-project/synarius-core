"""
Pin positions in diagram / scene coordinates (must match synarius-studio ``dataflow_items`` layout).

Used to convert user-facing absolute ``orthogonal_bends`` to values stored relative to the
connector source pin.
"""

from __future__ import annotations

_UI_SCALE = 70.0 / 100.0
_MODULE = 15.0 * _UI_SCALE
_REF_PIN_MOD = 19.0
_PIN_TRI_SCALE = 2.0
_PIN_LINE_LENGTH = _MODULE * (9.0 / _REF_PIN_MOD)
_PIN_TRI_DEPTH = _MODULE * (6.0 / _REF_PIN_MOD) * _PIN_TRI_SCALE
_VARIABLE_WIDTH = 6.0 * _MODULE
_VARIABLE_HEIGHT = 2.0 * _MODULE
_OPERATOR_SIZE = 3.0 * _MODULE


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


def variable_pin_diagram_xy(inst: object, pin_name: str) -> tuple[float, float]:
    bx, by = _block_origin_scene(inst)
    cy = _VARIABLE_HEIGHT / 2.0
    w = _variable_block_width_scene(inst)
    if pin_name == "out":
        return (
            bx + w + _PIN_TRI_DEPTH + _PIN_LINE_LENGTH,
            by + cy,
        )
    if pin_name in ("in",):
        return (
            bx - _PIN_LINE_LENGTH - _PIN_TRI_DEPTH,
            by + cy,
        )
    raise ValueError(f"Unknown variable pin {pin_name!r}")


def operator_pin_diagram_xy(inst: object, pin_name: str) -> tuple[float, float]:
    bx, by = _block_origin_scene(inst)
    if pin_name == "out":
        oy = 1.5 * _MODULE
        return (
            bx + _OPERATOR_SIZE + _PIN_TRI_DEPTH + _PIN_LINE_LENGTH,
            by + oy,
        )
    if pin_name == "in1":
        iy = 0.5 * _MODULE
        return (
            bx - _PIN_LINE_LENGTH - _PIN_TRI_DEPTH,
            by + iy,
        )
    if pin_name == "in2":
        iy = 2.5 * _MODULE
        return (
            bx - _PIN_LINE_LENGTH - _PIN_TRI_DEPTH,
            by + iy,
        )
    if pin_name in ("in",):
        return operator_pin_diagram_xy(inst, "in1")
    raise ValueError(f"Unknown operator pin {pin_name!r}")


def instance_source_pin_diagram_xy(instance: object, source_pin: str) -> tuple[float, float] | None:
    """Return the source-pin attachment point for a Variable or BasicOperator, or ``None``."""
    from synarius_core.model.data_model import BasicOperator, Variable

    pin = source_pin or "out"
    if isinstance(instance, Variable):
        return variable_pin_diagram_xy(instance, pin)
    if isinstance(instance, BasicOperator):
        return operator_pin_diagram_xy(instance, pin)
    return None


def connector_source_pin_diagram_xy(model: object, connector: object) -> tuple[float, float] | None:
    from synarius_core.model.data_model import Connector

    if not isinstance(connector, Connector):
        return None
    src = model.find_by_id(connector.source_instance_id)
    if src is None:
        return None
    return instance_source_pin_diagram_xy(src, connector.source_pin)
