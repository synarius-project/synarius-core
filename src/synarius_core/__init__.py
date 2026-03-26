"""Public package API for synarius-core.

This module exposes the main simulation façade types as well as
the top-level subpackages that make up the core architecture.
"""

from .simulation import SimulationFramework, SimulationState
from . import (
    cli,
    controller,
    model,
    persistence,
    fmu,
    run_engine,
    stimulus,
    recording,
    codegen,
    utils,
)

__all__ = [
    "SimulationFramework",
    "SimulationState",
    # Subpackages
    "cli",
    "controller",
    "model",
    "persistence",
    "fmu",
    "run_engine",
    "stimulus",
    "recording",
    "codegen",
    "utils",
]

