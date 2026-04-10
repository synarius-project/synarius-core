import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim.codegen_kernel import generate_fmfl_document  # noqa: E402
from synarius_core.dataflow_sim.python_step_emit import generate_unrolled_python_step_document  # noqa: E402
from synarius_core.dataflow_sim import (  # noqa: E402
    DataflowCompilePass,
    SimulationContext,
)
from synarius_core.model import (  # noqa: E402
    BasicOperator,
    BasicOperatorType,
    Connector,
    Model,
    Variable,
)


class CodegenKernelTest(unittest.TestCase):
    def test_fmfl_and_python_contain_chain_equations(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        b = Variable(name="b", type_key="t", value=0.0)
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
        fmfl = generate_fmfl_document(compiled, dt_s=0.02, diagnostics=tuple(ctx.diagnostics))
        py = generate_unrolled_python_step_document(compiled, dt_s=0.02, diagnostics=tuple(ctx.diagnostics))
        self.assertIn("v0.2 execution view", fmfl)
        self.assertIn("equations:", fmfl)
        self.assertIn("op = a + b", fmfl)
        self.assertIn("def run_equations", py)
        self.assertIn("RunStepExchange", py)
        self.assertIn("ws[", py)
        self.assertIn(" + ", py)

    def test_cycle_resolves_with_delayed_feedback_codegen(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=0.0)
        b = Variable(name="b", type_key="t", value=0.0)
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
        fmfl = generate_fmfl_document(compiled, dt_s=0.1, diagnostics=tuple(ctx.diagnostics))
        py = generate_unrolled_python_step_document(compiled, dt_s=0.1, diagnostics=tuple(ctx.diagnostics))
        self.assertIn("equations:", fmfl)
        self.assertIn("prev(", fmfl)
        self.assertIn("def run_equations", py)
        self.assertIn("workspace_previous", py)
        self.assertNotIn("raise RuntimeError('invalid dataflow (cycle)')", py)


if __name__ == "__main__":
    unittest.main()
