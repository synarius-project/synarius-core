"""Host exchange object for one scalar dataflow **equations** step (generated ``run_equations``).

Stimulation and copying results to diagram variables are handled by :class:`~.engine.SimpleRunEngine`
**outside** the generated function; see :class:`RunStepExchange` field docs.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any, AbstractSet
from uuid import UUID


@dataclass
class RunStepExchange:
    """Data passed into generated ``run_equations(exchange)`` for one logical step.

    * ``workspace`` — same mapping as :attr:`~synarius_core.dataflow_sim.context.SimulationContext.scalar_workspace`
      (``UUID`` scalars; FMU outputs may use ``(UUID, pin_name)`` keys per :func:`~.compiler.scalar_ws_read`).
    * ``stimmed`` — variable instance ids that already received a stimulation value this step; generated
      code skips overwriting those slots (matches :func:`~synarius_core.dataflow_sim.scalar_equations.apply_scalar_equations_topo`).
    * ``fmu_step`` — optional callback for FMU diagram nodes (same role as the engine's ``step_fmu`` hook).
    * ``simulation_context`` — optional :class:`~synarius_core.dataflow_sim.context.SimulationContext` for plugins.
    """

    workspace: MutableMapping[object, float]
    stimmed: AbstractSet[UUID]
    time_s: float = 0.0
    dt_s: float = 0.02
    fmu_step: Callable[[UUID], None] | None = None
    simulation_context: Any | None = None
