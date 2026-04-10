"""Smoke: SimpleRunEngine loads unrolled run_equations in init."""

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim import SimpleRunEngine  # noqa: E402
from synarius_core.model import (  # noqa: E402
    BasicOperator,
    BasicOperatorType,
    Connector,
    Model,
    Variable,
)


class EngineUnrolledRuntimeTest(unittest.TestCase):
    def test_run_equations_loaded_when_acyclic(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        model.attach(a, parent=model.root, reserve_existing=False, remap_ids=False)
        assert a.id
        eng = SimpleRunEngine(model, dt_s=0.01)
        eng.init()
        self.assertIsNotNone(eng.context.artifacts.get("dataflow"))
        self.assertIsNotNone(eng._run_equations)

    def test_run_equations_none_when_cycle(self) -> None:
        model = Model.new("main")
        x = Variable(name="x", type_key="t", value=0.0)
        y = Variable(name="y", type_key="t", value=0.0)
        model.attach(x, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(y, parent=model.root, reserve_existing=False, remap_ids=False)
        assert x.id and y.id
        model.attach(
            Connector(
                name="a",
                source_instance_id=x.id,
                source_pin="out",
                target_instance_id=y.id,
                target_pin="in",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        model.attach(
            Connector(
                name="b",
                source_instance_id=y.id,
                source_pin="out",
                target_instance_id=x.id,
                target_pin="in",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        eng = SimpleRunEngine(model)
        eng.init()
        self.assertIsNone(eng.context.artifacts.get("dataflow"))
        self.assertIsNone(eng._run_equations)

    def test_step_runs_unrolled_add(self) -> None:
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
        eng = SimpleRunEngine(model, dt_s=0.1)
        eng.init()
        eng.step()
        ws = eng.context.scalar_workspace
        self.assertIsNotNone(ws)
        self.assertAlmostEqual(float(ws[op.id]), 3.0, places=5)


if __name__ == "__main__":
    unittest.main()
