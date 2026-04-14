"""Tests for per-kind stimulation attributes and legacy migration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim.stimulation import (  # noqa: E402
    LEGACY_STIM_P_KEYS,
    STIM_CONSTANT_VALUE,
    STIM_RAMP_OFFSET,
    STIM_RAMP_SLOPE,
    STIM_SINE_AMPLITUDE,
    STIM_SINE_FREQUENCY_HZ,
    STIM_SINE_OFFSET,
    STIM_SINE_PHASE_DEG,
    STIM_STEP_HIGH,
    STIM_STEP_LOW,
    STIM_STEP_SWITCH_TIME_S,
    ensure_variable_stimulation_schema,
    stimulation_value,
)
from synarius_core.model import Model, Variable  # noqa: E402


class StimulationPerKindTest(unittest.TestCase):
    def test_constant_uses_named_slot(self) -> None:
        v = Variable(name="c", type_key="t", value=0.0)
        v.set("stim_kind", "constant")
        v.set(STIM_CONSTANT_VALUE, 3.25)
        self.assertAlmostEqual(stimulation_value(v, 0.5), 3.25, places=5)

    def test_ramp_sine_step_named_slots(self) -> None:
        r = Variable(name="r", type_key="t", value=0.0)
        r.set("stim_kind", "ramp")
        r.set(STIM_RAMP_OFFSET, 1.0)
        r.set(STIM_RAMP_SLOPE, 2.0)
        self.assertAlmostEqual(stimulation_value(r, 3.0), 7.0, places=5)

        s = Variable(name="s", type_key="t", value=0.0)
        s.set("stim_kind", "sine")
        s.set(STIM_SINE_OFFSET, 0.0)
        s.set(STIM_SINE_AMPLITUDE, 1.0)
        s.set(STIM_SINE_FREQUENCY_HZ, 0.0)
        s.set(STIM_SINE_PHASE_DEG, 0.0)
        self.assertAlmostEqual(stimulation_value(s, 1.0), 0.0, places=5)

        st = Variable(name="st", type_key="t", value=0.0)
        st.set("stim_kind", "step")
        st.set(STIM_STEP_LOW, 0.0)
        st.set(STIM_STEP_SWITCH_TIME_S, 1.0)
        st.set(STIM_STEP_HIGH, 5.0)
        self.assertAlmostEqual(stimulation_value(st, 0.5), 0.0, places=5)
        self.assertAlmostEqual(stimulation_value(st, 1.0), 5.0, places=5)

    def test_switch_kind_preserves_other_kind_params(self) -> None:
        v = Variable(name="sw", type_key="t", value=0.0)
        v.set("stim_kind", "constant")
        v.set(STIM_CONSTANT_VALUE, 5.0)
        v.set(STIM_RAMP_OFFSET, 10.0)
        v.set(STIM_RAMP_SLOPE, 2.0)
        v.set("stim_kind", "ramp")
        self.assertAlmostEqual(stimulation_value(v, 1.0), 12.0, places=5)
        v.set("stim_kind", "constant")
        self.assertAlmostEqual(stimulation_value(v, 0.0), 5.0, places=5)

    def test_legacy_migration_ramp(self) -> None:
        v = Variable(name="leg", type_key="t", value=0.0)
        # Simulate a legacy-only subtree: drop v1 params + schema, keep stim_kind + stim_p*.
        for k in list(v.attribute_dict.keys()):
            if not str(k).startswith("stim_"):
                continue
            if k in ("stim_kind",) + LEGACY_STIM_P_KEYS:
                continue
            del v.attribute_dict[k]
        v.set("stim_kind", "ramp")
        v.set("stim_p0", 1.0)
        v.set("stim_p1", 3.0)
        ensure_variable_stimulation_schema(v)
        self.assertAlmostEqual(float(v.get(STIM_RAMP_OFFSET)), 1.0, places=5)
        self.assertAlmostEqual(float(v.get(STIM_RAMP_SLOPE)), 3.0, places=5)
        self.assertAlmostEqual(stimulation_value(v, 2.0), 7.0, places=5)

    def test_model_attach_variable_migrates_on_stimulation_read(self) -> None:
        m = Model.new("main")
        v = Variable(name="x", type_key="t", value=0.0)
        m.attach(v, parent=m.root, reserve_existing=False, remap_ids=False)
        v.set("stim_kind", "constant")
        v.set("stim_p0", -9.81)
        stimulation_value(v, 0.0)
        self.assertAlmostEqual(float(v.get(STIM_CONSTANT_VALUE)), -9.81, places=5)


if __name__ == "__main__":
    unittest.main()
