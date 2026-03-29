"""Generic time-based stimulation for variables (constant, ramp, sine, step)."""

from __future__ import annotations

import math

from synarius_core.model import Variable

_STIM_KINDS = frozenset({"none", "constant", "ramp", "sine", "step"})


def _f(var: Variable, key: str, default: float = 0.0) -> float:
    try:
        v = var.get(key)
        return float(v)
    except (KeyError, TypeError, ValueError):
        return default


def _s(var: Variable, key: str, default: str = "none") -> str:
    try:
        return str(var.get(key)).strip().lower()
    except (KeyError, TypeError, ValueError):
        return default


def stimulation_value(var: Variable, time_s: float) -> float | None:
    """
    If ``var`` has active stimulation, return the value at ``time_s``; else ``None``.

    Attributes (writable on ``Variable``):

    * ``stim_kind``: ``none`` | ``constant`` | ``ramp`` | ``sine`` | ``step``
    * ``stim_p0`` … ``stim_p3``: parameters (meaning depends on ``stim_kind``):

      - **constant**: ``p0`` = value
      - **ramp**: ``p0`` = offset, ``p1`` = slope (value = ``p0 + p1 * t``)
      - **sine**: ``p0`` = offset, ``p1`` = amplitude, ``p2`` = frequency (Hz),
        ``p3`` = phase (degrees)
      - **step**: ``p0`` = value before switch, ``p1`` = switch time (s),
        ``p2`` = value at/after switch
    """
    kind = _s(var, "stim_kind", "none")
    if kind in ("", "none", "off"):
        return None
    if kind not in _STIM_KINDS:
        return None
    t = float(time_s)
    if kind == "constant":
        return _f(var, "stim_p0", 0.0)
    if kind == "ramp":
        return _f(var, "stim_p0", 0.0) + _f(var, "stim_p1", 0.0) * t
    if kind == "sine":
        off = _f(var, "stim_p0", 0.0)
        amp = _f(var, "stim_p1", 1.0)
        hz = _f(var, "stim_p2", 1.0)
        ph = math.radians(_f(var, "stim_p3", 0.0))
        return off + amp * math.sin(2.0 * math.pi * hz * t + ph)
    if kind == "step":
        low = _f(var, "stim_p0", 0.0)
        t_sw = _f(var, "stim_p1", 0.0)
        high = _f(var, "stim_p2", 1.0)
        return high if t >= t_sw else low
    return None


def is_stimulated(var: Variable) -> bool:
    kind = _s(var, "stim_kind", "none")
    return kind not in ("", "none", "off")
