"""Reference implementations of parameter lookup primitives.

These functions are the **normative Python reference** for the lookup semantics
defined in ``compiler_lowering_rules.rst``.  Generated ``run_equations`` code
calls them directly by name; they must not be renamed.

Arithmetic follows IEEE-754 float64.  Floating-point rounding deviations from
ideal real-arithmetic results do not constitute a semantic error.
"""

from __future__ import annotations

import numpy as np


def syn_curve_lookup_linear_clamp(axis: np.ndarray, values: np.ndarray, x: float) -> float:
    """1-D linear interpolation with clamp extrapolation.

    Parameters
    ----------
    axis:
        Strictly monotone increasing breakpoint axis, shape ``(n,)``, ``n >= 2``.
    values:
        Function values at each breakpoint, shape ``(n,)``.
    x:
        Query point.

    Returns
    -------
    float
        Interpolated/clamped value.
    """
    n = len(axis)
    # Clamp extrapolation
    if x <= axis[0]:
        return float(values[0])
    if x >= axis[n - 1]:
        return float(values[n - 1])
    # Binary search for the left bracket index i such that axis[i] <= x < axis[i+1]
    lo, hi = 0, n - 2
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if axis[mid] <= x:
            lo = mid
        else:
            hi = mid - 1
    i = lo
    t = (x - axis[i]) / (axis[i + 1] - axis[i])
    return float(values[i] + t * (values[i + 1] - values[i]))


def syn_map_lookup_bilinear_clamp(
    axis0: np.ndarray,
    axis1: np.ndarray,
    values: np.ndarray,
    x: float,
    y: float,
) -> float:
    """2-D bilinear interpolation with clamp extrapolation.

    Parameters
    ----------
    axis0:
        Strictly monotone increasing row axis, shape ``(m,)``, ``m >= 2``.
    axis1:
        Strictly monotone increasing column axis, shape ``(n,)``, ``n >= 2``.
    values:
        Value map, shape ``(m, n)``, row-major (``values[i, j]`` at
        ``(axis0[i], axis1[j])``).
    x:
        Query point along axis0.
    y:
        Query point along axis1.

    Returns
    -------
    float
        Bilinearly interpolated/clamped value.
    """
    m = len(axis0)
    n = len(axis1)

    # Clamp inputs
    x_c = float(np.clip(x, axis0[0], axis0[m - 1]))
    y_c = float(np.clip(y, axis1[0], axis1[n - 1]))

    # Row index: largest i with axis0[i] <= x_c, clamped to [0, m-2]
    lo, hi = 0, m - 2
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if axis0[mid] <= x_c:
            lo = mid
        else:
            hi = mid - 1
    i = lo

    # Column index: largest j with axis1[j] <= y_c, clamped to [0, n-2]
    lo, hi = 0, n - 2
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if axis1[mid] <= y_c:
            lo = mid
        else:
            hi = mid - 1
    j = lo

    tx = (x_c - axis0[i]) / (axis0[i + 1] - axis0[i])
    ty = (y_c - axis1[j]) / (axis1[j + 1] - axis1[j])

    return float(
        values[i, j] * (1.0 - tx) * (1.0 - ty)
        + values[i + 1, j] * tx * (1.0 - ty)
        + values[i, j + 1] * (1.0 - tx) * ty
        + values[i + 1, j + 1] * tx * ty
    )
