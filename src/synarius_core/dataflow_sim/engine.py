"""Step-wise evaluation of a compiled dataflow (no FMU)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from synarius_core.model import BasicOperator, BasicOperatorType, Model, Variable

from .compiler import CompiledDataflow, DataflowCompilePass
from .context import SimulationContext
from .stimulation import stimulation_value

if TYPE_CHECKING:
    pass


def _eval_op(op: BasicOperator, a: float, b: float) -> float:
    if op.operation == BasicOperatorType.PLUS:
        return a + b
    if op.operation == BasicOperatorType.MINUS:
        return a - b
    if op.operation == BasicOperatorType.MULTIPLY:
        return a * b
    if op.operation == BasicOperatorType.DIVIDE:
        if abs(b) < 1e-15:
            return float("nan")
        return a / b
    return float("nan")


class SimpleRunEngine:
    """
    Minimal runtime: fixed step, scalar float signals, stimulation, operator evaluation.

    Matches the informative ``RuntimePlugin`` shape (``name``, ``init``, ``step``).
    """

    name: str = "simple_scalar"

    def __init__(self, model: Model, *, dt_s: float = 0.02) -> None:
        self._model = model
        self._dt_s = float(dt_s)
        self._ctx = SimulationContext(model=model)
        self._compile_pass = DataflowCompilePass()
        self._compiled: CompiledDataflow | None = None
        self._workspace: dict[UUID, float] = {}
        self._initial_snapshot: dict[UUID, float] = {}

    @property
    def context(self) -> SimulationContext:
        return self._ctx

    @property
    def dt_s(self) -> float:
        return self._dt_s

    def init(self, ctx: SimulationContext | None = None) -> None:
        """(Re)compile and reset time and workspace from current model variable values."""
        if ctx is not None:
            self._ctx = ctx
        self._compile_pass.run(self._ctx)
        self._compiled = self._ctx.artifacts.get("dataflow")
        self._ctx.time_s = 0.0
        self._workspace.clear()
        self._initial_snapshot.clear()
        if self._compiled is None:
            return
        for uid, node in self._compiled.node_by_id.items():
            if isinstance(node, Variable):
                try:
                    v = float(node.value)
                except (TypeError, ValueError):
                    v = 0.0
                self._workspace[uid] = v
                self._initial_snapshot[uid] = v

    def reset(self) -> None:
        """Stop semantics: time zero and workspace back to snapshot from last ``init``."""
        self._ctx.time_s = 0.0
        self._workspace = dict(self._initial_snapshot)
        self._apply_workspace_to_variables()

    def step(self, ctx: SimulationContext | None = None) -> None:
        """Advance one step: stimulation, then topological propagation."""
        if ctx is not None:
            self._ctx = ctx
        if self._compiled is None:
            return

        self._ctx.time_s += self._dt_s
        t = self._ctx.time_s
        incoming = self._compiled.incoming
        stimmed: set[UUID] = set()

        for uid, node in self._compiled.node_by_id.items():
            if isinstance(node, Variable):
                sv = stimulation_value(node, t)
                if sv is not None:
                    self._workspace[uid] = float(sv)
                    stimmed.add(uid)

        for uid in self._compiled.topo_order:
            node = self._compiled.node_by_id.get(uid)
            if node is None:
                continue
            if isinstance(node, BasicOperator):
                pins = incoming.get(uid, {})
                a = self._workspace.get(pins.get("in1"), 0.0)
                b = self._workspace.get(pins.get("in2"), 0.0)
                self._workspace[uid] = _eval_op(node, a, b)
            elif isinstance(node, Variable):
                if uid in stimmed:
                    continue
                pins = incoming.get(uid, {})
                if "in" in pins:
                    src = pins["in"]
                    self._workspace[uid] = self._workspace.get(src, 0.0)

        self._apply_workspace_to_variables()

    def _apply_workspace_to_variables(self) -> None:
        if self._compiled is None:
            return
        for uid, node in self._compiled.node_by_id.items():
            if isinstance(node, Variable) and uid in self._workspace:
                node.value = self._workspace[uid]
