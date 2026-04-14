"""Step-wise evaluation of a compiled dataflow (variables, operators, optional FMU).

FMU diagram nodes (non-empty ``fmu.path``) are stepped when a plugin registers ``runtime:fmu``
(see bundled ``synarius_core/plugins/FmuRuntime`` + optional ``synarius-core[fmu]``). Otherwise their workspace
scalar stays at zero like other generic elementaries.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from synarius_core.model import ElementaryInstance, Model, Variable

from synarius_core.plugins.element_types import SimContext
from synarius_core.plugins.registry import PluginRegistry, run_plugin_compile_passes

try:
    from .compiler import CompiledDataflow, DataflowCompilePass
except ImportError:
    raise
from .context import SimulationContext
from .python_step_emit import generate_unrolled_python_step_document
from .step_exchange import RunStepExchange
from .stimulation import stimulation_value
from .unrolled_loader import load_run_equations_from_source

if TYPE_CHECKING:
    pass


class SimpleRunEngine:
    """
    Fixed-step loop: time advance, stimulation, **equations phase** via generated
    ``run_equations(exchange)`` (same source as Studio's unrolled Python tab), optional FMU hooks.

    **Orchestration**

    1. ``init`` — compile ``DataflowCompilePass``, plugin compile passes, fill scalar workspace,
       compile/load unrolled ``run_equations`` from :func:`~python_step_emit.generate_unrolled_python_step_document`,
       then call ``runtime:fmu`` plugin ``init_fmu(ctx)`` if present.
    2. ``step`` — increment ``ctx.time_s``, apply stimuli, call ``run_equations`` with
       :class:`~step_exchange.RunStepExchange` (workspace, ``stimmed``, ``fmu_step``, …), then
       optional legacy FMU ``step(ctx)``. Finally write workspace values back to :class:`Variable`
       instances.
    3. ``reset`` — restore workspace snapshot and ``reset_fmu(ctx)`` when the plugin provides it.

    If the plugin only implements ``step(ctx)`` (legacy shape) and not ``step_fmu``, that single
    ``step`` is invoked once after the equations pass (FMU ordering is then the plugin's
    responsibility).
    """

    name: str = "simple_scalar"

    def __init__(
        self,
        model: Model,
        *,
        dt_s: float = 0.02,
        plugin_registry: PluginRegistry | None = None,
        model_directory: Path | str | None = None,
    ) -> None:
        self._model = model
        self._dt_s = float(dt_s)
        self._plugin_registry = plugin_registry
        self._model_directory: Path | None = None
        if model_directory is not None and str(model_directory).strip() != "":
            _p = Path(model_directory).expanduser()
            try:
                self._model_directory = _p.resolve()
            except OSError:
                self._model_directory = _p
        self._ctx = SimulationContext(model=model)
        self._compile_pass = DataflowCompilePass()
        self._compiled: CompiledDataflow | None = None
        self._workspace: dict[UUID, float] = {}
        self._initial_snapshot: dict[UUID, float] = {}
        # True after ``init_fmu`` ran successfully; ``shutdown_fmu`` only then (avoids spurious
        # shutdown when the registry loads the plugin for the first time).
        self._runtime_fmu_session: bool = False
        self._fmu_sim_rt: Any = None
        self._run_equations: Callable[[RunStepExchange], None] | None = None

    @property
    def context(self) -> SimulationContext:
        return self._ctx

    @property
    def dt_s(self) -> float:
        return self._dt_s

    def _plugin_sim_context(self) -> SimContext:
        """Adapt engine :class:`SimulationContext` to :class:`~synarius_core.plugins.element_types.SimContext` for ``SimulationRuntimePlugin``.

        Uses the **same** ``artifacts`` / ``scalar_workspace`` / ``options`` / ``diagnostics``
        objects as the live :class:`SimulationContext` so FMU runtime writes stay visible to the engine.
        """
        c = self._ctx
        sw = c.scalar_workspace
        if sw is None:
            sw = {}
        return SimContext(
            artifacts=c.artifacts,
            scalar_workspace=sw,
            options=c.options,
            diagnostics=c.diagnostics,
            time_s=c.time_s,
        )

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
        self._sync_ctx_options()
        self._ctx.scalar_workspace = self._workspace
        self._run_equations = None
        if self._compiled is None:
            return
        wk_map = self._compiled.workspace_key_uid or {}
        for uid, node in self._compiled.node_by_id.items():
            sk = wk_map.get(uid, uid)
            if isinstance(node, Variable):
                try:
                    v = float(node.value)
                except (TypeError, ValueError):
                    v = 0.0
                self._workspace[sk] = v
                self._initial_snapshot[sk] = v
            elif isinstance(node, ElementaryInstance):
                # Operators and non-FMU elementaries: scalar slot (FMU outputs are filled by step_fmu).
                self._workspace.setdefault(sk, 0.0)
                self._initial_snapshot.setdefault(sk, 0.0)

        src = generate_unrolled_python_step_document(
            self._compiled,
            dt_s=self._dt_s,
            diagnostics=tuple(self._ctx.diagnostics),
        )
        self._run_equations = load_run_equations_from_source(src)

        if self._plugin_registry is not None:
            lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
            if lp is not None:
                self._fmu_sim_rt = None
                sr_fn = getattr(lp.instance, "simulation_runtime", None)
                if callable(sr_fn):
                    try:
                        self._fmu_sim_rt = sr_fn()
                    except Exception:
                        self._fmu_sim_rt = None
                if self._fmu_sim_rt is not None:
                    ri = getattr(self._fmu_sim_rt, "runtime_init", None)
                    if callable(ri):
                        ri(self._plugin_sim_context())
                        self._runtime_fmu_session = True
                else:
                    fn = getattr(lp.instance, "init_fmu", None)
                    if callable(fn):
                        fn(self._ctx)
                        self._runtime_fmu_session = True

    def _sync_ctx_options(self) -> None:
        self._ctx.options["communication_step_size"] = self._dt_s
        if self._model_directory is not None:
            self._ctx.options["model_directory"] = str(self._model_directory)
        else:
            self._ctx.options.pop("model_directory", None)

    def reset(self) -> None:
        """Stop semantics: time zero and workspace back to snapshot from last ``init``."""
        self._ctx.time_s = 0.0
        self._workspace = dict(self._initial_snapshot)
        self._ctx.scalar_workspace = self._workspace
        self._sync_ctx_options()
        if self._plugin_registry is not None and self._compiled is not None:
            lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
            if lp is not None:
                if self._fmu_sim_rt is not None:
                    rr = getattr(self._fmu_sim_rt, "runtime_reset", None)
                    if callable(rr):
                        rr(self._plugin_sim_context())
                else:
                    rn = getattr(lp.instance, "reset_fmu", None)
                    if callable(rn):
                        rn(self._ctx)
        self._apply_workspace_to_variables()

    def step(self, ctx: SimulationContext | None = None) -> None:
        """Advance one step: stimulation, then topological propagation."""
        if ctx is not None:
            self._ctx = ctx
        if self._compiled is None or self._run_equations is None:
            return

        # Snapshot before this step's stimulation (committed end of previous step) for delayed feedback.
        workspace_previous = dict(self._workspace) if self._compiled.feedback_edges else None

        self._ctx.time_s += self._dt_s
        t = self._ctx.time_s
        stimmed: set[UUID] = set()
        self._sync_ctx_options()
        self._ctx.scalar_workspace = self._workspace

        wk_map = self._compiled.workspace_key_uid or {}
        for uid, node in self._compiled.node_by_id.items():
            if isinstance(node, Variable):
                sv = stimulation_value(node, t)
                if sv is not None:
                    sk = wk_map.get(uid, uid)
                    self._workspace[sk] = float(sv)
                    stimmed.add(uid)

        exchange = RunStepExchange(
            workspace=self._workspace,
            stimmed=stimmed,
            time_s=self._ctx.time_s,
            dt_s=self._dt_s,
            workspace_previous=workspace_previous,
            fmu_step=self._invoke_runtime_fmu_step,
            simulation_context=self._ctx,
        )
        self._run_equations(exchange)

        self._maybe_invoke_runtime_fmu_step_legacy()
        self._apply_workspace_to_variables()

    def _maybe_invoke_runtime_fmu_step_legacy(self) -> None:
        """If the plugin has no ``step_fmu``, call ``step(ctx)`` once (whole-step FMU hook)."""
        if self._plugin_registry is None:
            return
        lp = self._plugin_registry.plugin_for_capability("runtime:fmu")
        if lp is None:
            return
        if self._fmu_sim_rt is not None:
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
            self._fmu_sim_rt = None
            return
        if self._fmu_sim_rt is not None:
            rs = getattr(self._fmu_sim_rt, "runtime_shutdown", None)
            if callable(rs):
                rs(self._plugin_sim_context())
            self._fmu_sim_rt = None
        else:
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
        if self._fmu_sim_rt is not None:
            st = getattr(self._fmu_sim_rt, "runtime_step", None)
            if callable(st):
                st(self._plugin_sim_context(), uid)
            return
        fn = getattr(lp.instance, "step_fmu", None)
        if callable(fn):
            fn(self._ctx, uid)

    def _apply_workspace_to_variables(self) -> None:
        if self._compiled is None:
            return
        wk_map = self._compiled.workspace_key_uid or {}
        for uid, node in self._compiled.node_by_id.items():
            if isinstance(node, Variable):
                sk = wk_map.get(uid, uid)
                if sk in self._workspace:
                    node.value = self._workspace[sk]
