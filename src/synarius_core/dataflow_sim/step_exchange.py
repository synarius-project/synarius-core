"""Host exchange object for one scalar dataflow **equations** step (generated ``run_equations``).

Stimulation and copying results to diagram variables are handled by :class:`~.engine.SimpleRunEngine`
**outside** the generated function; see :class:`RunStepExchange` field docs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, AbstractSet
from uuid import UUID


@dataclass
class RunStepExchange:
    """Data passed into generated ``run_equations(exchange)`` for one logical step.

    * ``workspace`` — same mapping as :attr:`~synarius_core.dataflow_sim.context.SimulationContext.scalar_workspace`
      (label-string keys: ``"node_name"`` for scalars, ``"node_name.pin_name"`` for FMU output pins).
    * ``workspace_previous`` — snapshot of ``workspace`` at **step start** (before stimulation) for
      **delayed feedback** edges; unused when the graph is acyclic. Same keying as ``workspace``.
    * ``stimmed`` — variable labels (strings) that already received a stimulation value this step;
      generated code skips overwriting those slots.
    * ``fmu_step`` — optional callback for FMU diagram nodes (same role as the engine's ``step_fmu`` hook).
    * ``simulation_context`` — optional :class:`~synarius_core.dataflow_sim.context.SimulationContext` for plugins.
    """

    workspace: MutableMapping[object, float]
    stimmed: AbstractSet[str]
    time_s: float = 0.0
    dt_s: float = 0.02
    workspace_previous: Mapping[object, float] | None = None
    fmu_step: Callable[[UUID], None] | None = None
    simulation_context: Any | None = None
    #: Resolved parameter data for this step: node UUID → (values_ndarray, axes_dict).
    #: Populated by :class:`~synarius_core.dataflow_sim.engine.SimpleRunEngine` when a
    #: :class:`~synarius_core.parameters.runtime.ParameterRuntime` is attached.
    param_cache: dict | None = None
