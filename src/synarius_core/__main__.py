from __future__ import annotations

from .simulation import SimulationFramework


def main() -> None:
    sim = SimulationFramework(dt=1.0)
    sim.run(max_steps=3)
    print(f"Finished: time={sim.state.time}, steps={sim.state.step_count}")


if __name__ == "__main__":
    main()

