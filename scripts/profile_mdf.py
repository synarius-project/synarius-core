#!/usr/bin/env python3
"""
MDF/MF4: Testdateien erzeugen und Einlesen profilieren (asammdf vs. pandas DataFrame).

Größen: 1 MB, 10 MB, 100 MB, 1 GB.

Edge-Cases (je Zielgröße eine Datei):
  • minimal — 3 Signale, ein gemeinsames Zeitraster (eine Datengruppe)
  • multi   — 180 Kanäle, 3 verschiedene Zeitraster (drei Datengruppen à 60 Kanäle)

Modi:
  --suite              Alle 8 Dateien erzeugen und nacheinander profilieren (Standard)
  --generate-only      Nur erzeugen
  --input …            Nur profilieren (eigene Dateien)

Pakete:
    pip install asammdf numpy pandas psutil
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import psutil
from asammdf import MDF, Signal


# ----------------------------
# Testdaten-Generierung
# ----------------------------

TARGET_SIZES: dict[str, int] = {
    "1MB": 1 * 1024 * 1024,
    "10MB": 10 * 1024 * 1024,
    "100MB": 100 * 1024 * 1024,
    "1GB": 1 * 1024 * 1024 * 1024,
}


@dataclass(frozen=True)
class ScenarioSpec:
    """Beschreibt die Kantenfall-Struktur der MDF-Datei."""

    key: str
    title: str
    channels: int
    rasters: int


SCENARIOS: dict[str, ScenarioSpec] = {
    "minimal": ScenarioSpec(
        key="minimal",
        title="3 Signale, 1 Zeitraster",
        channels=3,
        rasters=1,
    ),
    "multi": ScenarioSpec(
        key="multi",
        title="180 Kanäle, 3 Zeitraster",
        channels=180,
        rasters=3,
    ),
}


def estimate_samples_for_target(
    target_bytes: int,
    channel_count: int,
    dtype: np.dtype = np.dtype(np.float64),
    timestamp_dtype: np.dtype = np.dtype(np.float64),
    safety_factor: float = 0.96,
) -> int:
    bytes_per_timestamp = np.dtype(timestamp_dtype).itemsize
    bytes_per_sample_values = channel_count * np.dtype(dtype).itemsize
    approx_bytes_per_row = bytes_per_timestamp + bytes_per_sample_values
    estimated = int((target_bytes * safety_factor) / approx_bytes_per_row)
    return max(estimated, 1)


def estimate_samples_equal_groups(
    target_bytes: int,
    channels_per_group: int,
    num_groups: int,
    dtype: np.dtype = np.dtype(np.float64),
    timestamp_dtype: np.dtype = np.dtype(np.float64),
    safety_factor: float = 0.96,
) -> int:
    """Gleiche Sample-Anzahl pro Gruppe, Zielgröße auf alle Gruppen verteilt."""
    bytes_per_row = np.dtype(timestamp_dtype).itemsize + channels_per_group * np.dtype(dtype).itemsize
    budget = target_bytes * safety_factor / num_groups
    n = int(budget / bytes_per_row)
    return max(n, 1)


def build_signals_single_raster(sample_count: int, channel_count: int) -> list[Signal]:
    timestamps = np.arange(sample_count, dtype=np.float64) * 0.001
    signals: list[Signal] = []
    base = np.arange(sample_count, dtype=np.float64)

    for i in range(channel_count):
        if i == 0:
            samples = np.sin(base / 1000.0)
            unit, name = "V", "sinus"
        elif i == 1:
            samples = np.cos(base / 1500.0)
            unit, name = "V", "cosinus"
        else:
            samples = (base % 1000) / 1000.0
            unit, name = "-", "saw"
        if i >= 3:
            rng = np.random.default_rng(seed=42 + i)
            samples = rng.standard_normal(sample_count).astype(np.float64)
            unit, name = "-", f"noise_{i}"

        signals.append(
            Signal(samples=samples, timestamps=timestamps, name=name, unit=unit),
        )

    return signals


def build_signals_multi_raster(
    n_per_group: int,
    channels_per_group: int,
    dts: tuple[float, float, float],
) -> list[list[Signal]]:
    """Drei getrennte Gruppen mit je channels_per_group Kanälen und eigenem Raster."""
    groups: list[list[Signal]] = []
    for g, dt in enumerate(dts):
        timestamps = np.arange(n_per_group, dtype=np.float64) * dt
        base = np.arange(n_per_group, dtype=np.float64)
        sigs: list[Signal] = []
        for ch in range(channels_per_group):
            phase = (g * 17 + ch * 13) % 1000
            samples = np.sin(base / (200.0 + phase)) + 0.1 * (ch % 7)
            name = f"g{g}_ch{ch:03d}"
            sigs.append(
                Signal(samples=samples.astype(np.float64), timestamps=timestamps, name=name, unit="V"),
            )
        groups.append(sigs)
    return groups


def write_mdf_minimal(output_path: Path, target_bytes: int, version: str = "4.10") -> None:
    spec = SCENARIOS["minimal"]
    sample_count = estimate_samples_for_target(
        target_bytes,
        channel_count=spec.channels,
    )
    print(
        f"Erzeuge {output_path.name}: Ziel≈{target_bytes / (1024**2):.2f} MB, "
        f"Szenario={spec.title}, Samples={sample_count:,}, Kanäle={spec.channels}",
    )
    signals = build_signals_single_raster(sample_count, spec.channels)
    mdf = MDF(version=version)
    mdf.append(signals)
    mdf.save(str(output_path), overwrite=True)
    mdf.close()
    _print_wrote(output_path, target_bytes)


def write_mdf_multi(output_path: Path, target_bytes: int, version: str = "4.10") -> None:
    spec = SCENARIOS["multi"]
    channels_per_group = spec.channels // spec.rasters
    n = estimate_samples_equal_groups(
        target_bytes,
        channels_per_group=channels_per_group,
        num_groups=spec.rasters,
    )
    # Drei deutlich verschiedene Raster (z. B. 100 µs, 1 ms, 10 ms)
    dts = (1e-4, 1e-3, 1e-2)
    print(
        f"Erzeuge {output_path.name}: Ziel≈{target_bytes / (1024**2):.2f} MB, "
        f"Szenario={spec.title}, Samples/Gruppe={n:,}, "
        f"Kanäle/Gruppe={channels_per_group}, Raster s={dts}",
    )
    group_signal_lists = build_signals_multi_raster(n, channels_per_group, dts)
    mdf = MDF(version=version)
    for sigs in group_signal_lists:
        mdf.append(sigs)
    mdf.save(str(output_path), overwrite=True)
    mdf.close()
    _print_wrote(output_path, target_bytes)


def _print_wrote(output_path: Path, target_bytes: int) -> None:
    actual_size = output_path.stat().st_size
    diff_pct = (actual_size - target_bytes) / target_bytes * 100.0
    print(
        f"  -> geschrieben: {actual_size:,} Byte "
        f"({actual_size / (1024**2):.2f} MB, Abweichung Ziel {diff_pct:+.2f}%)",
    )


def generate_suite_files(out_dir: Path) -> list[tuple[Path, str, str]]:
    """
    Erzeugt alle Kombinationen aus TARGET_SIZES × SCENARIOS.

    Rückgabe: Liste von (Pfad, size_label, scenario_key) in stabil sortierter Reihenfolge.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[tuple[Path, str, str]] = []
    for size_label, size_bytes in TARGET_SIZES.items():
        for scenario_key in ("minimal", "multi"):
            name = f"test_{size_label}_{scenario_key}.mf4"
            path = out_dir / name
            if scenario_key == "minimal":
                write_mdf_minimal(path, size_bytes)
            else:
                write_mdf_multi(path, size_bytes)
            created.append((path, size_label, scenario_key))
    return created


# ----------------------------
# Mess-Helfer (Lesen)
# ----------------------------

@dataclass
class BenchResult:
    name: str
    seconds: float
    peak_rss_mb: float
    output_bytes: int | None = None
    extra: dict[str, Any] | None = None


class PeakMemoryMonitor:
    def __init__(self, interval_s: float = 0.02) -> None:
        self.interval_s = interval_s
        self.process = psutil.Process(os.getpid())
        self._peak = self.process.memory_info().rss
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        def _run() -> None:
            while not self._stop.is_set():
                try:
                    rss = self.process.memory_info().rss
                    if rss > self._peak:
                        self._peak = rss
                except psutil.Error:
                    pass
                time.sleep(self.interval_s)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> float:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return self._peak / (1024 * 1024)


def bench(name: str, func: Callable[[], Any]) -> tuple[BenchResult, Any]:
    gc.collect()
    monitor = PeakMemoryMonitor()
    monitor.start()
    t0 = time.perf_counter()
    value = func()
    dt = time.perf_counter() - t0
    peak_mb = monitor.stop()
    return BenchResult(
        name=name,
        seconds=dt,
        peak_rss_mb=peak_mb,
        output_bytes=None,
    ), value


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for unit in units:
        if x < 1024 or unit == units[-1]:
            return f"{x:.2f} {unit}"
        x /= 1024
    return f"{n} B"


def open_mdf(path: Path) -> MDF:
    return MDF(str(path))


def count_channels_and_groups(mdf: MDF) -> dict[str, Any]:
    group_count = len(mdf.groups)
    channel_count = 0
    for group in mdf.groups:
        channels = getattr(group, "channels", [])
        channel_count += len(channels)
    return {"groups": group_count, "channels": channel_count}


def dataframe_from_mdf(
    mdf_path: Path,
    reduce_memory_usage: bool = False,
    raster: float | None = None,
    bench_name: str | None = None,
) -> tuple[BenchResult, pd.DataFrame]:
    label = bench_name or f"to_dataframe[{mdf_path.name}]"

    def _to_df() -> pd.DataFrame:
        mdf = MDF(str(mdf_path))
        try:
            kwargs: dict[str, Any] = {"reduce_memory_usage": reduce_memory_usage}
            if raster is not None:
                kwargs["raster"] = raster
            return mdf.to_dataframe(**kwargs)
        finally:
            try:
                mdf.close()
            except Exception:
                pass

    result, df = bench(label, _to_df)
    result.extra = {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "memory_usage_mb": float(df.memory_usage(deep=True).sum() / (1024 * 1024)),
    }
    return result, df


@dataclass
class FileReadProfile:
    path: str
    file_size_bytes: int
    mdf: BenchResult
    dataframe: BenchResult
    size_label: str = ""
    scenario_key: str = ""
    scenario_title: str = ""


def profile_one_file(
    path: Path,
    *,
    reduce_memory_usage: bool,
    raster: float | None,
    step: Callable[[str], None],
    size_label: str = "",
    scenario_key: str = "",
    scenario_title: str = "",
) -> FileReadProfile:
    file_size = path.stat().st_size
    name = path.name

    step(f"MDF laden (asammdf) — {name}")
    open_result, mdf = bench(f"open_mdf[{name}]", lambda: open_mdf(path))
    try:
        meta = count_channels_and_groups(mdf)
        open_result.extra = meta
    finally:
        try:
            mdf.close()
        except Exception:
            pass

    step(f"to_dataframe (pandas) — {name}")
    df_result, _df = dataframe_from_mdf(
        path,
        reduce_memory_usage=reduce_memory_usage,
        raster=raster,
        bench_name=f"to_dataframe[{name}]",
    )

    return FileReadProfile(
        path=str(path),
        file_size_bytes=file_size,
        mdf=open_result,
        dataframe=df_result,
        size_label=size_label,
        scenario_key=scenario_key,
        scenario_title=scenario_title,
    )


def print_results_table(profiles: list[FileReadProfile]) -> None:
    if not profiles:
        print("(keine Dateien profiliert)")
        return

    title = "Einlesen: asammdf (MDF) vs. pandas DataFrame — Übersicht"
    sep = "=" * len(title)
    print(f"\n{sep}\n{title}\n{sep}")

    col_szen = 40
    col_file = 28
    col_sz = 11
    col_t = 9
    col_rss = 9
    col_dfmem = 11
    col_ratio = 7
    col_dpeak = 8
    col_g = 4
    col_k = 5

    header = (
        f"{'Szenario':<{col_szen}} "
        f"{'Datei':<{col_file}} "
        f"{'Größe':>{col_sz}} "
        f"{'MDF s':>{col_t}} "
        f"{'MDF MB':>{col_rss}} "
        f"{'DF s':>{col_t}} "
        f"{'DF MB':>{col_rss}} "
        f"{'×':>{col_ratio}} "
        f"{'ΔPk':>{col_dpeak}} "
        f"{'DF inh.':>{col_dfmem}} "
        f"{'G':>{col_g}} "
        f"{'K':>{col_k}}"
    )
    sub = (
        f"{'':<{col_szen}} "
        f"{'':<{col_file}} "
        f"{'':>{col_sz}} "
        f"{'asam':>{col_t}} "
        f"{'RSS':>{col_rss}} "
        f"{'pandas':>{col_t}} "
        f"{'RSS':>{col_rss}} "
        f"{'Zeit':>{col_ratio}} "
        f"{'MB':>{col_dpeak}} "
        f"{'deep':>{col_dfmem}} "
        f"{'':>{col_g}} "
        f"{'':>{col_k}}"
    )
    line = "-" * len(header)

    print(header)
    print(sub)
    print(line)

    for p in profiles:
        m = p.mdf.extra or {}
        d = p.dataframe.extra or {}
        g = m.get("groups", "")
        k = m.get("channels", "")
        df_deep = d.get("memory_usage_mb", "")
        df_deep_s = f"{df_deep:.1f}" if isinstance(df_deep, (int, float)) else "-"

        if p.mdf.seconds > 0:
            t_ratio = f"{p.dataframe.seconds / p.mdf.seconds:.2f}×"
        else:
            t_ratio = "—"
        d_peak = p.dataframe.peak_rss_mb - p.mdf.peak_rss_mb
        d_peak_s = f"{d_peak:+.1f}"

        scen = p.scenario_title or p.scenario_key or "—"
        if p.size_label:
            scen = f"{p.size_label} · {scen}"

        print(
            f"{scen:<{col_szen}} "
            f"{Path(p.path).name:<{col_file}} "
            f"{fmt_bytes(p.file_size_bytes):>{col_sz}} "
            f"{p.mdf.seconds:>{col_t}.3f} "
            f"{p.mdf.peak_rss_mb:>{col_rss}.1f} "
            f"{p.dataframe.seconds:>{col_t}.3f} "
            f"{p.dataframe.peak_rss_mb:>{col_rss}.1f} "
            f"{t_ratio:>{col_ratio}} "
            f"{d_peak_s:>{col_dpeak}} "
            f"{df_deep_s:>{col_dfmem}} "
            f"{g!s:>{col_g}} "
            f"{k!s:>{col_k}}"
        )

    print(line)
    print(
        "× = DF-Zeit / MDF-Zeit; ΔPk = Differenz der Peak-RSS-Werte der beiden Phasen; "
        "DF inh. = pandas memory_usage(deep=True)."
    )


# ----------------------------
# CLI
# ----------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MDF-Testdaten erzeugen und/oder Einlesen profilieren (asammdf vs. DataFrame).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--suite",
        action="store_true",
        help="8 Dateien erzeugen (4 Größen × 2 Szenarien) und alle profilieren",
    )
    g.add_argument(
        "--generate-only",
        action="store_true",
        help="Nur Testdateien erzeugen, kein Profiling",
    )
    g.add_argument(
        "--input",
        nargs="+",
        metavar="FILE",
        help="Nur diese MDF/MF4-Dateien profilieren (ohne Suite)",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("mdf_testdaten"),
        help="Verzeichnis für generierte MF4-Dateien",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Optional: JSON-Ergebnisse (benchmark_results.json)",
    )
    parser.add_argument(
        "--raster",
        type=float,
        default=None,
        help="Optionales Raster (s) für to_dataframe()",
    )
    parser.add_argument(
        "--reduce-memory-usage",
        action="store_true",
        help="reduce_memory_usage=True bei to_dataframe()",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
    )
    return parser.parse_args()


def _run_profile_batch(
    paths_meta: list[tuple[Path, str, str]],
    *,
    reduce_memory_usage: bool,
    raster: float | None,
    quiet: bool,
) -> list[FileReadProfile]:
    step_n = 0
    total = len(paths_meta) * 2

    def step(msg: str) -> None:
        nonlocal step_n
        if quiet:
            return
        step_n += 1
        print(f"[{step_n}/{total}] {msg}", flush=True)

    profiles: list[FileReadProfile] = []
    for i, (path, size_label, scenario_key) in enumerate(paths_meta, start=1):
        if not quiet:
            title = SCENARIOS[scenario_key].title if scenario_key in SCENARIOS else scenario_key
            print(f"\n--- {i}/{len(paths_meta)}: {path.name} ({title}) ---", flush=True)
        prof = profile_one_file(
            path,
            reduce_memory_usage=reduce_memory_usage,
            raster=raster,
            step=step,
            size_label=size_label,
            scenario_key=scenario_key,
            scenario_title=SCENARIOS[scenario_key].title if scenario_key in SCENARIOS else "",
        )
        profiles.append(prof)
    return profiles


def main() -> None:
    args = parse_args()

    data_dir = args.data_dir.expanduser().resolve()

    if args.input is None and not args.suite and not args.generate_only:
        # Standard: volle Suite
        args.suite = True

    if args.suite or args.generate_only:
        print(f"Ausgabeverzeichnis Testdaten: {data_dir}\n", flush=True)
        generate_suite_files(data_dir)
        if args.generate_only:
            print(f"\nFertig (nur Generierung). Dateien unter: {data_dir}")
            return

    paths_meta: list[tuple[Path, str, str]]
    if args.input is not None:
        paths_meta = []
        for p in args.input:
            path = Path(p).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"Eingabedatei nicht gefunden: {path}")
            paths_meta.append((path, "", ""))
    elif args.suite:
        paths_meta = []
        for size_label in TARGET_SIZES:
            for sk in ("minimal", "multi"):
                p = data_dir / f"test_{size_label}_{sk}.mf4"
                if not p.exists():
                    raise FileNotFoundError(
                        f"Datei fehlt: {p}. Bitte zuerst mit --generate-only erzeugen.",
                    )
                paths_meta.append((p, size_label, sk))
    else:
        raise RuntimeError("Intern: weder --input noch --suite gesetzt.")

    out_dir = args.out_dir.expanduser().resolve() if args.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    profiles = _run_profile_batch(
        paths_meta,
        reduce_memory_usage=args.reduce_memory_usage,
        raster=args.raster,
        quiet=args.quiet,
    )

    print_results_table(profiles)

    if out_dir is not None:
        payload = []
        for p in profiles:
            payload.append(
                {
                    "path": p.path,
                    "size_label": p.size_label,
                    "scenario_key": p.scenario_key,
                    "scenario_title": p.scenario_title,
                    "file_size_bytes": p.file_size_bytes,
                    "mdf_open": asdict(p.mdf),
                    "to_dataframe": asdict(p.dataframe),
                }
            )
        json_path = out_dir / "benchmark_results.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\nJSON: {json_path}")


if __name__ == "__main__":
    main()
