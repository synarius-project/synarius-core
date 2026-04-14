import sys
import unittest
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import SynariusController  # noqa: E402
from synarius_core.model import Variable  # noqa: E402
from synarius_core.variable_registry import VariableNameRegistry  # noqa: E402


class VariableNameRegistryTest(unittest.TestCase):
    def test_increment_decrement_removes_row_at_zero(self) -> None:
        reg = VariableNameRegistry()
        reg.increment("A")
        reg.increment("A")
        self.assertEqual(reg.count_for_name("A"), 2)
        reg.decrement("A")
        self.assertEqual(reg.count_for_name("A"), 1)
        reg.decrement("A")
        self.assertEqual(reg.count_for_name("A"), 0)
        self.assertEqual(reg.rows_ordered_by_name(), [])

    def test_on_renamed(self) -> None:
        reg = VariableNameRegistry()
        reg.increment("X")
        reg.on_renamed("X", "Y")
        self.assertEqual(reg.count_for_name("X"), 0)
        self.assertEqual(reg.count_for_name("Y"), 1)

    def test_clear(self) -> None:
        reg = VariableNameRegistry()
        reg.increment("p")
        reg.clear()
        self.assertEqual(reg.rows_ordered_by_name(), [])


class ModelVariableRegistryIntegrationTest(unittest.TestCase):
    @staticmethod
    def _count_map(rows: list[tuple[str, int, str]]) -> dict[str, int]:
        return {name: count for name, count, _mapped in rows}

    def test_new_and_del_keep_counts(self) -> None:
        ctl = SynariusController()
        self.assertEqual(ctl.model.variable_registry.rows_ordered_by_name(), [])
        ctl.execute("new Variable Speed")
        ctl.execute("new Variable Speed")
        rows = self._count_map(ctl.model.variable_registry.rows_ordered_by_name())
        self.assertEqual(rows.get("Speed"), 2)
        speeds = [n for n in ctl.model.iter_objects() if isinstance(n, Variable) and n.name == "Speed"]
        self.assertEqual(len(speeds), 2)
        ctl.execute(f"del {speeds[0].hash_name}")
        rows2 = self._count_map(ctl.model.variable_registry.rows_ordered_by_name())
        self.assertEqual(rows2.get("Speed"), 1)

    def test_rebuild_matches_tree(self) -> None:
        ctl = SynariusController()
        ctl.execute("new Variable A")
        ctl.execute("new Variable B")
        ctl.model.variable_registry.clear()
        self.assertEqual(ctl.model.variable_registry.rows_ordered_by_name(), [])
        ctl.model.rebuild_variable_registry()
        rows = self._count_map(ctl.model.variable_registry.rows_ordered_by_name())
        self.assertEqual(rows.get("A"), 1)
        self.assertEqual(rows.get("B"), 1)


if __name__ == "__main__":
    unittest.main()
