#!/usr/bin/env python3
"""Regenerate FMF library SVGs to match Synarius Studio BasicOperator glyph geometry.

Mirrors ``_paint_basic_operator_glyph`` (``synarius_studio/diagram/dataflow_items.py``):
fill #2468dc, stroke #16161c. Run: ``python scripts/generate_operator_library_svgs.py``
"""
from __future__ import annotations

from pathlib import Path

FILL = "#2468dc"
STROKE = "#16161c"

OPS = [
    ("Add", "add", "plus"),
    ("Sub", "sub", "minus"),
    ("Mul", "mul", "mul"),
    ("Div", "div", "div"),
]


def _fmt(n: float) -> str:
    s = f"{n:.4f}"
    s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def plus_path(cx: float, cy: float, arm: float, bar: float) -> str:
    t = bar * 0.5
    x0, x1 = cx - arm, cx + arm
    y0, y1 = cy - t, cy + t
    xl, xr = cx - t, cx + t
    yu, yd = cy - arm, cy + arm
    return (
        f"M {_fmt(xl)} {_fmt(yu)} L {_fmt(xr)} {_fmt(yu)} L {_fmt(xr)} {_fmt(y0)} "
        f"L {_fmt(x1)} {_fmt(y0)} L {_fmt(x1)} {_fmt(y1)} L {_fmt(xr)} {_fmt(y1)} "
        f"L {_fmt(xr)} {_fmt(yd)} L {_fmt(xl)} {_fmt(yd)} L {_fmt(xl)} {_fmt(y1)} "
        f"L {_fmt(x0)} {_fmt(y1)} L {_fmt(x0)} {_fmt(y0)} L {_fmt(xl)} {_fmt(y0)} L {_fmt(xl)} {_fmt(yu)} Z"
    )


def minus_path(cx: float, cy: float, arm: float, bar: float) -> str:
    t = bar * 0.5
    x0, x1 = cx - arm, cx + arm
    y0, y1 = cy - t, cy + t
    return f"M {_fmt(x0)} {_fmt(y0)} L {_fmt(x1)} {_fmt(y0)} L {_fmt(x1)} {_fmt(y1)} L {_fmt(x0)} {_fmt(y1)} Z"


def mul_lines(cx: float, cy: float, arm: float, bar: float, outline_w: float) -> str:
    """Two diagonals: outer stroke line + inner fill line (avoids path union)."""
    k = 0.72
    x0, y0 = cx - arm * k, cy - arm * k
    x1, y1 = cx + arm * k, cy + arm * k
    ow = outline_w
    w_outer = bar + 2.0 * ow
    # Line 1: \
    # Line 2: /
    s = ""
    for xa, ya, xb, yb in ((x0, y0, x1, y1), (x0, y1, x1, y0)):
        s += (
            f'  <line x1="{_fmt(xa)}" y1="{_fmt(ya)}" x2="{_fmt(xb)}" y2="{_fmt(yb)}" '
            f'stroke="{STROKE}" stroke-width="{_fmt(w_outer)}" stroke-linecap="butt"/>\n'
            f'  <line x1="{_fmt(xa)}" y1="{_fmt(ya)}" x2="{_fmt(xb)}" y2="{_fmt(yb)}" '
            f'stroke="{FILL}" stroke-width="{_fmt(bar)}" stroke-linecap="butt"/>\n'
        )
    return s


def div_content(S: float, outline_w: float) -> str:
    w = h = S
    cx = w * 0.5
    cy = h * 0.5
    arm = min(w, h) * 0.36
    inset = min(w, h) * 0.18
    bar = max(2.2, min(w, h) * 0.09)
    t = bar * 0.5
    left = inset
    right = w - inset
    y0, y1 = cy - t, cy + t
    bar_d = (
        f"M {_fmt(left)} {_fmt(y0)} L {_fmt(right)} {_fmt(y0)} L {_fmt(right)} {_fmt(y1)} "
        f"L {_fmt(left)} {_fmt(y1)} Z"
    )
    dot_r = min(w, h) * 0.068
    gap = min(w, h) * 0.22
    parts = [f'<path fill="{FILL}" stroke="{STROKE}" stroke-width="{_fmt(outline_w)}" '
             f'stroke-linejoin="miter" stroke-linecap="butt" d="{bar_d}"/>']
    for offy in (-gap, gap):
        cx0, cy0 = cx, cy + offy
        d = (
            f"M {_fmt(cx0 - dot_r)} {_fmt(cy0)} "
            f"A {_fmt(dot_r)} {_fmt(dot_r)} 0 1 1 {_fmt(cx0 + dot_r)} {_fmt(cy0)} "
            f"A {_fmt(dot_r)} {_fmt(dot_r)} 0 1 1 {_fmt(cx0 - dot_r)} {_fmt(cy0)} Z"
        )
        parts.append(
            f'<path fill="{FILL}" stroke="{STROKE}" stroke-width="{_fmt(outline_w)}" '
            f'stroke-linejoin="miter" d="{d}"/>'
        )
    return "\n".join(parts)


def single_path_svg(size: int, d: str, outline_w: float) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">\n'
        f'  <path fill="{FILL}" stroke="{STROKE}" stroke-width="{_fmt(outline_w)}" '
        f'stroke-linejoin="miter" stroke-linecap="butt" d="{d}"/>\n'
        "</svg>\n"
    )


def mul_svg(size: int, cx: float, cy: float, arm: float, bar: float, outline_w: float) -> str:
    inner = mul_lines(cx, cy, arm, bar, outline_w)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">\n'
        f"{inner}"
        "</svg>\n"
    )


def params(S: float) -> tuple[float, float, float, float, float]:
    w = h = S
    cx = w * 0.5
    cy = h * 0.5
    arm = min(w, h) * 0.36
    bar = max(2.2, min(w, h) * 0.09)
    outline_w = max(1.2, bar * 0.38)
    return cx, cy, arm, bar, outline_w


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    std = root / "Lib/std/components"
    ex_add = root / "docs/specifications/examples/std/components/Add/resources/icons"

    for folder, stem, kind in OPS:
        for S in (16, 32, 64):
            cx, cy, arm, bar, ow = params(float(S))
            if kind == "plus":
                doc = single_path_svg(S, plus_path(cx, cy, arm, bar), ow)
            elif kind == "minus":
                doc = single_path_svg(S, minus_path(cx, cy, arm, bar), ow)
            elif kind == "mul":
                doc = mul_svg(S, cx, cy, arm, bar, ow)
            else:
                doc = (
                    f'<?xml version="1.0" encoding="UTF-8"?>\n'
                    f'<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" '
                    f'viewBox="0 0 {S} {S}">\n'
                    f"{div_content(float(S), ow)}\n"
                    "</svg>\n"
                )
            out = std / folder / "resources/icons" / f"{stem}_{S}.svg"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(doc, encoding="utf-8")

        if stem == "add":
            ex_add.mkdir(parents=True, exist_ok=True)
            for S in (16, 32, 64):
                cx, cy, arm, bar, ow = params(float(S))
                doc = single_path_svg(S, plus_path(cx, cy, arm, bar), ow)
                (ex_add / f"add_{S}.svg").write_text(doc, encoding="utf-8")

    print("Wrote Lib/std + examples/std Add icons.")


if __name__ == "__main__":
    main()
