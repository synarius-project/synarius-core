import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.model import (  # noqa: E402
    BasicOperator,
    BasicOperatorType,
    Connector,
    Model,
    Variable,
    elementary_fmu_block,
)
from synarius_core.dataflow_sim import (  # noqa: E402
    CompiledFmuDiagram,
    DataflowCompilePass,
    SimpleRunEngine,
    SimulationContext,
)
from synarius_core.plugins.registry import PluginRegistry  # noqa: E402


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

    def test_topo_includes_fmu_elementary_between_variable_and_operator(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        fmu = elementary_fmu_block(
            name="f",
            type_key="test.Fmu",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            fmu_ports=[
                {"name": "u", "causality": "input", "variability": "continuous", "data_type": "float"},
                {"name": "y", "causality": "output", "variability": "continuous", "data_type": "float"},
            ],
        )
        op = BasicOperator(name="op", type_key="std.Add", operation=BasicOperatorType.PLUS)
        c = Variable(name="c", type_key="t", value=2.0)
        for n in (a, fmu, op, c):
            model.attach(n, parent=model.root, reserve_existing=False, remap_ids=False)
        assert a.id and fmu.id and op.id and c.id
        for conn in (
            Connector(
                name="e1",
                source_instance_id=a.id,
                source_pin="out",
                target_instance_id=fmu.id,
                target_pin="u",
            ),
            Connector(
                name="e2",
                source_instance_id=fmu.id,
                source_pin="y",
                target_instance_id=op.id,
                target_pin="in1",
            ),
            Connector(
                name="e3",
                source_instance_id=c.id,
                source_pin="out",
                target_instance_id=op.id,
                target_pin="in2",
            ),
        ):
            model.attach(conn, parent=model.root, reserve_existing=False, remap_ids=False)

        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        g = ctx.artifacts.get("dataflow")
        self.assertIsNotNone(g)
        assert g is not None
        order = g.topo_order
        ia = order.index(a.id)
        i_fmu = order.index(fmu.id)
        ic = order.index(c.id)
        iop = order.index(op.id)
        self.assertLess(ia, i_fmu)
        self.assertLess(i_fmu, iop)
        self.assertLess(ic, iop)

    def test_compile_emits_note_for_generic_elementary_blocks(self) -> None:
        model = Model.new("main")
        fmu = elementary_fmu_block(
            name="solo",
            type_key="test.Fmu",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
        )
        model.attach(fmu, parent=model.root, reserve_existing=False, remap_ids=False)
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        self.assertIsNotNone(ctx.artifacts.get("dataflow"))
        self.assertTrue(any("generic elementary" in m.lower() for m in ctx.diagnostics))

    def test_fmu_diagram_artifact_lists_fmu_nodes(self) -> None:
        model = Model.new("main")
        fmu = elementary_fmu_block(
            name="f",
            type_key="test.Fmu",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
        )
        model.attach(fmu, parent=model.root, reserve_existing=False, remap_ids=False)
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        art = ctx.artifacts.get("fmu_diagram")
        self.assertIsInstance(art, CompiledFmuDiagram)
        assert art is not None and fmu.id is not None
        self.assertEqual(art.fmu_node_ids, frozenset({fmu.id}))

    def test_non_fmu_graph_has_empty_fmu_diagram(self) -> None:
        model = Model.new("main")
        a = Variable(name="a", type_key="t", value=1.0)
        model.attach(a, parent=model.root, reserve_existing=False, remap_ids=False)
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        art = ctx.artifacts.get("fmu_diagram")
        self.assertIsInstance(art, CompiledFmuDiagram)
        assert art is not None
        self.assertEqual(art.fmu_node_ids, frozenset())

    def test_fmu_unconnected_pins_emit_diagnostics(self) -> None:
        model = Model.new("main")
        fmu = elementary_fmu_block(
            name="f",
            type_key="test.Fmu",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            fmu_ports=[
                {"name": "u", "causality": "input", "variability": "continuous", "data_type": "float"},
                {"name": "y", "causality": "output", "variability": "continuous", "data_type": "float"},
            ],
        )
        model.attach(fmu, parent=model.root, reserve_existing=False, remap_ids=False)
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        self.assertTrue(any("input pin 'u'" in m for m in ctx.diagnostics))
        self.assertTrue(any("output pin 'y'" in m for m in ctx.diagnostics))

    def test_fmu_parameter_pin_skips_unconnected_input_warning(self) -> None:
        model = Model.new("main")
        fmu = elementary_fmu_block(
            name="f",
            type_key="test.Fmu",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            fmu_ports=[{"name": "k", "causality": "input", "data_type": "float"}],
            fmu_variables=[{"name": "k", "causality": "parameter", "value_reference": 0}],
        )
        model.attach(fmu, parent=model.root, reserve_existing=False, remap_ids=False)
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        self.assertFalse(any("input pin 'k'" in m for m in ctx.diagnostics))

    def test_fmu_causality_target_mismatch(self) -> None:
        model = Model.new("main")
        src = Variable(name="a", type_key="t", value=1.0)
        fmu = elementary_fmu_block(
            name="f",
            type_key="test.Fmu",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            fmu_ports=[{"name": "y", "causality": "output", "data_type": "float"}],
            fmu_variables=[{"name": "y", "causality": "output", "value_reference": 1}],
        )
        model.attach(src, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(fmu, parent=model.root, reserve_existing=False, remap_ids=False)
        assert src.id and fmu.id
        model.attach(
            Connector(
                name="e",
                source_instance_id=src.id,
                source_pin="out",
                target_instance_id=fmu.id,
                target_pin="y",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        self.assertTrue(any("declared output" in m and "target" in m for m in ctx.diagnostics))

    def test_fmu_type_mismatch_on_edge(self) -> None:
        model = Model.new("main")
        src = Variable(name="a", type_key="t", value=1.0)
        fmu = elementary_fmu_block(
            name="f",
            type_key="test.Fmu",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            fmu_ports=[
                {"name": "u", "causality": "input", "data_type": "string"},
                {"name": "y", "causality": "output", "data_type": "float"},
            ],
        )
        sink = BasicOperator(name="op", type_key="std.Add", operation=BasicOperatorType.PLUS)
        b = Variable(name="b", type_key="t", value=0.0)
        c = Variable(name="c", type_key="t", value=0.0)
        for n in (src, fmu, sink, b, c):
            model.attach(n, parent=model.root, reserve_existing=False, remap_ids=False)
        assert src.id and fmu.id and sink.id and b.id and c.id
        model.attach(
            Connector(
                name="e0",
                source_instance_id=src.id,
                source_pin="out",
                target_instance_id=fmu.id,
                target_pin="u",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        model.attach(
            Connector(
                name="e1",
                source_instance_id=fmu.id,
                source_pin="y",
                target_instance_id=sink.id,
                target_pin="in1",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        model.attach(
            Connector(
                name="e2",
                source_instance_id=b.id,
                source_pin="out",
                target_instance_id=sink.id,
                target_pin="in2",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        model.attach(
            Connector(
                name="e3",
                source_instance_id=sink.id,
                source_pin="out",
                target_instance_id=c.id,
                target_pin="in",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )
        ctx = SimulationContext(model=model)
        DataflowCompilePass().run(ctx)
        self.assertTrue(any("type mismatch" in m for m in ctx.diagnostics))


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
        self.assertIsNone(ctx.artifacts.get("fmu_diagram"))
        self.assertTrue(any("cycle" in m.lower() for m in ctx.diagnostics))

    def test_init_shutdowns_runtime_fmu_before_each_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plug_root = Path(td) / "Plugins" / "track"
            plug_root.mkdir(parents=True)
            (plug_root / "pluginDescription.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<PluginDescription>
  <Name>TrackFmuShutdown</Name>
  <Version>0.1</Version>
  <Module>track</Module>
  <Class>TrackFmu</Class>
  <Capabilities>
    <Capability>runtime:fmu</Capability>
  </Capabilities>
</PluginDescription>
""",
                encoding="utf-8",
            )
            (plug_root / "track.py").write_text(
                """class TrackFmu:
    name = "track"

    def __init__(self) -> None:
        self.shutdowns = 0

    def shutdown_fmu(self, ctx):
        self.shutdowns += 1

    def init_fmu(self, ctx):
        pass

    def step_fmu(self, ctx, uid):
        pass
""",
                encoding="utf-8",
            )
            reg = PluginRegistry(
                extra_plugin_containers=[Path(td) / "Plugins"],
                scan_builtin_plugin_directories=False,
            )
            lp = reg.plugin_for_capability("runtime:fmu")
            self.assertIsNotNone(lp)
            assert lp is not None
            impl = lp.instance
            eng = SimpleRunEngine(Model.new("main"), plugin_registry=reg)
            eng.init()
            self.assertEqual(impl.shutdowns, 0)
            eng.init()
            self.assertEqual(impl.shutdowns, 1)

    def test_legacy_runtime_step_called_when_no_step_fmu(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plug_root = Path(td) / "Plugins" / "legacy"
            plug_root.mkdir(parents=True)
            (plug_root / "pluginDescription.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<PluginDescription>
  <Name>LegacyStep</Name>
  <Version>0.1</Version>
  <Module>legacy</Module>
  <Class>LegacyRuntime</Class>
  <Capabilities>
    <Capability>runtime:fmu</Capability>
  </Capabilities>
</PluginDescription>
""",
                encoding="utf-8",
            )
            (plug_root / "legacy.py").write_text(
                """class LegacyRuntime:
    name = "legacy"

    def __init__(self) -> None:
        self.steps = 0

    def shutdown_fmu(self, ctx):
        pass

    def init_fmu(self, ctx):
        pass

    def step(self, ctx):
        self.steps += 1
""",
                encoding="utf-8",
            )
            reg = PluginRegistry(
                extra_plugin_containers=[Path(td) / "Plugins"],
                scan_builtin_plugin_directories=False,
            )
            model = Model.new("main")
            v = Variable(name="v", type_key="t", value=1.0)
            model.attach(v, parent=model.root, reserve_existing=False, remap_ids=False)
            lp = reg.plugin_for_capability("runtime:fmu")
            assert lp is not None
            impl = lp.instance
            eng = SimpleRunEngine(model, plugin_registry=reg)
            eng.init()
            eng.step()
            self.assertEqual(impl.steps, 1)


if __name__ == "__main__":
    unittest.main()
