"""Scene/layout constants and low-level helpers for ``diagram_geometry`` (Studio alignment).

Each constant that mirrors a value from ``synarius-studio/src/synarius_studio/diagram/dataflow_items.py``
carries a comment naming the studio counterpart.  Keep them in sync: a divergence causes a
pixel-level mismatch between the core's pin-position calculation and the studio's rendered position,
which manifests as connector bend drift after drag-release.

See ``synarius-studio/docs/developer/connector_rendering.rst`` for context.
"""

from __future__ import annotations

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
# Pin label layout for multi-pin elementary lib blocks (FMU / same family).
# Must match synarius-studio ``dataflow_items``: _FMU_PIN_LABEL_EDGE_INSET, _FMU_PIN_LABEL_CENTER_GAP,
# and ``FmuBlockItem.__pin_label_font`` pixel size (``max(10, int(MODULE * 1.15))``).
_FMU_PIN_LABEL_EDGE_INSET = _MODULE * 0.32
_FMU_PIN_LABEL_CENTER_GAP = _MODULE * 1.2
_FMU_PIN_LABEL_FONT_PS = max(10, int(_MODULE * 1.15))
# Lookup block (Kennlinie / Kennfeld): fixed-size square; must match studio ``LOOKUP_BLOCK_SIZE``.
_LOOKUP_BLOCK_SIZE = 6.0 * _MODULE


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
