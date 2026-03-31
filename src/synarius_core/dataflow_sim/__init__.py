"""Dataflow compile + step engine (scalar variables/operators; generic elementaries in graph only).

After :class:`DataflowCompilePass`, ``ctx.artifacts`` contains:

* ``dataflow`` — :class:`CompiledDataflow` (or ``None`` if the graph has a cycle).
* ``fmu_diagram`` — :class:`CompiledFmuDiagram` with FMU node ids when the graph is valid,
  else ``None`` (cycle). For a valid graph without FMU blocks, ``fmu_node_ids`` is empty.

FMU-specific wiring checks are appended to ``ctx.diagnostics`` (unconnected pins, optional
``fmu.variables`` causality vs connector direction, simple pin ``data_type`` compatibility).
"""

from .compiler import (
    CompiledDataflow,
    CompiledFmuDiagram,
    DataflowCompilePass,
    elementary_has_fmu_path,
    iter_live_connectors,
    iter_live_diagram_nodes,
)
from .context import SimulationContext
from .engine import SimpleRunEngine
from .stimulation import is_stimulated, stimulation_value

__all__ = [
    "CompiledDataflow",
    "CompiledFmuDiagram",
    "DataflowCompilePass",
    "elementary_has_fmu_path",
    "SimulationContext",
    "SimpleRunEngine",
    "is_stimulated",
    "stimulation_value",
    "iter_live_connectors",
    "iter_live_diagram_nodes",
]
