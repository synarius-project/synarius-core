"""Build a time-indexed DataFrame from channel buffers and write CSV / Parquet / MDF."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def _dataframe_from_series_buffers(
    series_buffers: dict[str, tuple[Iterable[float], Iterable[float]]],
) -> pd.DataFrame | None:
    """Return a DataFrame indexed by time, or ``None`` if nothing valid to export."""
    if not series_buffers:
        return None
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
        return None
    return pd.DataFrame(data_cols, index=pd.Index(t, name="time"))


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=True)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    df.to_parquet(path)


def _write_mdf_or_fallback_csv(df: pd.DataFrame, path: Path, channel_order: list[str]) -> None:
    try:
        from asammdf import MDF, Signal as MDFSignal  # type: ignore[import]
    except Exception:
        _write_csv(df, path)
        return

    mdf = MDF()
    try:
        t_arr = df.index.to_numpy(dtype=np.float64, copy=False)
        for name in channel_order:
            if name not in df.columns:
                continue
            vals = df[name].to_numpy(dtype=np.float64, copy=False)
            sig = MDFSignal(samples=vals, timestamps=t_arr, name=name)
            mdf.append(sig)
        mdf.save(str(path))
    finally:
        try:
            mdf.close()
        except Exception:
            pass


def _export_dataframe(df: pd.DataFrame, path: Path, fmt: str, channel_order: list[str]) -> None:
    suf = path.suffix.lower()
    if fmt == "csv" or suf == ".csv":
        _write_csv(df, path)
        return
    if fmt == "parquet" or suf in (".parquet", ".pq"):
        _write_parquet(df, path)
        return
    _write_mdf_or_fallback_csv(df, path, channel_order)


def export_recording_buffers(
    series_buffers: dict[str, tuple[Iterable[float], Iterable[float]]],
    path: Path | str,
    fmt: str = "mdf",
) -> None:
    """Export per-channel time-series buffers as CSV/Parquet/MDF.

    ``series_buffers`` maps channel name → (t_iterable, y_iterable). All channels
    are expected to share the same time base (same length and sample times).
    """
    df = _dataframe_from_series_buffers(series_buffers)
    if df is None:
        return
    p = Path(path)
    _export_dataframe(df, p, fmt, sorted(series_buffers.keys()))
