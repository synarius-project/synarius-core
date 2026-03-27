import sys
from pathlib import Path
import unittest


# Make `src/` importable when running tests via `python -m unittest`.
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.model import AttributeDict  # pyright: ignore[reportMissingImports]


class AttributeDictTest(unittest.TestCase):
    def test_setitem_stores_default_metadata(self) -> None:
        attributes = AttributeDict()

        attributes["speed"] = 42

        self.assertEqual(attributes["speed"], 42)
        self.assertTrue(attributes.exposed("speed"))
        self.assertFalse(attributes.writable("speed"))
        self.assertFalse(attributes.virtual("speed"))

    def test_getitem_uses_getter_when_present(self) -> None:
        attributes = AttributeDict()

        # Use base dict API to inject a full entry tuple with getter.
        dict.__setitem__(
            attributes,
            "answer",
            (0, None, lambda: 123, True, True),
        )

        self.assertEqual(attributes["answer"], 123)
        self.assertTrue(attributes.virtual("answer"))
        self.assertTrue(attributes.writable("answer"))
        self.assertTrue(attributes.exposed("answer"))

    def test_getitem_uses_stored_value_without_getter(self) -> None:
        attributes = AttributeDict()

        dict.__setitem__(
            attributes,
            "mode",
            ("edit", None, None, False, True),
        )

        self.assertEqual(attributes["mode"], "edit")
        self.assertFalse(attributes.virtual("mode"))
        self.assertTrue(attributes.writable("mode"))
        self.assertFalse(attributes.exposed("mode"))

    def test_set_virtual_creates_virtual_entry(self) -> None:
        attributes = AttributeDict()
        source = {"value": 7}

        def getter() -> int:
            return source["value"]

        def setter(new_value: int) -> None:
            source["value"] = new_value

        attributes.set_virtual(
            "dynamic_value",
            getter,
            setter,
            exposed=False,
            writable=True,
        )

        self.assertEqual(attributes["dynamic_value"], 7)
        self.assertTrue(attributes.virtual("dynamic_value"))
        self.assertTrue(attributes.writable("dynamic_value"))
        self.assertFalse(attributes.exposed("dynamic_value"))


if __name__ == "__main__":
    unittest.main()

