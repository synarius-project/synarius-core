from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimulationState:
    """Holds the mutable simulation state."""

    time: float = 0.0
    step_count: int = 0


class SimulationFramework:
    """
    Minimal, step-based simulation framework.

    GUI projects should import this package but not be required for simulation to work.
    """

    def __init__(self, dt: float = 1.0):
        if dt <= 0:
            raise ValueError("dt must be > 0")
        self.dt = float(dt)
        self.state = SimulationState()

    def reset(self) -> SimulationState:
        """Reset the internal state."""
        self.state = SimulationState()
        return self.state

    def step(self) -> SimulationState:
        """Advance the simulation by one step."""
        self.state.time += self.dt
        self.state.step_count += 1
        return self.state

    def run(self, max_steps: int) -> SimulationState:
        """Run the simulation for `max_steps` steps."""
        if max_steps < 0:
            raise ValueError("max_steps must be >= 0")
        for _ in range(max_steps):
            self.step()
        return self.state

