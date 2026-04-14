"""Dataflow compile + step engine (scalar variables/operators; generic elementaries in graph only).

After :class:`DataflowCompilePass`, ``ctx.artifacts`` contains:

* ``dataflow`` — :class:`CompiledDataflow`, or ``None`` if compilation failed (e.g. FMU on a
  directed cycle, or invalid ``dataflow.scalar_slot_id`` on an FMU block).
* ``fmu_diagram`` — :class:`CompiledFmuDiagram` with FMU node ids when the graph is valid,
  else ``None``. For a valid graph without FMU blocks, ``fmu_node_ids`` is empty.

  Directed cycles among **non-FMU** nodes are accepted: the compiler inserts **unit-delay
  feedback** on a minimal edge set so the remainder is acyclic; see :class:`CompiledDataflow`
  ``feedback_edges`` and ``RunStepExchange.workspace_previous``.

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
from .codegen_kernel import generate_fmfl_document, generate_python_kernel_document
from .python_step_emit import generate_unrolled_python_step_document
from .scalar_equations import apply_scalar_equations_topo, eval_basic_operator
from .step_exchange import RunStepExchange
from .unrolled_loader import load_run_equations_from_source
from .runtime_source_text import read_simple_run_engine_module_source
from .stimulation import (
    STIMULATION_DISPLAY_KEYS,
    ensure_variable_stimulation_schema,
    is_stimulated,
    stimulation_value,
)

__all__ = [
    "CompiledDataflow",
    "CompiledFmuDiagram",
    "DataflowCompilePass",
    "elementary_has_fmu_path",
    "SimulationContext",
    "SimpleRunEngine",
    "generate_fmfl_document",
    "generate_python_kernel_document",
    "generate_unrolled_python_step_document",
    "RunStepExchange",
    "load_run_equations_from_source",
    "apply_scalar_equations_topo",
    "eval_basic_operator",
    "read_simple_run_engine_module_source",
    "STIMULATION_DISPLAY_KEYS",
    "ensure_variable_stimulation_schema",
    "is_stimulated",
    "stimulation_value",
    "iter_live_connectors",
    "iter_live_diagram_nodes",
]
