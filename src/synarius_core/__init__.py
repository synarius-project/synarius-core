"""Public package API for synarius-core.

This module exposes the main simulation façade types as well as
the top-level subpackages that make up the core architecture.
"""

from .simulation import SimulationFramework, SimulationState
from . import (
    cli,
    controller,
    fmu,
    io,
    library,
    model,
    plugins,
    recording,
    standard_library,
)

__all__ = [
    "SimulationFramework",
    "SimulationState",
    # Subpackages
    "cli",
    "controller",
    "library",
    "model",
    "plugins",
    "fmu",
    "recording",
    "io",
    "standard_library",
]

