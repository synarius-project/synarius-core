"""Dataflow compile + step engine (scalar, generic stimulation; no FMU)."""

from .compiler import (
    CompiledDataflow,
    DataflowCompilePass,
    iter_live_connectors,
    iter_live_diagram_nodes,
)
from .context import SimulationContext
from .engine import SimpleRunEngine
from .stimulation import is_stimulated, stimulation_value

__all__ = [
    "CompiledDataflow",
    "DataflowCompilePass",
    "SimulationContext",
    "SimpleRunEngine",
    "is_stimulated",
    "stimulation_value",
    "iter_live_connectors",
    "iter_live_diagram_nodes",
]
