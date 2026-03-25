import sys
from pathlib import Path


# Make `src/` importable when running tests via `python -m unittest`.
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))


from synarius_core import SimulationFramework


import unittest


class SmokeTest(unittest.TestCase):
    def test_simulation_smoke(self) -> None:
        sim = SimulationFramework(dt=0.5)
        sim.run(max_steps=4)
        self.assertEqual(sim.state.step_count, 4)
        self.assertEqual(sim.state.time, 2.0)

