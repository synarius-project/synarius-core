"""Regenerate ``dcm2_maximal_10000_kennwerte.dcm`` with varied map/curve sizes and nonlinear data.

Preserves: 2000 blocks each of KENNFELD, KENNLINIE, FESTWERT, FESTWERTEBLOCK,
STUETZSTELLENVERTEILUNG; seed-shuffled interleaving; random seed 20260402.

Run from ``synarius-core``:
  python scripts/generate_dcm2_maximal_stress.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path


def _axis_monotonic(n: int, rng: random.Random, *, spread: float) -> list[float]:
    t = 0.0
    out: list[float] = []
    for i in range(n):
        step = rng.uniform(0.04, 1.1) * (0.6 + 0.8 * math.sin(i * 0.55 + rng.uniform(0, 0.5)))
        t += step * spread
        out.append(round(t, 6))
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = round(out[i - 1] + 1e-4, 6)
    return out


def _pick_map_size(rng: random.Random) -> tuple[int, int]:
    pairs = (
        [(2, 2)] * 10
        + [(2, 3), (3, 2)] * 8
        + [(3, 3), (2, 4), (4, 2)] * 6
        + [(3, 5), (5, 3), (4, 4)] * 5
        + [(4, 6), (6, 4), (5, 5)] * 4
        + [(5, 7), (7, 4), (4, 8), (8, 3)] * 3
        + [(6, 6), (5, 8), (8, 5), (3, 9), (9, 3)] * 2
        + [(6, 9), (7, 7), (10, 4), (4, 10)]
    )
    return pairs[rng.randrange(len(pairs))]


def _pick_curve_n(rng: random.Random) -> int:
    return rng.choices(
        [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 20, 24],
        weights=[2, 3, 4, 5, 5, 5, 4, 4, 3, 3, 2, 2, 2, 1],
        k=1,
    )[0]


def _emit_kennfeld(lines: list[str], idx: int, rng: random.Random) -> None:
    nx, ny = _pick_map_size(rng)
    name = f"K_MAX_{idx:05d}"
    meta = rng.random() < 0.12
    lines.append(f"KENNFELD {name} {nx} {ny}")
    if meta:
        lines.append(' LANGNAME "Stress map with metadata"')
        lines.append(" EINHEIT kPa")
        lines.append(' LANGNAME_X "Speed axis"')
        lines.append(" EINHEIT_X rpm")
        lines.append(' LANGNAME_Y "Load axis"')
        lines.append(" EINHEIT_Y %")
        lines.append(f" VAR {name}")
    xax = _axis_monotonic(nx, rng, spread=rng.uniform(0.2, 2.0))
    yax = _axis_monotonic(ny, rng, spread=rng.uniform(0.15, 1.8))
    lines.append(" ST/X " + " ".join(f"{v:.6f}" for v in xax))
    for j, y in enumerate(yax):
        lines.append(f" ST/Y {y:.6f}")
        row = []
        for i, x in enumerate(xax):
            z = (
                0.02 * (i + 1) * (j + 1)
                + 1.8 * math.sin(0.35 * x + 0.22 * y)
                + 0.12 * (x * x) / (1.0 + y * y)
                + 0.5 * math.tanh((x - xax[len(xax) // 2]) / max(0.5, xax[-1] - xax[0] + 1e-6))
            )
            row.append(round(z * (1.0 + 0.01 * (idx % 97)), 6))
        lines.append(" WERT " + " ".join(f"{v:.6f}" for v in row))
    lines.append("END")
    lines.append("")


def _emit_kennlinie(lines: list[str], idx: int, rng: random.Random) -> None:
    n = _pick_curve_n(rng)
    name = f"K_MAX_{idx:05d}"
    meta = rng.random() < 0.12
    lines.append(f"KENNLINIE {name} {n}")
    if meta:
        lines.append(' LANGNAME "Stress curve with metadata"')
        lines.append(" EINHEIT Nm")
        lines.append(' LANGNAME_X "Speed axis"')
        lines.append(" EINHEIT_X rpm")
        lines.append(" FUNKTION StressSuite")
        lines.append(f" VAR {name}")
    xax = _axis_monotonic(n, rng, spread=rng.uniform(0.25, 2.5))
    wrow = []
    for i, x in enumerate(xax):
        w = (
            10.0 * (1.0 - math.exp(-x / max(0.8, xax[-1] * 0.25)))
            + 0.45 * x * math.sin(x / max(0.3, xax[-1] / 5))
            + 0.08 * (i * i)
        )
        wrow.append(round(w * (1.0 + 0.001 * (idx % 500)), 6))
    lines.append(" ST/X " + " ".join(f"{v:.6f}" for v in xax))
    lines.append(" WERT " + " ".join(f"{v:.6f}" for v in wrow))
    lines.append("END")
    lines.append("")


def _emit_festwert(lines: list[str], idx: int, rng: random.Random) -> None:
    name = f"K_MAX_{idx:05d}"
    val = round((idx % 10000) * 0.1 + rng.uniform(-2, 2), 3)
    meta = rng.random() < 0.08
    lines.append(f"FESTWERT {name}")
    if meta:
        lines.append(' LANGNAME "Stress scalar with metadata"')
        lines.append(" EINHEIT V")
        lines.append(f" VAR {name}")
    lines.append(f" WERT {val:.3f}")
    lines.append("END")
    lines.append("")


def _emit_festwerteblock(lines: list[str], idx: int, rng: random.Random) -> None:
    n = rng.randint(3, 14)
    name = f"K_MAX_{idx:05d}"
    lines.append(f"FESTWERTEBLOCK {name} {n}")
    base = (idx % 9000) * 0.01
    vals = []
    t = 0.0
    for k in range(n):
        t += rng.uniform(0.5, 3.0) * (1.0 + 0.3 * math.sin(k))
        vals.append(round(base + t + 0.2 * math.log1p(k + 1), 3))
    lines.append(" WERT " + " ".join(f"{v:.3f}" for v in vals))
    lines.append("END")
    lines.append("")


def _emit_stuetz(lines: list[str], idx: int, rng: random.Random) -> None:
    n = rng.randint(4, 14)
    name = f"K_MAX_{idx:05d}"
    lines.append(f"STUETZSTELLENVERTEILUNG {name} {n}")
    xax = _axis_monotonic(n, rng, spread=rng.uniform(1.0, 120.0))
    lines.append(" ST/X " + " ".join(f"{v:.3f}" for v in xax))
    lines.append("END")
    lines.append("")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_path = root / "tests" / "testdata" / "parameter_formats" / "dcm" / "dcm2_maximal_10000_kennwerte.dcm"
    rng = random.Random(20260402)
    kinds = (
        ["KENNFELD"] * 2000
        + ["KENNLINIE"] * 2000
        + ["FESTWERT"] * 2000
        + ["FESTWERTEBLOCK"] * 2000
        + ["STUETZ"] * 2000
    )
    rng.shuffle(kinds)
    lines: list[str] = [
        "* Generated stress-test example with 10000 Kenngroessen",
        "* Includes all supported DCM data types in random order",
        "* Kennfelder/Kennlinien: varied sizes, nonlinear axes and values",
        "* Random seed: 20260402",
        "KONSERVIERUNG_FORMAT 2.0",
        "",
    ]
    emitters = {
        "KENNFELD": _emit_kennfeld,
        "KENNLINIE": _emit_kennlinie,
        "FESTWERT": _emit_festwert,
        "FESTWERTEBLOCK": _emit_festwerteblock,
        "STUETZ": _emit_stuetz,
    }
    for i, kind in enumerate(kinds):
        emitters[kind](lines, i, rng)
    text = "\n".join(lines).rstrip() + "\n"
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path} ({len(text) // 1024} KiB)")


if __name__ == "__main__":
    main()
