"""Parity: apply_scalar_equations_topo vs. generated unrolled run_equations."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim import (  # noqa: E402
    DataflowCompilePass,
    SimulationContext,
    apply_scalar_equations_topo,
)
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


def _initial_workspace(compiled) -> dict:
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

        base = _initial_workspace(compiled)
        w1 = dict(base)
        w2 = dict(base)
        apply_scalar_equations_topo(w1, compiled, stimmed=set(), fmu_step=None)
        run_eq(RunStepExchange(workspace=w2, stimmed=set(), dt_s=0.02))
        self.assertEqual(w1, w2)
        self.assertAlmostEqual(w2[op.id], 3.0, places=5)

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

        base = _initial_workspace(compiled)
        base[b.id] = 42.0  # stimulated value preserved
        w1 = dict(base)
        w2 = dict(base)
        stim = {b.id}
        apply_scalar_equations_topo(w1, compiled, stimmed=stim, fmu_step=None)
        run_eq(RunStepExchange(workspace=w2, stimmed=stim, dt_s=0.02))
        self.assertEqual(w1, w2)
        self.assertEqual(w2[b.id], 42.0)

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

        base = _initial_workspace(compiled)
        committed = dict(base)
        w1 = dict(base)
        w2 = dict(base)
        apply_scalar_equations_topo(
            w1,
            compiled,
            stimmed=set(),
            fmu_step=None,
            workspace_committed=committed,
        )
        run_eq(
            RunStepExchange(
                workspace=w2,
                stimmed=set(),
                dt_s=0.02,
                workspace_previous=committed,
            )
        )
        self.assertEqual(w1, w2)

    def test_scalar_slot_fusion_parity(self) -> None:
        """``workspace_key_uid`` may map two diagram nodes to one scalar slot (fusion)."""
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=3.0)
        b = Variable(name="b", type_key="t", value=3.0)
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
        base_compiled = ctx.artifacts.get("dataflow")
        self.assertIsNotNone(base_compiled)
        assert base_compiled is not None
        wk = dict(base_compiled.workspace_key_uid or {})
        wk[b.id] = a.id
        compiled = replace(base_compiled, workspace_key_uid=wk)

        src = generate_unrolled_python_step_document(compiled, dt_s=0.02, diagnostics=tuple(ctx.diagnostics))
        run_eq = load_run_equations_from_source(src)

        base = _initial_workspace(compiled)
        w1 = dict(base)
        w2 = dict(base)
        apply_scalar_equations_topo(w1, compiled, stimmed=set(), fmu_step=None)
        run_eq(RunStepExchange(workspace=w2, stimmed=set(), dt_s=0.02))
        self.assertEqual(w1, w2)
        self.assertAlmostEqual(w2[a.id], 3.0, places=5)


if __name__ == "__main__":
    unittest.main()
