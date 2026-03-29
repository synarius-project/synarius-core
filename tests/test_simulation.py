import sys
import unittest
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.model import (  # noqa: E402
    BasicOperator,
    BasicOperatorType,
    Connector,
    Model,
    Variable,
)
from synarius_core.dataflow_sim import (  # noqa: E402
    DataflowCompilePass,
    SimpleRunEngine,
    SimulationContext,
)


class SimulationCompileTest(unittest.TestCase):
    def test_topo_add_chain(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        b = Variable(name="b", type_key="t", value=0.0)
        op = BasicOperator(name="op", type_key="std.Add", operation=BasicOperatorType.PLUS)
        model.attach(a, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(b, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(op, parent=model.root, reserve_existing=False, remap_ids=False)
        assert a.id and b.id and op.id
        c1 = Connector(
            name="e1",
            source_instance_id=a.id,
            source_pin="out",
            target_instance_id=op.id,
            target_pin="in1",
        )
        c2 = Connector(
            name="e2",
            source_instance_id=b.id,
            source_pin="out",
            target_instance_id=op.id,
            target_pin="in2",
        )
        model.attach(c1, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(c2, parent=model.root, reserve_existing=False, remap_ids=False)

        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        g = ctx.artifacts.get("dataflow")
        self.assertIsNotNone(g)
        assert g is not None
        order = g.topo_order
        ia = order.index(a.id)
        ib = order.index(b.id)
        io = order.index(op.id)
        self.assertLess(ia, io)
        self.assertLess(ib, io)


class SimulationEngineTest(unittest.TestCase):
    def test_ramp_stim_and_add(self) -> None:
        model = Model.new("main")
        src = Variable(name="src", type_key="t", value=0.0)
        cst = Variable(name="cst", type_key="t", value=2.0)
        out = Variable(name="out", type_key="t", value=0.0)
        op = BasicOperator(name="op", type_key="std.Add", operation=BasicOperatorType.PLUS)
        for n in (src, cst, op, out):
            model.attach(n, parent=model.root, reserve_existing=False, remap_ids=False)
        assert src.id and cst.id and op.id and out.id
        src.set("stim_kind", "ramp")
        src.set("stim_p0", 0.0)
        src.set("stim_p1", 10.0)

        e1 = Connector(
            name="c1",
            source_instance_id=src.id,
            source_pin="out",
            target_instance_id=op.id,
            target_pin="in1",
        )
        e2 = Connector(
            name="c2",
            source_instance_id=cst.id,
            source_pin="out",
            target_instance_id=op.id,
            target_pin="in2",
        )
        e3 = Connector(
            name="c3",
            source_instance_id=op.id,
            source_pin="out",
            target_instance_id=out.id,
            target_pin="in",
        )
        for e in (e1, e2, e3):
            model.attach(e, parent=model.root, reserve_existing=False, remap_ids=False)

        eng = SimpleRunEngine(model, dt_s=0.1)
        eng.init()
        eng.step()
        # t=0.1, ramp = 0 + 10*0.1 = 1, plus 2 -> 3
        self.assertAlmostEqual(out.value, 3.0, places=5)

    def test_cycle_diagnostic(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=0.0)
        b = Variable(name="b", type_key="t", value=0.0)
        model.attach(a, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(b, parent=model.root, reserve_existing=False, remap_ids=False)
        assert a.id and b.id
        e1 = Connector(
            name="x",
            source_instance_id=a.id,
            source_pin="out",
            target_instance_id=b.id,
            target_pin="in",
        )
        e2 = Connector(
            name="y",
            source_instance_id=b.id,
            source_pin="out",
            target_instance_id=a.id,
            target_pin="in",
        )
        model.attach(e1, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(e2, parent=model.root, reserve_existing=False, remap_ids=False)
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        self.assertIsNone(ctx.artifacts.get("dataflow"))
        self.assertTrue(any("cycle" in m.lower() for m in ctx.diagnostics))


if __name__ == "__main__":
    unittest.main()
