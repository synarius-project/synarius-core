"""Short text summaries of :class:`numpy.ndarray` values (CLI / Cal-Param print)."""

from __future__ import annotations

import numpy as np


def format_ndarray_summary(arr: np.ndarray) -> str:
    """Compact description of *arr* for human-readable output (same rules as legacy controller code)."""
    if arr.size == 0:
        return "(leer)"
    flat = np.asarray(arr, dtype=np.float64).ravel()
    if flat.size == 1:
        v = float(flat[0])
        return f"{v:g}" if np.isfinite(v) else str(v)
    finite = flat[np.isfinite(flat)]
    if finite.size == 0:
        return f"shape={tuple(arr.shape)} (keine endlichen Werte)"
    return (
        f"shape={tuple(arr.shape)} min={float(np.min(finite)):g} max={float(np.max(finite)):g} "
        f"mean={float(np.mean(finite)):g}"
    )
