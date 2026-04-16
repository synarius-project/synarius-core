"""Generic time-based stimulation for variables (constant, ramp, sine, step).

Each ``stim_kind`` uses its **own** attribute names (no semantic overloading of shared
``stim_p0``…``stim_p3``). Switching kind only changes which parameters ``stimulation_value``
reads; other per-kind parameters stay stored on the variable.

**Legacy:** Models that still have ``stim_p0``…``stim_p3`` are migrated once (see
:func:`ensure_variable_stimulation_schema`) using the current ``stim_kind`` to interpret
the old slots; then those keys are removed.
"""

from __future__ import annotations

import math
from typing import Final

from synarius_core.model import Variable
from synarius_core.model.attribute_dict import AttributeEntry

_STIM_KINDS = frozenset({"none", "constant", "ramp", "sine", "step"})

STIM_SCHEMA_VERSION: Final[int] = 1

# --- Per-kind parameters (CCP / lsattr) -----------------------------------------

STIM_KIND_ATTR = "stim_kind"
STIM_SCHEMA_VERSION_ATTR = "stim_params_schema_version"

STIM_CONSTANT_VALUE = "stim_constant_value"
STIM_RAMP_OFFSET = "stim_ramp_offset"
STIM_RAMP_SLOPE = "stim_ramp_slope"
STIM_SINE_OFFSET = "stim_sine_offset"
STIM_SINE_AMPLITUDE = "stim_sine_amplitude"
STIM_SINE_FREQUENCY_HZ = "stim_sine_frequency_hz"
STIM_SINE_PHASE_DEG = "stim_sine_phase_deg"
STIM_STEP_LOW = "stim_step_low"
STIM_STEP_SWITCH_TIME_S = "stim_step_switch_time_s"
STIM_STEP_HIGH = "stim_step_high"

LEGACY_STIM_P_KEYS: Final[tuple[str, ...]] = ("stim_p0", "stim_p1", "stim_p2", "stim_p3")

# Order for ``print`` / tooling (excludes legacy after migration).
STIMULATION_DISPLAY_KEYS: Final[tuple[str, ...]] = (
    STIM_KIND_ATTR,
    STIM_SCHEMA_VERSION_ATTR,
    STIM_CONSTANT_VALUE,
    STIM_RAMP_OFFSET,
    STIM_RAMP_SLOPE,
    STIM_SINE_OFFSET,
    STIM_SINE_AMPLITUDE,
    STIM_SINE_FREQUENCY_HZ,
    STIM_SINE_PHASE_DEG,
    STIM_STEP_LOW,
    STIM_STEP_SWITCH_TIME_S,
    STIM_STEP_HIGH,
)

# Keys to copy when cloning a variable (includes legacy for old subtrees).
STIMULATION_PASTE_KEYS: Final[tuple[str, ...]] = STIMULATION_DISPLAY_KEYS + LEGACY_STIM_P_KEYS

# ``Variable._install_stimulation_attributes`` — (key, default) for ``attribute_dict`` tuples (no legacy ``stim_p*``).
STIMULATION_INSTALL_ENTRIES: Final[tuple[tuple[str, str | int | float], ...]] = (
    (STIM_KIND_ATTR, "none"),
    (STIM_SCHEMA_VERSION_ATTR, STIM_SCHEMA_VERSION),
    (STIM_CONSTANT_VALUE, 0.0),
    (STIM_RAMP_OFFSET, 0.0),
    (STIM_RAMP_SLOPE, 1.0),
    (STIM_SINE_OFFSET, 0.0),
    (STIM_SINE_AMPLITUDE, 1.0),
    (STIM_SINE_FREQUENCY_HZ, 1.0),
    (STIM_SINE_PHASE_DEG, 0.0),
    (STIM_STEP_LOW, 0.0),
    (STIM_STEP_SWITCH_TIME_S, 0.0),
    (STIM_STEP_HIGH, 1.0),
)

_STIM_ALL_KNOWN_DEFAULTS: dict[str, str | int | float] = {k: v for k, v in STIMULATION_INSTALL_ENTRIES}
for _lk, _lv in zip(LEGACY_STIM_P_KEYS, (0.0, 1.0, 1.0, 0.0), strict=True):
    _STIM_ALL_KNOWN_DEFAULTS[_lk] = _lv


def register_stim_attribute_if_missing(var: Variable, key: str) -> None:
    """Allow ``set stim_p0 …`` / other ``stim_*`` keys on variables without pre-created slots."""
    if key in var.attribute_dict:
        return
    if key not in _STIM_ALL_KNOWN_DEFAULTS:
        return
    dict.__setitem__(var.attribute_dict, key, AttributeEntry.stored(_STIM_ALL_KNOWN_DEFAULTS[key], writable=True))


def on_legacy_stim_parameter_set(var: Variable) -> None:
    """Mirror deprecated ``stim_p*`` into per-kind attrs when schema is already v1 (post-migration scripts)."""
    if _schema_version(var) < STIM_SCHEMA_VERSION:
        return
    if not _has_legacy_stim_slots(var):
        return
    kind = _s(var, STIM_KIND_ATTR, "none")
    if kind in ("", "none", "off"):
        return
    p0 = _f(var, LEGACY_STIM_P_KEYS[0], 0.0)
    p1 = _f(var, LEGACY_STIM_P_KEYS[1], 1.0)
    p2 = _f(var, LEGACY_STIM_P_KEYS[2], 1.0)
    p3 = _f(var, LEGACY_STIM_P_KEYS[3], 0.0)
    if kind == "constant":
        var.set(STIM_CONSTANT_VALUE, p0)
    elif kind == "ramp":
        var.set(STIM_RAMP_OFFSET, p0)
        var.set(STIM_RAMP_SLOPE, p1)
    elif kind == "sine":
        var.set(STIM_SINE_OFFSET, p0)
        var.set(STIM_SINE_AMPLITUDE, p1)
        var.set(STIM_SINE_FREQUENCY_HZ, p2)
        var.set(STIM_SINE_PHASE_DEG, p3)
    elif kind == "step":
        var.set(STIM_STEP_LOW, p0)
        var.set(STIM_STEP_SWITCH_TIME_S, p1)
        var.set(STIM_STEP_HIGH, p2)


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


def _schema_version(var: Variable) -> int:
    try:
        return int(var.get(STIM_SCHEMA_VERSION_ATTR))
    except (KeyError, TypeError, ValueError):
        return 0


def _has_legacy_stim_slots(var: Variable) -> bool:
    return any(k in var.attribute_dict for k in LEGACY_STIM_P_KEYS)


def _apply_default_stimulation_params(var: Variable, *, overwrite: bool = False) -> None:
    """Ensure all per-kind parameters exist with defaults (matches former ctor defaults)."""
    defaults: dict[str, float] = {
        STIM_CONSTANT_VALUE: 0.0,
        STIM_RAMP_OFFSET: 0.0,
        STIM_RAMP_SLOPE: 1.0,
        STIM_SINE_OFFSET: 0.0,
        STIM_SINE_AMPLITUDE: 1.0,
        STIM_SINE_FREQUENCY_HZ: 1.0,
        STIM_SINE_PHASE_DEG: 0.0,
        STIM_STEP_LOW: 0.0,
        STIM_STEP_SWITCH_TIME_S: 0.0,
        STIM_STEP_HIGH: 1.0,
    }
    for key, val in defaults.items():
        if overwrite or key not in var.attribute_dict:
            var.set(key, val)


def _legacy_float(var: Variable, index: int, default: float) -> float:
    key = LEGACY_STIM_P_KEYS[index]
    if key not in var.attribute_dict:
        return default
    return _f(var, key, default)


def ensure_variable_stimulation_schema(var: Variable) -> None:
    """If ``stim_params_schema_version`` < 1, map legacy ``stim_p*`` into per-kind attrs and drop legacy keys."""
    if _schema_version(var) >= STIM_SCHEMA_VERSION:
        return

    kind = _s(var, STIM_KIND_ATTR, "none")
    has_legacy = _has_legacy_stim_slots(var)

    p0 = _legacy_float(var, 0, 0.0)
    p1 = _legacy_float(var, 1, 1.0)
    p2 = _legacy_float(var, 2, 1.0)
    p3 = _legacy_float(var, 3, 0.0)

    _apply_default_stimulation_params(var, overwrite=False)

    if has_legacy:
        if kind == "constant":
            var.set(STIM_CONSTANT_VALUE, p0)
        elif kind == "ramp":
            var.set(STIM_RAMP_OFFSET, p0)
            var.set(STIM_RAMP_SLOPE, p1)
        elif kind == "sine":
            var.set(STIM_SINE_OFFSET, p0)
            var.set(STIM_SINE_AMPLITUDE, p1)
            var.set(STIM_SINE_FREQUENCY_HZ, p2)
            var.set(STIM_SINE_PHASE_DEG, p3)
        elif kind == "step":
            var.set(STIM_STEP_LOW, p0)
            var.set(STIM_STEP_SWITCH_TIME_S, p1)
            var.set(STIM_STEP_HIGH, p2)

        for lk in LEGACY_STIM_P_KEYS:
            if lk in var.attribute_dict:
                del var.attribute_dict[lk]

    var.set(STIM_SCHEMA_VERSION_ATTR, STIM_SCHEMA_VERSION)


def stimulation_value(var: Variable, time_s: float) -> float | None:
    """
    If ``var`` has active stimulation, return the value at ``time_s``; else ``None``.

    **Attributes** (see module constants for names):

    * ``stim_kind``: ``none`` | ``constant`` | ``ramp`` | ``sine`` | ``step``
    * **constant:** ``stim_constant_value``
    * **ramp:** ``stim_ramp_offset``, ``stim_ramp_slope`` (value = offset + slope * t)
    * **sine:** ``stim_sine_offset``, ``stim_sine_amplitude``, ``stim_sine_frequency_hz``,
      ``stim_sine_phase_deg``
    * **step:** ``stim_step_low``, ``stim_step_switch_time_s``, ``stim_step_high``
    """
    ensure_variable_stimulation_schema(var)
    kind = _s(var, STIM_KIND_ATTR, "none")
    if kind in ("", "none", "off"):
        return None
    if kind not in _STIM_KINDS:
        return None
    t = float(time_s)
    if kind == "constant":
        return _f(var, STIM_CONSTANT_VALUE, 0.0)
    if kind == "ramp":
        return _f(var, STIM_RAMP_OFFSET, 0.0) + _f(var, STIM_RAMP_SLOPE, 0.0) * t
    if kind == "sine":
        off = _f(var, STIM_SINE_OFFSET, 0.0)
        amp = _f(var, STIM_SINE_AMPLITUDE, 1.0)
        hz = _f(var, STIM_SINE_FREQUENCY_HZ, 1.0)
        ph = math.radians(_f(var, STIM_SINE_PHASE_DEG, 0.0))
        return off + amp * math.sin(2.0 * math.pi * hz * t + ph)
    if kind == "step":
        low = _f(var, STIM_STEP_LOW, 0.0)
        t_sw = _f(var, STIM_STEP_SWITCH_TIME_S, 0.0)
        high = _f(var, STIM_STEP_HIGH, 1.0)
        return high if t >= t_sw else low
    return None


def is_stimulated(var: Variable) -> bool:
    ensure_variable_stimulation_schema(var)
    kind = _s(var, STIM_KIND_ATTR, "none")
    return kind not in ("", "none", "off")
