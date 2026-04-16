import sys
from pathlib import Path
import unittest

# Make `src/` importable when running tests via `python -m unittest`.
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.model import AttributeDict  # pyright: ignore[reportMissingImports]
from synarius_core.model.attribute_dict import AttributeEntry  # pyright: ignore[reportMissingImports]


# ---------------------------------------------------------------------------
# AttributeEntry dataclass
# ---------------------------------------------------------------------------


class AttributeEntryTest(unittest.TestCase):
    def test_stored_factory_defaults(self) -> None:
        e = AttributeEntry.stored(42)
        self.assertEqual(e.value, 42)
        self.assertIsNone(e.setter)
        self.assertIsNone(e.getter)
        self.assertTrue(e.exposed)
        self.assertFalse(e.writable)
        self.assertIsNone(e.value_spec)

    def test_stored_factory_explicit_flags(self) -> None:
        e = AttributeEntry.stored("x", exposed=False, writable=True)
        self.assertFalse(e.exposed)
        self.assertTrue(e.writable)

    def test_virtual_factory(self) -> None:
        g = lambda: 7
        s = lambda v: None
        e = AttributeEntry.virtual(g, s, exposed=False, writable=True)
        self.assertIs(e.getter, g)
        self.assertIs(e.setter, s)
        self.assertFalse(e.exposed)
        self.assertTrue(e.writable)
        self.assertIsNone(e.value_spec)

    def test_post_init_rejects_setter_plus_value_spec(self) -> None:
        with self.assertRaises(ValueError):
            AttributeEntry(setter=lambda v: None, value_spec=lambda v: v)

    def test_frozen_rejects_mutation(self) -> None:
        e = AttributeEntry.stored(1)
        with self.assertRaises(Exception):
            e.value = 2  # type: ignore[misc]

    def test_dataclasses_replace_preserves_metadata(self) -> None:
        import dataclasses
        spec = lambda v: int(v)
        e = AttributeEntry.stored(0, writable=True, value_spec=spec)
        e2 = dataclasses.replace(e, value=99)
        self.assertEqual(e2.value, 99)
        self.assertTrue(e2.writable)
        self.assertIs(e2.value_spec, spec)


# ---------------------------------------------------------------------------
# AttributeDict
# ---------------------------------------------------------------------------


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

        dict.__setitem__(
            attributes,
            "answer",
            AttributeEntry.virtual(lambda: 123, exposed=True, writable=True),
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
            AttributeEntry.stored("edit", exposed=False, writable=True),
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

    def test_set_value_raises_on_non_writable(self) -> None:
        attributes = AttributeDict()
        attributes["speed"] = 42  # writable=False by default

        with self.assertRaises(PermissionError):
            attributes.set_value("speed", 99)

    def test_set_value_routes_through_virtual_setter(self) -> None:
        attributes = AttributeDict()
        store = [0]
        attributes.set_virtual(
            "v",
            getter=lambda: store[0],
            setter=lambda val: store.__setitem__(0, int(val)),
            writable=True,
        )

        attributes.set_value("v", 5)

        self.assertEqual(store[0], 5)
        self.assertEqual(attributes["v"], 5)

    def test_set_value_does_not_run_value_spec_on_virtual_path(self) -> None:
        """value_spec must be None for virtual entries; the setter is the contract."""
        attributes = AttributeDict()
        calls: list[object] = []
        # Build virtual entry directly — note: value_spec MUST be None for virtual
        attributes.set_virtual(
            "v",
            getter=lambda: None,
            setter=lambda val: calls.append(("setter", val)),
            writable=True,
        )

        attributes.set_value("v", "x")

        self.assertEqual(calls, [("setter", "x")])

    def test_set_value_runs_value_spec_on_stored_path(self) -> None:
        attributes = AttributeDict()
        spec_calls: list[object] = []

        def spec(v: object) -> int:
            spec_calls.append(v)
            return int(v)  # type: ignore[arg-type]

        dict.__setitem__(
            attributes,
            "count",
            AttributeEntry.stored(0, writable=True, value_spec=spec),
        )

        attributes.set_value("count", "7")

        self.assertEqual(attributes["count"], 7)
        self.assertEqual(spec_calls, ["7"])

    def test_set_value_value_spec_rejection_propagates(self) -> None:
        attributes = AttributeDict()

        def reject(v: object) -> int:
            if not isinstance(v, int):
                raise TypeError(f"expected int, got {type(v).__name__}")
            return v

        dict.__setitem__(
            attributes,
            "n",
            AttributeEntry.stored(0, writable=True, value_spec=reject),
        )

        with self.assertRaises(TypeError):
            attributes.set_value("n", "not_an_int")

        # Stored value must be unchanged after rejection.
        self.assertEqual(attributes.stored_value("n"), 0)

    def test_set_value_preserves_metadata_via_replace(self) -> None:
        import dataclasses
        attributes = AttributeDict()
        spec = lambda v: v
        dict.__setitem__(
            attributes,
            "k",
            AttributeEntry.stored(0, writable=True, value_spec=spec),
        )

        attributes.set_value("k", 99)

        raw = dict.__getitem__(attributes, "k")
        self.assertIsInstance(raw, AttributeEntry)
        self.assertEqual(raw.value, 99)
        self.assertIs(raw.value_spec, spec)
        self.assertTrue(raw.writable)

    def test_allows_structural_value_replace_writable(self) -> None:
        attributes = AttributeDict()
        dict.__setitem__(attributes, "tree", AttributeEntry.stored({}, writable=True))
        self.assertTrue(attributes.allows_structural_value_replace("tree"))

    def test_allows_structural_value_replace_virtual_setter(self) -> None:
        attributes = AttributeDict()
        attributes.set_virtual("v", getter=lambda: None, setter=lambda v: None, writable=True)
        self.assertTrue(attributes.allows_structural_value_replace("v"))

    def test_allows_structural_value_replace_read_only(self) -> None:
        attributes = AttributeDict()
        attributes["ro"] = "value"  # writable=False, no setter
        self.assertFalse(attributes.allows_structural_value_replace("ro"))

    # --- adapter window: legacy 5-tuples still readable ---

    def test_adapter_reads_legacy_tuple(self) -> None:
        attributes = AttributeDict()
        dict.__setitem__(attributes, "legacy", ("hello", None, None, True, True))

        self.assertEqual(attributes["legacy"], "hello")
        self.assertTrue(attributes.exposed("legacy"))
        self.assertTrue(attributes.writable("legacy"))
        self.assertFalse(attributes.virtual("legacy"))

    def test_adapter_set_value_on_legacy_tuple(self) -> None:
        attributes = AttributeDict()
        dict.__setitem__(attributes, "legacy", ("old", None, None, True, True))

        attributes.set_value("legacy", "new")

        self.assertEqual(attributes["legacy"], "new")
        # After set_value the entry must be a proper AttributeEntry.
        raw = dict.__getitem__(attributes, "legacy")
        self.assertIsInstance(raw, AttributeEntry)


if __name__ == "__main__":
    unittest.main()
