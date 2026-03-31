"""Recording and export functionality for synarius-core."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def export_recording_buffers(
    series_buffers: dict[str, tuple[Iterable[float], Iterable[float]]],
    path: Path | str,
    fmt: str = "mdf",
) -> None:
    """Export per-channel time-series buffers as CSV/Parquet/MDF.

    ``series_buffers`` maps channel name → (t_iterable, y_iterable). All channels
    are expected to share the same time base (same length and sample times).
    """
    p = Path(path)
    if not series_buffers:
        return

    names = sorted(series_buffers.keys())
    any_buf = next(iter(series_buffers.values()))
    t = np.asarray(list(any_buf[0]), dtype=np.float64)
    data_cols: dict[str, np.ndarray] = {}
    for name in names:
        xs, ys = series_buffers[name]
        xs_arr = np.asarray(list(xs), dtype=np.float64)
        ys_arr = np.asarray(list(ys), dtype=np.float64)
        if xs_arr.shape != t.shape:
            continue
        data_cols[name] = ys_arr
    if not data_cols:
        return
    df = pd.DataFrame(data_cols, index=pd.Index(t, name="time"))

    suf = p.suffix.lower()
    if fmt == "csv" or suf == ".csv":
        df.to_csv(p, index=True)
        return
    if fmt == "parquet" or suf in (".parquet", ".pq"):
        df.to_parquet(p)
        return

    # MDF: use asammdf if available; otherwise fall back to CSV.
    try:
        from asammdf import MDF, Signal as MDFSignal  # type: ignore[import]
    except Exception:
        df.to_csv(p, index=True)
        return

    mdf = MDF()
    try:
        t_arr = df.index.to_numpy(dtype=np.float64, copy=False)
        for name in names:
            if name not in df.columns:
                continue
            vals = df[name].to_numpy(dtype=np.float64, copy=False)
            sig = MDFSignal(samples=vals, timestamps=t_arr, name=name)
            mdf.append(sig)
        mdf.save(str(p))
    finally:
        try:
            mdf.close()
        except Exception:
            pass
