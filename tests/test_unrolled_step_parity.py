"""Parity: apply_scalar_equations_topo vs. generated unrolled run_equations.

The old path (apply_scalar_equations_topo) uses UUID-keyed workspaces.
The new path (run_equations) uses label-string-keyed workspaces.  Direct dict
equality is therefore not possible; numerical values at matched keys are compared
instead.
"""

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim import (  # noqa: E402
    DataflowCompilePass,
    SimulationContext,
    apply_scalar_equations_topo,
)
from synarius_core.dataflow_sim.equation_walk import label as _node_label  # noqa: E402
from synarius_core.dataflow_sim.python_step_emit import generate_unrolled_python_step_document  # noqa: E402
from synarius_core.dataflow_sim.step_exchange import RunStepExchange  # noqa: E402
from synarius_core.dataflow_sim.unrolled_loader import load_run_equations_from_source  # noqa: E402
from synarius_core.model import (  # noqa: E402
    BasicOperator,
    BasicOperatorType,
    Connector,
    ElementaryInstance,
    Model,
    Variable,
)


def _uuid_workspace(compiled) -> dict:
    """Initial workspace with UUID keys (for apply_scalar_equations_topo)."""
    ws: dict = {}
    wk = compiled.workspace_key_uid or {}
    for uid, node in compiled.node_by_id.items():
        sk = wk.get(uid, uid)
        if isinstance(node, Variable):
            try:
                v = float(node.value)
            except (TypeError, ValueError):
                v = 0.0
            ws[sk] = v
        elif isinstance(node, ElementaryInstance):
            ws.setdefault(sk, 0.0)
    return ws


def _label_workspace(compiled) -> dict:
    """Initial workspace with label-string keys (for run_equations)."""
    ws: dict = {}
    for uid, node in compiled.node_by_id.items():
        lbl = _node_label(node)
        if isinstance(node, Variable):
            try:
                v = float(node.value)
            except (TypeError, ValueError):
                v = 0.0
            ws[lbl] = v
        elif isinstance(node, ElementaryInstance):
            ws.setdefault(lbl, 0.0)
    return ws


class UnrolledParityTest(unittest.TestCase):
    def test_add_chain_matches_apply_scalar(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        b = Variable(name="b", type_key="t", value=2.0)
        op = BasicOperator(name="op", type_key="std.Add", operation=BasicOperatorType.PLUS)
        model.attach(a, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(b, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(op, parent=model.root, reserve_existing=False, remap_ids=False)
        assert a.id and b.id and op.id
        for c in (
            Connector(
                name="e1",
                source_instance_id=a.id,
                source_pin="out",
                target_instance_id=op.id,
                target_pin="in1",
            ),
            Connector(
                name="e2",
                source_instance_id=b.id,
                source_pin="out",
                target_instance_id=op.id,
                target_pin="in2",
            ),
        ):
            model.attach(c, parent=model.root, reserve_existing=False, remap_ids=False)

        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        compiled = ctx.artifacts.get("dataflow")
        self.assertIsNotNone(compiled)

        src = generate_unrolled_python_step_document(compiled, dt_s=0.02, diagnostics=tuple(ctx.diagnostics))
        run_eq = load_run_equations_from_source(src)

        w1 = _uuid_workspace(compiled)
        w2 = _label_workspace(compiled)
        apply_scalar_equations_topo(w1, compiled, stimmed=set(), fmu_step=None)
        run_eq(RunStepExchange(workspace=w2, stimmed=set(), dt_s=0.02))

        self.assertAlmostEqual(float(w1[op.id]), 3.0, places=5)
        self.assertAlmostEqual(float(w2["op"]), 3.0, places=5)
        self.assertAlmostEqual(float(w1[op.id]), float(w2["op"]), places=5)

    def test_stimmed_skips_wire_copy(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        b = Variable(name="b", type_key="t", value=99.0)
        model.attach(a, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(b, parent=model.root, reserve_existing=False, remap_ids=False)
        assert a.id and b.id
        model.attach(
            Connector(
                name="e",
                source_instance_id=a.id,
                source_pin="out",
                target_instance_id=b.id,
                target_pin="in",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        compiled = ctx.artifacts.get("dataflow")
        self.assertIsNotNone(compiled)

        src = generate_unrolled_python_step_document(compiled, dt_s=0.02, diagnostics=tuple(ctx.diagnostics))
        run_eq = load_run_equations_from_source(src)

        w1 = _uuid_workspace(compiled)
        w2 = _label_workspace(compiled)
        w1[b.id] = 42.0
        w2["b"] = 42.0
        stim_uuid = {b.id}
        stim_label = {"b"}
        apply_scalar_equations_topo(w1, compiled, stimmed=stim_uuid, fmu_step=None)
        run_eq(RunStepExchange(workspace=w2, stimmed=stim_label, dt_s=0.02))
        # Stimulation guard: both must keep the stimulated value
        self.assertEqual(float(w1[b.id]), 42.0)
        self.assertEqual(float(w2["b"]), 42.0)

    def test_delayed_feedback_cycle_matches_apply_scalar(self) -> None:
        """Two-variable ring: one feedback edge reads previous-step committed values."""
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        b = Variable(name="b", type_key="t", value=2.0)
        model.attach(a, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(b, parent=model.root, reserve_existing=False, remap_ids=False)
        assert a.id and b.id
        model.attach(
            Connector(
                name="x",
                source_instance_id=a.id,
                source_pin="out",
                target_instance_id=b.id,
                target_pin="in",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        model.attach(
            Connector(
                name="y",
                source_instance_id=b.id,
                source_pin="out",
                target_instance_id=a.id,
                target_pin="in",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        compiled = ctx.artifacts.get("dataflow")
        self.assertIsNotNone(compiled)
        assert compiled is not None
        self.assertTrue(compiled.feedback_edges)

        src = generate_unrolled_python_step_document(compiled, dt_s=0.02, diagnostics=tuple(ctx.diagnostics))
        run_eq = load_run_equations_from_source(src)

        w1 = _uuid_workspace(compiled)
        committed_uuid = dict(w1)
        w2 = _label_workspace(compiled)
        committed_label = dict(w2)
        apply_scalar_equations_topo(
            w1,
            compiled,
            stimmed=set(),
            fmu_step=None,
            workspace_committed=committed_uuid,
        )
        run_eq(
            RunStepExchange(
                workspace=w2,
                stimmed=set(),
                dt_s=0.02,
                workspace_previous=committed_label,
            )
        )
        # Both must produce the same numerical results.
        self.assertAlmostEqual(float(w1[a.id]), float(w2["a"]), places=5)
        self.assertAlmostEqual(float(w1[b.id]), float(w2["b"]), places=5)

    def test_label_workspace_produces_correct_add(self) -> None:
        """run_equations label-keyed workspace yields correct scalar results."""
        model = Model.new("main")
        x = Variable(name="x", type_key="t", value=5.0)
        y = Variable(name="y", type_key="t", value=3.0)
        op = BasicOperator(name="sum", type_key="std.Add", operation=BasicOperatorType.PLUS)
        model.attach(x, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(y, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(op, parent=model.root, reserve_existing=False, remap_ids=False)
        assert x.id and y.id and op.id
        for c in (
            Connector(
                name="e1",
                source_instance_id=x.id,
                source_pin="out",
                target_instance_id=op.id,
                target_pin="in1",
            ),
            Connector(
                name="e2",
                source_instance_id=y.id,
                source_pin="out",
                target_instance_id=op.id,
                target_pin="in2",
            ),
        ):
            model.attach(c, parent=model.root, reserve_existing=False, remap_ids=False)

        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        compiled = ctx.artifacts.get("dataflow")
        self.assertIsNotNone(compiled)

        src = generate_unrolled_python_step_document(compiled, dt_s=0.02, diagnostics=tuple(ctx.diagnostics))
        run_eq = load_run_equations_from_source(src)

        w = _label_workspace(compiled)
        run_eq(RunStepExchange(workspace=w, stimmed=set(), dt_s=0.02))
        self.assertAlmostEqual(float(w["sum"]), 8.0, places=5)


if __name__ == "__main__":
    unittest.main()
