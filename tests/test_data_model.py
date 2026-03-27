import sys
from pathlib import Path
import unittest
from uuid import uuid4


# Make `src/` importable when running tests via `python -m unittest`.
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.model import (  # noqa: E402
    ComplexInstance,
    DuplicateIdError,
    IdFactory,
    Model,
    Pin,
    PinDataType,
    PinDirection,
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


class ModelLifecycleTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
