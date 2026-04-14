import sys
from pathlib import Path
import unittest
from uuid import uuid4


# Make `src/` importable when running tests via `python -m unittest`.
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.model import (  # noqa: E402
    BasicOperator,
    BasicOperatorType,
    ComplexInstance,
    Connector,
    DataViewer,
    DuplicateIdError,
    ElementaryInstance,
    IdFactory,
    Model,
    ModelElementType,
    Pin,
    PinDataType,
    PinDirection,
    Signal,
    SignalContainer,
    Size2D,
    elementary_fmu_block,
    VariableDatabase,
    VariableMappingEntry,
    Variable,
)


class IdFactoryTest(unittest.TestCase):
    def test_reserve_contains_unregister(self) -> None:
        factory = IdFactory()
        id_ = uuid4()

        self.assertFalse(factory.contains(id_))
        factory.reserve(id_)
        self.assertTrue(factory.contains(id_))
        factory.unregister(id_)
        self.assertFalse(factory.contains(id_))

    def test_reserve_raises_for_duplicate(self) -> None:
        factory = IdFactory()
        id_ = uuid4()
        factory.reserve(id_)
        with self.assertRaises(DuplicateIdError):
            factory.reserve(id_)


class DataViewerDefaultPositionTest(unittest.TestCase):
    def test_next_dataviewer_default_position_first_and_step(self) -> None:
        model = Model.new("main")
        self.assertEqual(model.next_dataviewer_default_position(), (20.0, 440.0))
        dv = DataViewer(viewer_id=1, position=(0.0, 0.0), size=Size2D(1.0, 1.0))
        model.attach(dv, parent=model.root, reserve_existing=False, remap_ids=False)
        self.assertEqual(model.next_dataviewer_default_position(), (100.0, 440.0))
        dv2 = DataViewer(viewer_id=2, position=(0.0, 0.0), size=Size2D(1.0, 1.0))
        model.attach(dv2, parent=model.root, reserve_existing=False, remap_ids=False)
        self.assertEqual(model.next_dataviewer_default_position(), (180.0, 440.0))


class ModelLifecycleTest(unittest.TestCase):
    def test_main_has_default_output_color_attribute(self) -> None:
        model = Model.new("main")
        self.assertEqual(model.root.get("output_color"), "#ADD8E6")
        self.assertTrue(model.root.attribute_dict.writable("output_color"))

    def test_pin_uses_enum_data_type(self) -> None:
        pin = Pin(name="in", direction=PinDirection.IN, data_type=PinDataType.FLOAT)
        self.assertEqual(pin.data_type, PinDataType.FLOAT)

    def test_attach_assigns_ids_and_registers(self) -> None:
        model = Model.new("root")
        child = Variable(name="v", type_key="var")

        model.attach(child, parent=model.root, reserve_existing=False, remap_ids=False)

        self.assertIsNotNone(child.id)
        self.assertTrue(model.context.id_factory.contains(child.id))  # type: ignore[arg-type]
        self.assertEqual(model.root.get_child(child.hash_name), child)

    def test_delete_unregisters_ids(self) -> None:
        model = Model.new("root")
        child = Variable(name="v", type_key="var")
        model.attach(child, parent=model.root, reserve_existing=False, remap_ids=False)
        child_id = child.id
        self.assertIsNotNone(child_id)

        model.delete(model.root, child_id)  # type: ignore[arg-type]

        self.assertFalse(model.context.id_factory.contains(child_id))  # type: ignore[arg-type]
        self.assertIsNone(model.root.get_child(str(child_id)))

    def test_paste_remaps_ids_by_default(self) -> None:
        model = Model.new("root")
        source = Variable(name="src", type_key="var")
        model.attach(source, parent=model.root, reserve_existing=False, remap_ids=False)

        pasted = model.paste(model.root, source)

        self.assertNotEqual(pasted.id, source.id)
        self.assertIsNotNone(pasted.id)
        self.assertTrue(model.context.id_factory.contains(pasted.id))  # type: ignore[arg-type]

    def test_load_existing_ids_detects_duplicates(self) -> None:
        duplicate_id = uuid4()
        child1 = Variable(name="a", type_key="var", obj_id=duplicate_id)
        child2 = Variable(name="b", type_key="var", obj_id=duplicate_id)
        root = ComplexInstance(name="root", children=[child1, child2], obj_id=uuid4())

        with self.assertRaises(DuplicateIdError):
            Model(root, load_existing_ids=True)

    def test_get_root_and_get_root_model_for_attached_object(self) -> None:
        model = Model.new("root")
        child = Variable(name="v", type_key="var")
        model.attach(child, parent=model.root, reserve_existing=False, remap_ids=False)

        self.assertIs(child.get_root(), model.root)
        self.assertIs(child.get_root_model(), model)

    def test_get_root_model_for_detached_object(self) -> None:
        detached = Variable(name="v", type_key="var")
        self.assertIs(detached.get_root(), detached)
        self.assertIsNone(detached.get_root_model())


class ModelElementTypeTest(unittest.TestCase):
    def test_type_stored_exposed_not_writable(self) -> None:
        v = Variable(name="v", type_key="custom.lib.widget")
        self.assertEqual(v.get("type"), ModelElementType.MODEL_VARIABLE.value)
        self.assertTrue(v.attribute_dict.exposed("type"))
        self.assertFalse(v.attribute_dict.writable("type"))
        self.assertFalse(v.attribute_dict.virtual("type"))
        with self.assertRaises(PermissionError):
            v.set("type", "MODEL.FAKE")

    def test_types_per_class(self) -> None:
        model = Model.new("root")
        self.assertEqual(model.root.get("type"), ModelElementType.MODEL_COMPLEX.value)

        v = Variable(name="v", type_key="x")
        op = BasicOperator(name="o", type_key="y", operation=BasicOperatorType.PLUS)
        el = ElementaryInstance(name="e", type_key="z")
        fmu = elementary_fmu_block(
            name="f",
            type_key="fmu.lib",
            fmu_path="/tmp/x.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            guid="",
            model_identifier="m",
        )
        c = Connector(
            name="c",
            source_instance_id=uuid4(),
            source_pin="a",
            target_instance_id=uuid4(),
            target_pin="b",
        )

        self.assertEqual(v.get("type"), "MODEL.VARIABLE")
        self.assertEqual(op.get("type"), "MODEL.BASIC_OPERATOR")
        self.assertEqual(el.get("type"), "MODEL.ELEMENTARY")
        self.assertEqual(fmu.get("type"), "MODEL.ELEMENTARY")
        self.assertEqual(c.get("type"), "MODEL.CONNECTOR")


class ElementaryFmuBlockTest(unittest.TestCase):
    def test_type_is_elementary(self) -> None:
        f = elementary_fmu_block(
            name="fm1",
            type_key="test",
            fmu_path="/tmp/a.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            guid="g",
            model_identifier="m",
        )
        self.assertEqual(f.get("type"), ModelElementType.MODEL_ELEMENTARY.value)
        self.assertTrue(f.attribute_dict.exposed("type"))
        self.assertFalse(f.attribute_dict.writable("type"))
        self.assertFalse(f.attribute_dict.virtual("type"))
        with self.assertRaises(PermissionError):
            f.set("type", "MODEL.FAKE")

    def test_fmu_namespace_writable(self) -> None:
        f = elementary_fmu_block(
            name="fm1",
            type_key="test",
            fmu_path="/tmp/a.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            guid="g",
            model_identifier="m",
            fmu_generation_tool="tool",
        )
        self.assertTrue(f.attribute_dict.writable("fmu"))

    def test_optional_numeric_attributes(self) -> None:
        f = elementary_fmu_block(
            name="fm1",
            type_key="test",
            fmu_path="/tmp/a.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            guid="",
            model_identifier="",
            step_size_hint=0.01,
            tolerance=1e-6,
            start_time=0.0,
            stop_time=10.0,
        )
        self.assertEqual(f.get("fmu.step_size_hint"), 0.01)
        self.assertEqual(f.get("fmu.tolerance"), 1e-6)
        self.assertEqual(f.get("fmu.start_time"), 0.0)
        self.assertEqual(f.get("fmu.stop_time"), 10.0)

    def test_fmu_variables_catalog(self) -> None:
        catalog = [
            {"name": "h", "value_reference": 0, "causality": "output", "variability": "continuous", "data_type": "Real"},
            {"name": "g", "value_reference": 1, "causality": "parameter", "variability": "fixed", "unit": "m/s2"},
        ]
        f = elementary_fmu_block(
            name="fm1",
            type_key="test",
            fmu_path="/tmp/b.fmu",
            fmi_version="3.0",
            fmu_type="CoSimulation",
            guid="",
            model_identifier="",
            fmu_variables=catalog,
        )
        vars_ = f.get("fmu.variables")
        self.assertEqual(len(vars_), 2)
        self.assertEqual(vars_[0]["name"], "h")
        self.assertEqual(vars_[0]["value_reference"], 0)
        self.assertEqual(vars_[0]["causality"], "output")
        self.assertEqual(vars_[1]["name"], "g")
        self.assertEqual(vars_[1]["unit"], "m/s2")

    def test_fmu_ports_storage(self) -> None:
        ports = [
            {
                "name": "u",
                "value_reference": 1,
                "causality": "input",
                "variability": "continuous",
                "data_type": "float",
                "start_override": 2.5,
            }
        ]
        f = elementary_fmu_block(
            name="fm1",
            type_key="test",
            fmu_path="/tmp/a.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            guid="",
            model_identifier="",
            fmu_ports=ports,
        )
        pmap = f.get("pin")
        self.assertIn("u", pmap)
        self.assertEqual(pmap["u"]["value_reference"], 1)
        self.assertEqual(pmap["u"]["start_override"], 2.5)
        self.assertEqual(f.get("pin.u.direction"), "IN")

    def test_paste_remaps_elementary_fmu_block(self) -> None:
        model = Model.new("root")
        f = elementary_fmu_block(
            name="fm1",
            type_key="test",
            fmu_path="/tmp/a.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            guid="g1",
            model_identifier="mid",
            fmu_description="desc",
            fmu_ports=[{"name": "x", "value_reference": 0, "causality": "output", "variability": "continuous", "data_type": "float"}],
            fmu_extra_meta={"k": 1},
        )
        model.attach(f, parent=model.root, reserve_existing=False, remap_ids=False)
        pasted = model.paste(model.root, f)
        self.assertNotEqual(pasted.id, f.id)
        self.assertEqual(pasted.get("fmu.path"), f.get("fmu.path"))
        self.assertEqual(pasted.get("fmu.description"), "desc")
        self.assertIn("x", pasted.get("pin"))
        self.assertEqual(pasted.get("fmu.extra_meta"), {"k": 1})

    def test_paste_deep_copies_fmu_variables_list(self) -> None:
        model = Model.new("root")
        f = elementary_fmu_block(
            name="fm1",
            type_key="test",
            fmu_path="/tmp/a.fmu",
            fmi_version="2.0",
            fmu_type="CoSimulation",
            guid="g1",
            model_identifier="mid",
            fmu_variables=[{"name": "x", "value_reference": 42}],
        )
        model.attach(f, parent=model.root, reserve_existing=False, remap_ids=False)
        pasted = model.paste(model.root, f)
        vars_orig = f.get("fmu.variables")
        vars_p = pasted.get("fmu.variables")
        self.assertEqual(vars_orig, vars_p)
        vars_orig[0]["value_reference"] = 999
        self.assertEqual(vars_p[0]["value_reference"], 42)


class HierarchicalAttributePathTest(unittest.TestCase):
    def test_variable_pin_paths(self) -> None:
        v = Variable(name="v", type_key="var")
        self.assertEqual(v.get("pin.out.direction"), "OUT")
        v.set("pin.out.y", 0.25)
        self.assertEqual(v.get("pin.out.y"), 0.25)
        pmap = v.get("pin")
        self.assertIsInstance(pmap, dict)
        self.assertIn("out", pmap)

    def test_split_path_escapes(self) -> None:
        from synarius_core.model.attribute_path import join_attribute_path, split_attribute_path

        s = join_attribute_path(["a", "b.c", "d"])
        self.assertEqual(split_attribute_path(s), ["a", "b.c", "d"])


class MeasurementsRecordingTest(unittest.TestCase):
    def test_measurements_tree_created_for_main(self) -> None:
        model = Model.new("main")
        meas = model.get_root_by_type(ModelElementType.MODEL_MEASUREMENTS)
        self.assertIsNotNone(meas)
        stimuli = model.get_root_by_type(ModelElementType.MODEL_STIMULI)
        recording = model.get_root_by_type(ModelElementType.MODEL_RECORDING)
        self.assertIsNotNone(stimuli)
        self.assertIsNotNone(recording)
        self.assertIsInstance(stimuli, SignalContainer)
        self.assertIsInstance(recording, SignalContainer)

    def test_signal_container_series_lifecycle(self) -> None:
        model = Model.new("main")
        recording = model.get_root_by_type(ModelElementType.MODEL_RECORDING)
        self.assertIsInstance(recording, SignalContainer)
        rec = recording

        sig = Signal(name="ch1")
        model.attach(sig, parent=rec, reserve_existing=False, remap_ids=False)  # type: ignore[arg-type]
        t = [0.0, 1.0, 2.0]
        y = [10.0, 11.0, 12.0]
        rec.set_series(sig, t, y)
        t_out, y_out = rec.get_series(sig)
        self.assertEqual(t_out, t)
        self.assertEqual(y_out, y)

        rec.append_samples(sig, [3.0, 4.0], [13.0, 14.0], max_points=10)
        t2, y2 = rec.get_series(sig)
        self.assertEqual(t2, [0.0, 1.0, 2.0, 3.0, 4.0])
        self.assertEqual(y2, [10.0, 11.0, 12.0, 13.0, 14.0])

        rec.clear_series(sig)
        t3, y3 = rec.get_series(sig)
        self.assertEqual(t3, [])
        self.assertEqual(y3, [])

        rec.set_series(sig, [0.0], [1.0])
        rec.clear_all_series()
        t4, y4 = rec.get_series(sig)
        self.assertEqual(t4, [])
        self.assertEqual(y4, [])


class VariableMappingDatabaseTest(unittest.TestCase):
    def test_variable_database_created_for_main(self) -> None:
        model = Model.new("main")
        db = model.get_root_by_type(ModelElementType.MODEL_VARIABLE_DATABASE)
        self.assertIsNotNone(db)
        self.assertIsInstance(db, VariableDatabase)

    def test_mapping_entries_follow_variable_registry(self) -> None:
        model = Model.new("main")
        v = Variable(name="speed", type_key="var")
        model.attach(v, parent=model.root, reserve_existing=False, remap_ids=False)
        db = model.get_variable_database()
        self.assertIsInstance(db, VariableDatabase)
        entry = db.entry_for_name("speed")
        self.assertIsInstance(entry, VariableMappingEntry)
        self.assertEqual(entry.get("mapped_signal"), "None")

        model.set_variable_mapped_signal("speed", "speed")
        self.assertEqual(model.variable_mapped_signal("speed"), "speed")
        self.assertEqual(entry.get("mapped_signal"), "speed")

        entry.set("mapped_signal", "rpm_sig")
        self.assertEqual(model.variable_mapped_signal("speed"), "rpm_sig")
        self.assertEqual(entry.get("mapped_signal"), "rpm_sig")

        assert entry.id is not None
        model.delete(model.root, v.id)  # type: ignore[arg-type]
        self.assertIsNone(db.entry_for_name("speed"))


if __name__ == "__main__":
    unittest.main()
