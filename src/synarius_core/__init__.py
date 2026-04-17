"""Public package API for synarius-core.

This module exposes the main simulation façade types as well as
the top-level subpackages that make up the core architecture.
"""

from .simulation import SimulationFramework, SimulationState
# ``cli`` must come after ``controller``: :mod:`synarius_core.cli.synarius_cli` imports
# :class:`~synarius_core.controller.synarius_controller.SynariusController`. Loading ``cli``
# first leaves ``synarius_core.controller`` only partially initialized and breaks
# ``from synarius_core.controller import SynariusController`` (e.g. PyInstaller / Studio).
from . import (
    controller,
    cli,
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

