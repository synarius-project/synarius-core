"""Parity: apply_scalar_equations_topo vs. generated unrolled run_equations."""

import sys
import unittest
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
    for uid, node in compiled.node_by_id.items():
        if isinstance(node, Variable):
            try:
                v = float(node.value)
            except (TypeError, ValueError):
                v = 0.0
            ws[uid] = v
        elif isinstance(node, ElementaryInstance):
            ws[uid] = 0.0
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


if __name__ == "__main__":
    unittest.main()
