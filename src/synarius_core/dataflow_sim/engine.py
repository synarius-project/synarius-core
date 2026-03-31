"""Step-wise evaluation of a compiled dataflow (variables, operators, optional FMU).

FMU diagram nodes (non-empty ``fmu.path``) are stepped when a plugin registers ``runtime:fmu``
(see bundled ``Plugins/FmuRuntime`` + optional ``synarius-core[fmu]``). Otherwise their workspace
scalar stays at zero like other generic elementaries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from synarius_core.model import BasicOperator, BasicOperatorType, ElementaryInstance, Model, Variable

from synarius_core.plugins.registry import PluginRegistry, run_plugin_compile_passes

from .compiler import CompiledDataflow, DataflowCompilePass, elementary_has_fmu_path
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
    Fixed-step loop: time advance, stimulation, topological evaluation of variables and
    :class:`~synarius_core.model.BasicOperator` nodes, and optional FMU stepping.

    **Orchestration**

    1. ``init`` — compile ``DataflowCompilePass``, plugin compile passes, fill scalar workspace,
       then call ``runtime:fmu`` plugin ``init_fmu(ctx)`` if present.
    2. ``step`` — increment ``ctx.time_s``, apply stimuli, walk ``topo_order``; for each FMU
       diagram node (non-empty ``fmu.path``) call ``step_fmu(ctx, node_id)``; otherwise evaluate
       variables/operators as before. Finally write workspace values back to :class:`Variable`
       instances.
    3. ``reset`` — restore workspace snapshot and ``reset_fmu(ctx)`` when the plugin provides it.

    If the plugin only implements ``step(ctx)`` (legacy shape) and not ``step_fmu``, that single
    ``step`` is invoked once after the topological pass (FMU ordering is then the plugin's
    responsibility).
    """

    name: str = "simple_scalar"

    def __init__(
        self,
        model: Model,
        *,
        dt_s: float = 0.02,
        plugin_registry: PluginRegistry | None = None,
    ) -> None:
        self._model = model
        self._dt_s = float(dt_s)
        self._plugin_registry = plugin_registry
        self._ctx = SimulationContext(model=model)
        self._compile_pass = DataflowCompilePass()
        self._compiled: CompiledDataflow | None = None
        self._workspace: dict[UUID, float] = {}
        self._initial_snapshot: dict[UUID, float] = {}
        # True after ``init_fmu`` ran successfully; ``shutdown_fmu`` only then (avoids spurious
        # shutdown when the registry loads the plugin for the first time).
        self._runtime_fmu_session: bool = False

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
        # Tear down a previous ``init_fmu`` session before rebuilding (e.g. second init, cycle).
        self._shutdown_runtime_fmu_plugin()
        self._compile_pass.run(self._ctx)
        if self._plugin_registry is not None:
            run_plugin_compile_passes(self._ctx, self._plugin_registry)
        self._compiled = self._ctx.artifacts.get("dataflow")
        self._ctx.time_s = 0.0
        self._workspace.clear()
        self._initial_snapshot.clear()
        self._ctx.options["communication_step_size"] = self._dt_s
        self._ctx.scalar_workspace = self._workspace
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
            elif isinstance(node, ElementaryInstance):
                # Operators and non-FMU elementaries: scalar slot (FMU outputs are filled by step_fmu).
                self._workspace[uid] = 0.0
                self._initial_snapshot[uid] = 0.0

        if self._plugin_registry is not None:
            lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
            if lp is not None:
                fn = getattr(lp.instance, "init_fmu", None)
                if callable(fn):
                    fn(self._ctx)
                    self._runtime_fmu_session = True

    def reset(self) -> None:
        """Stop semantics: time zero and workspace back to snapshot from last ``init``."""
        self._ctx.time_s = 0.0
        self._workspace = dict(self._initial_snapshot)
        self._ctx.scalar_workspace = self._workspace
        self._ctx.options["communication_step_size"] = self._dt_s
        if self._plugin_registry is not None and self._compiled is not None:
            lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
            if lp is not None:
                rn = getattr(lp.instance, "reset_fmu", None)
                if callable(rn):
                    rn(self._ctx)
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
        self._ctx.options["communication_step_size"] = self._dt_s
        self._ctx.scalar_workspace = self._workspace

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
            if isinstance(node, ElementaryInstance) and elementary_has_fmu_path(node):
                self._invoke_runtime_fmu_step(uid)
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

        self._maybe_invoke_runtime_fmu_step_legacy()
        self._apply_workspace_to_variables()

    def _maybe_invoke_runtime_fmu_step_legacy(self) -> None:
        """If the plugin has no ``step_fmu``, call ``step(ctx)`` once (whole-step FMU hook)."""
        if self._plugin_registry is None:
            return
        lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
        if lp is None:
            return
        if callable(getattr(lp.instance, "step_fmu", None)):
            return
        fn = getattr(lp.instance, "step", None)
        if callable(fn):
            fn(self._ctx)

    def close(self) -> None:
        """Terminate FMUs and delete extract dirs; safe to call when discarding the engine."""
        self._shutdown_runtime_fmu_plugin()

    def _shutdown_runtime_fmu_plugin(self) -> None:
        if not self._runtime_fmu_session or self._plugin_registry is None:
            return
        lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
        if lp is None:
            self._runtime_fmu_session = False
            return
        fn = getattr(lp.instance, "shutdown_fmu", None)
        if callable(fn):
            fn(self._ctx)
        self._runtime_fmu_session = False

    def _invoke_runtime_fmu_step(self, uid: UUID) -> None:
        if self._plugin_registry is None:
            return
        lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
        if lp is None:
            return
        fn = getattr(lp.instance, "step_fmu", None)
        if callable(fn):
            fn(self._ctx, uid)

    def _apply_workspace_to_variables(self) -> None:
        if self._compiled is None:
            return
        for uid, node in self._compiled.node_by_id.items():
            if isinstance(node, Variable) and uid in self._workspace:
                node.value = self._workspace[uid]
