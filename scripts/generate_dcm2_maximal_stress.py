"""Regenerate ``dcm2_maximal_10000_kennwerte.dcm`` with varied map/curve sizes and nonlinear data.

Preserves: 2000 blocks each of KENNFELD, KENNLINIE, FESTWERT, FESTWERTEBLOCK,
STUETZSTELLENVERTEILUNG; seed-shuffled interleaving; random seed 20260402.

Symbols use rotating automotive ``Cal_*`` stems (torque/velocity-themed) plus a
five-digit index for uniqueness.

Run from ``synarius-core``:
  python scripts/generate_dcm2_maximal_stress.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path

# Automotive-style calibration identifiers (ASCII). Suffix _{idx:05d} keeps names unique in [0, 9999].
_MAP_STEMS: tuple[str, ...] = (
    "Cal_TrqVelFld",
    "Cal_BoostTrqMap",
    "Cal_EngVelFuMass",
    "Cal_WheelTrqSplit",
    "Cal_MotorTrqSurf",
    "Cal_TransTrqShift",
    "Cal_DiffVelLockMap",
    "Cal_RgnTrqLimFld",
    "Cal_InjTrqPulse",
    "Cal_EgrVelMixMap",
    "Cal_CatTempTrq",
    "Cal_TurboVelSurge",
)
_CURVE_STEMS: tuple[str, ...] = (
    "Cal_CrankTrqVelCrv",
    "Cal_PedlTrqRamp",
    "Cal_BrkTrqVelCurve",
    "Cal_GbxTrqConvLin",
    "Cal_IdleVelStabCrv",
    "Cal_AccelTrqDem",
    "Cal_StallTrqLimCrv",
    "Cal_CruiseVelHold",
    "Cal_SPCTrqInterp",
    "Cal_TCSVelRedLin",
)
_SCALAR_STEMS: tuple[str, ...] = (
    "Cal_VelLimGainSc",
    "Cal_BattRefVolt",
    "Cal_TrqRedFact",
    "Cal_WheelSpdGain",
    "Cal_EngIdleVelOfs",
    "Cal_YawRateTrqK",
    "Cal_ParkBrkTrq",
)
_VBLK_STEMS: tuple[str, ...] = (
    "Cal_SensTrqOfsVec",
    "Cal_CylPrsOfsBlk",
    "Cal_PhaseCurOfs",
    "Cal_PinionTrqTab",
    "Cal_VelFldGainArr",
    "Cal_BrakePadTempVec",
)
_AXIS_STEMS: tuple[str, ...] = (
    "Cal_CrankAngVelAx",
    "Cal_ThrotVelBrk",
    "Cal_VehLongVelSts",
    "Cal_RoadSpdAxis",
    "Cal_MotorRPMVel",
    "Cal_TrqDemAxis",
)


def _cal_name_map(idx: int) -> str:
    return f"{_MAP_STEMS[idx % len(_MAP_STEMS)]}_{idx:05d}"


def _cal_name_curve(idx: int) -> str:
    return f"{_CURVE_STEMS[idx % len(_CURVE_STEMS)]}_{idx:05d}"


def _cal_name_scalar(idx: int) -> str:
    return f"{_SCALAR_STEMS[idx % len(_SCALAR_STEMS)]}_{idx:05d}"


def _cal_name_valblk(idx: int) -> str:
    return f"{_VBLK_STEMS[idx % len(_VBLK_STEMS)]}_{idx:05d}"


def _cal_name_axis(idx: int) -> str:
    return f"{_AXIS_STEMS[idx % len(_AXIS_STEMS)]}_{idx:05d}"


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


def _canonical_curve_axis(n: int) -> list[float]:
    out: list[float] = []
    for i in range(n):
        t = float(i + 1)
        v = (t**1.28) * (1.0 + 0.04 * math.sin(0.6 * t))
        out.append(round(v, 6))
    for i in range(1, n):
        if out[i] <= out[i - 1]:
            out[i] = round(out[i - 1] + 1e-4, 6)
    return out


def _canonical_map_axis(n: int, *, phase: float, scale: float) -> list[float]:
    out: list[float] = []
    for i in range(n):
        t = float(i + 1)
        v = scale * (t**1.22) * (1.0 + 0.035 * math.sin(phase + 0.55 * t))
        out.append(round(v, 6))
    for i in range(1, n):
        if out[i] <= out[i - 1]:
            out[i] = round(out[i - 1] + 1e-4, 6)
    return out


def _select_curve_axis(n: int, rng: random.Random) -> list[float]:
    # Most curves share canonical axes by length; a minority keeps random nonlinearity.
    if rng.random() < 0.82:
        return _canonical_curve_axis(n)
    return _axis_monotonic(n, rng, spread=rng.uniform(0.25, 2.5))


def _select_map_axes(nx: int, ny: int, rng: random.Random) -> tuple[list[float], list[float]]:
    # Most maps share canonical axes by axis length; minority keeps per-parameter variation.
    if rng.random() < 0.82:
        return (
            _canonical_map_axis(nx, phase=0.3, scale=1.0),
            _canonical_map_axis(ny, phase=1.1, scale=0.85),
        )
    return (
        _axis_monotonic(nx, rng, spread=rng.uniform(0.2, 2.0)),
        _axis_monotonic(ny, rng, spread=rng.uniform(0.15, 1.8)),
    )


def _emit_kennfeld(lines: list[str], idx: int, rng: random.Random) -> None:
    nx, ny = _pick_map_size(rng)
    name = _cal_name_map(idx)
    meta = rng.random() < 0.12
    lines.append(f"KENNFELD {name} {nx} {ny}")
    if meta:
        lines.append(' LANGNAME "Boost torque map vs velocity axes"')
        lines.append(" EINHEIT kPa")
        lines.append(' LANGNAME_X "Engine velocity axis"')
        lines.append(" EINHEIT_X rpm")
        lines.append(' LANGNAME_Y "Driver torque demand axis"')
        lines.append(" EINHEIT_Y %")
        lines.append(f" VAR {name}")
    xax, yax = _select_map_axes(nx, ny, rng)
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
    name = _cal_name_curve(idx)
    meta = rng.random() < 0.12
    lines.append(f"KENNLINIE {name} {n}")
    if meta:
        lines.append(' LANGNAME "Crank torque delivery curve vs engine velocity"')
        lines.append(" EINHEIT Nm")
        lines.append(' LANGNAME_X "Engine velocity axis"')
        lines.append(" EINHEIT_X rpm")
        lines.append(" FUNKTION VehicleStressCalibration")
        lines.append(f" VAR {name}")
    xax = _select_curve_axis(n, rng)
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
    name = _cal_name_scalar(idx)
    val = round((idx % 10000) * 0.1 + rng.uniform(-2, 2), 3)
    meta = rng.random() < 0.08
    lines.append(f"FESTWERT {name}")
    if meta:
        lines.append(' LANGNAME "Vehicle velocity limiter gain scalar"')
        lines.append(" EINHEIT V")
        lines.append(f" VAR {name}")
    lines.append(f" WERT {val:.3f}")
    lines.append("END")
    lines.append("")


def _emit_festwerteblock(lines: list[str], idx: int, rng: random.Random) -> None:
    name = _cal_name_valblk(idx)
    base = (idx % 9000) * 0.01
    # ASAM DCM2 allows multidimensional FESTWERTEBLOCK: "<nx> @ <ny>" + ny WERT rows.
    if rng.random() < 0.36:
        nx = rng.randint(3, 10)
        ny = rng.randint(2, 6)
        lines.append(f"FESTWERTEBLOCK {name} {nx} @ {ny}")
        for j in range(ny):
            vals: list[float] = []
            t = 0.0
            for i in range(nx):
                t += rng.uniform(0.4, 2.6) * (1.0 + 0.25 * math.sin(i + 0.6 * j))
                vals.append(round(base + 0.8 * j + t + 0.15 * math.log1p(i + 1), 3))
            lines.append(" WERT " + " ".join(f"{v:.3f}" for v in vals))
    else:
        n = rng.randint(3, 14)
        lines.append(f"FESTWERTEBLOCK {name} {n}")
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
    name = _cal_name_axis(idx)
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
