"""Orthogonal connector geometry: alternating x/y bend coordinates (diagram space)."""

from __future__ import annotations

_EPS = 1e-6
_EPS_POLY = 1e-2
_COLLINEAR_DY = 10.0
_DEFAULT_DETOUR = 24.0


def bends_relative_to_absolute(sx: float, sy: float, relative: list[float]) -> list[float]:
    """
    Turn bend coordinates stored **relative to the source pin** (sx, sy) into absolute diagram values.

    Even indices are x-offsets from ``sx``, odd indices y-offsets from ``sy`` (same alternation as
    :func:`orthogonal_polyline`).
    """
    out: list[float] = []
    for i, v in enumerate(relative):
        fv = float(v)
        out.append(fv + sx if i % 2 == 0 else fv + sy)
    return out


def bends_absolute_to_relative(sx: float, sy: float, absolute: list[float]) -> list[float]:
    """Inverse of :func:`bends_relative_to_absolute` for persisting bends while the source block moves."""
    out: list[float] = []
    for i, v in enumerate(absolute):
        fv = float(v)
        out.append(fv - sx if i % 2 == 0 else fv - sy)
    return out


def auto_orthogonal_bends(sx: float, sy: float, tx: float, ty: float) -> list[float]:
    """
    Default H–V–H (pins horizontal): interior encoded as [x_mid, y_at_vertical_end].
    Empty list means a single straight segment is enough (or degenerate).
    """
    dx = tx - sx
    dy = ty - sy
    if abs(dx) < 1.0 or abs(dy) < 1.0:
        return []
    if abs(dy) <= _COLLINEAR_DY:
        return []

    x_min, x_max = (sx, tx) if sx <= tx else (tx, sx)
    span_x = x_max - x_min
    span_y = abs(dy)
    r = min(14.0, span_x * 0.32, span_y * 0.32, max(0.5, span_y * 0.5 - 1.0))
    r = max(0.5, r)
    eps = 2.0
    while r > 0.55:
        lo_b = x_min + r + eps
        hi_b = x_max - r - eps
        if lo_b <= hi_b:
            break
        r = max(0.5, r * 0.82)
    x_mid = (sx + tx) * 0.5
    lo_b = x_min + r + eps
    hi_b = x_max - r - eps
    if lo_b <= hi_b:
        x_mid = max(lo_b, min(x_mid, hi_b))
    return [x_mid, ty]


def orthogonal_drag_segments(
    sx: float, sy: float, tx: float, ty: float, bends: list[float]
) -> list[tuple[float, float, float, float, int, str]]:
    """
    Draggable legs on the **resolved** polyline (after completion / detour).

    Each entry is ``(x1, y1, x2, y2, bend_index, axis)`` with ``axis`` ``"x"`` or ``"y"``:
    moving the mouse along that axis updates ``bends[bend_index]``.
    Skips the first leg (source pin stub); includes the final approach when it matches the bend.
    """
    if not bends:
        return []
    pts = polyline_for_endpoints(sx, sy, tx, ty, bends)
    bi = 0
    out: list[tuple[float, float, float, float, int, str]] = []
    for i in range(1, len(pts) - 1):
        if bi >= len(bends):
            break
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        vert = abs(ax - bx) < 1e-3
        need_vert = bi % 2 == 0
        if vert != need_vert:
            continue
        out.append((ax, ay, bx, by, bi, "x" if need_vert else "y"))
        bi += 1
    return out


def _dedupe_consecutive_points(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not pts:
        return pts
    out: list[tuple[float, float]] = [pts[0]]
    for x, y in pts[1:]:
        lx, ly = out[-1]
        if abs(x - lx) < _EPS and abs(y - ly) < _EPS:
            continue
        out.append((x, y))
    return out


def _axis_redundant_middle(
    prev: tuple[float, float],
    mid: tuple[float, float],
    nxt: tuple[float, float],
    eps: float = _EPS_POLY,
) -> bool:
    """True if *mid* lies on the axis-aligned segment *prev*–*nxt* (strictly between, or at endpoints)."""
    x0, y0 = prev
    x1, y1 = mid
    x2, y2 = nxt
    if abs(y0 - y1) < eps and abs(y1 - y2) < eps:
        lo, hi = (x0, x2) if x0 <= x2 else (x2, x0)
        return lo - eps <= x1 <= hi + eps
    if abs(x0 - x1) < eps and abs(x1 - x2) < eps:
        lo, hi = (y0, y2) if y0 <= y2 else (y2, y0)
        return lo - eps <= y1 <= hi + eps
    return False


def simplify_axis_aligned_polyline(
    pts: list[tuple[float, float]], eps: float = _EPS_POLY
) -> list[tuple[float, float]]:
    """Drop interior vertices that lie on the same horizontal or vertical run as neighbours."""
    if len(pts) < 3:
        return list(pts)
    out: list[tuple[float, float]] = [pts[0]]
    for i in range(1, len(pts) - 1):
        if _axis_redundant_middle(out[-1], pts[i], pts[i + 1], eps):
            continue
        out.append(pts[i])
    out.append(pts[-1])
    return out


def remove_axis_aligned_spikes(
    pts: list[tuple[float, float]], eps: float = _EPS_POLY
) -> list[tuple[float, float]]:
    """
    Remove interior vertices that jog off the axis-aligned segment between neighbours.

    Bad or over-long ``orthogonal_bends`` lists can yield e.g. three points with the same
    *x* where the middle *y* lies outside the span of the outer two — a visible vertical
    "tail" in the diagram (see debug logs: same column, non-monotonic *y*).
    """
    if len(pts) < 3:
        return list(pts)
    out = list(pts)
    changed = True
    while changed and len(out) >= 3:
        changed = False
        i = 1
        while i < len(out) - 1:
            px, py = out[i - 1]
            cx, cy = out[i]
            nx, ny = out[i + 1]
            if abs(px - cx) < eps and abs(cx - nx) < eps:
                lo, hi = (py, ny) if py <= ny else (ny, py)
                if cy < lo - eps or cy > hi + eps:
                    del out[i]
                    changed = True
                    continue
            elif abs(py - cy) < eps and abs(cy - ny) < eps:
                lo, hi = (px, nx) if px <= nx else (nx, px)
                if cx < lo - eps or cx > hi + eps:
                    del out[i]
                    changed = True
                    continue
            i += 1
    return out


def orthogonal_polyline(
    sx: float, sy: float, tx: float, ty: float, bends: list[float]
) -> list[tuple[float, float]]:
    """
    Vertices from source to target (inclusive).

    ``bends`` alternates x, y, x, y, …: first move horizontal to (bends[0], sy),
    then vertical to (bends[0], bends[1]), then horizontal to (bends[2], bends[1]), …
    Finally route to (tx, ty) with a horizontal last segment into the target pin.
    """
    if not bends:
        return [(sx, sy), (tx, ty)]

    pts: list[tuple[float, float]] = [(float(sx), float(sy))]
    px, py = float(sx), float(sy)
    for i, v in enumerate(bends):
        fv = float(v)
        if i % 2 == 0:
            px, py = fv, py
        else:
            px, py = px, fv
        pts.append((px, py))

    px, py = pts[-1]
    tx, ty = float(tx), float(ty)
    # Pin / bend vs target: sub-pixel drift on x or y — snap to target without detour.
    if abs(py - ty) <= _EPS_POLY and abs(px - tx) <= 1.0:
        pts[-1] = (tx, ty)
        return _dedupe_consecutive_points(pts)
    # Same column as target pin: detour is only needed when the knee is clearly off the
    # target row. Sub-pixel / sub-grid y drift (or small pin vs knee mismatch) must not
    # add the sideways detour — that shows up as an extra vertical "tail" in the editor.
    if abs(px - tx) < _EPS and abs(py - ty) <= _COLLINEAR_DY:
        pts[-1] = (tx, ty)
        return _dedupe_consecutive_points(pts)
    # Last segment into target is horizontal; snap small Δy to target row (see _COLLINEAR_DY).
    if abs(py - ty) <= _COLLINEAR_DY:
        pts[-1] = (px, ty)
        pts.append((tx, ty))
        return _dedupe_consecutive_points(pts)
    if abs(px - tx) < _EPS:
        # Same x as target before final approach: step sideways then H into pin (no zero-length stub).
        away = max(_DEFAULT_DETOUR, abs(ty - py) * 0.08 + 12.0)
        if abs(sx - tx) > _EPS:
            sign = 1.0 if sx < tx else -1.0
        else:
            sign = 1.0
        ox = px + sign * away
        pts.append((ox, py))
        pts.append((ox, ty))
        pts.append((tx, ty))
    else:
        pts.append((px, ty))
        pts.append((tx, ty))
    return _dedupe_consecutive_points(pts)


def polyline_for_endpoints(
    sx: float, sy: float, tx: float, ty: float, bends: list[float]
) -> list[tuple[float, float]]:
    """Use stored bends, or default auto routing when ``bends`` is empty."""
    if bends:
        raw = orthogonal_polyline(sx, sy, tx, ty, bends)
        sim = simplify_axis_aligned_polyline(raw)
        return remove_axis_aligned_spikes(sim)
    b = auto_orthogonal_bends(sx, sy, tx, ty)
    if b:
        raw = orthogonal_polyline(sx, sy, tx, ty, b)
        sim = simplify_axis_aligned_polyline(raw)
        return remove_axis_aligned_spikes(sim)
    return [(sx, sy), (tx, ty)]


def encode_bends_from_polyline(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    poly: list[tuple[float, float]],
) -> list[float]:
    """
    Recover alternating bend vector from a full orthogonal polyline S→…→T.
    Interior vertices only; poly[0] must be (sx,sy) and poly[-1] (tx,ty).
    """
    if len(poly) < 2:
        return []
    if (
        abs(poly[0][0] - sx) > _EPS_POLY
        or abs(poly[0][1] - sy) > _EPS_POLY
        or abs(poly[-1][0] - tx) > _EPS_POLY
        or abs(poly[-1][1] - ty) > _EPS_POLY
    ):
        raise ValueError("poly endpoints must match source and target.")
    interior = poly[1:-1]
    if not interior:
        return []
    out: list[float] = []
    for i, (x, y) in enumerate(interior):
        out.append(float(x) if i % 2 == 0 else float(y))
    return out


def canonicalize_absolute_bends(
    sx: float, sy: float, tx: float, ty: float, bends_abs: list[float]
) -> list[float]:
    """
    Rebuild a minimal alternating bend list for the same endpoints.

    Expanded polylines (e.g. runtime detours from :func:`orthogonal_polyline`) sometimes get
    persisted as extra bend numbers; collinear vertices are stripped so routing matches the
    intended H–V–H (or longer) knee set without spurious support points.
    """
    b = [float(x) for x in bends_abs]
    if not b:
        return []
    for _ in range(8):
        poly = orthogonal_polyline(sx, sy, tx, ty, b)
        sim = simplify_axis_aligned_polyline(poly)
        sim = remove_axis_aligned_spikes(sim)
        if len(sim) < 2:
            return []
        try:
            nb = encode_bends_from_polyline(sx, sy, tx, ty, sim)
        except ValueError:
            return b
        if not nb:
            return []
        if len(nb) == len(b) and all(abs(nb[i] - b[i]) < 1e-5 for i in range(len(b))):
            return nb
        b = nb
    return b
