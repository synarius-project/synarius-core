"""Public package API for synarius-core.

This module exposes the main simulation façade types as well as
the top-level subpackages that make up the core architecture.
"""

from .simulation import SimulationFramework, SimulationState
from . import (
    cli,
    controller,
    codegen,
    fmu,
    io,
    library,
    model,
    persistence,
    recording,
    run_engine,
    stimulus,
    standard_library,
    utils,
)

__all__ = [
    "SimulationFramework",
    "SimulationState",
    # Subpackages
    "cli",
    "controller",
    "library",
    "model",
    "persistence",
    "fmu",
    "run_engine",
    "stimulus",
    "recording",
    "codegen",
    "io",
    "utils",
    "standard_library",
]

