from __future__ import annotations

import sys
from pathlib import Path


def _load_simulation_framework():
    """Import ``SimulationFramework`` for frozen, editable install, or ``python .../__main__.py``."""
    if getattr(sys, "frozen", False):
        from synarius_core.simulation import SimulationFramework

        return SimulationFramework

    if __package__:
        from .simulation import SimulationFramework

        return SimulationFramework

    # Running ``python .../synarius_core/__main__.py`` sets ``__package__`` to None; relative imports fail.
    core_src = Path(__file__).resolve().parents[1]
    if str(core_src) not in sys.path:
        sys.path.insert(0, str(core_src))
    from synarius_core.simulation import SimulationFramework

    return SimulationFramework


def main() -> None:
    SimulationFramework = _load_simulation_framework()
    sim = SimulationFramework(dt=1.0)
    sim.run(max_steps=3)
    print(f"Finished: time={sim.state.time}, steps={sim.state.step_count}")


if __name__ == "__main__":
    main()
