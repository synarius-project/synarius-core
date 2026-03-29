import sys
import tempfile
from pathlib import Path
import unittest


sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import CommandError, MinimalController  # noqa: E402
from synarius_core.variable_naming import InvalidVariableNameError  # noqa: E402


class MinimalControllerProtocolTest(unittest.TestCase):
    def test_new_basic_operator_accepts_position(self) -> None:
        ctl = MinimalController()
        ctl.execute("new BasicOperator + 10 20 1 name=OpPlaced")
        self.assertEqual(float(ctl.execute("get OpPlaced.x")), 10.0)
        self.assertEqual(float(ctl.execute("get OpPlaced.y")), 20.0)

    def test_new_set_get_and_ls(self) -> None:
        ctl = MinimalController()
        created = ctl.execute("new Variable Speed")
        self.assertIsNotNone(created)

        listing = ctl.execute("ls")
        self.assertIn("Speed", listing or "")

        ctl.execute("set Speed.value 3.14")
        got = ctl.execute("get Speed.value")
        self.assertEqual(got, "3.14")

    def test_new_variable_rejects_invalid_python_name(self) -> None:
        ctl = MinimalController()
        with self.assertRaises(InvalidVariableNameError):
            ctl.execute("new Variable 1bad")

    def test_set_name_rejects_invalid_python_identifier(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable okname")
        with self.assertRaises(InvalidVariableNameError):
            ctl.execute("set okname.name bad-name")

    def test_select_and_set_selection(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("new Variable B")
        ctl.execute("select A B")
        updated = ctl.execute("set @selection value 10")
        self.assertEqual(updated, "2")

    def test_cd_allows_elementary_object_context(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Elem")
        path = ctl.execute("cd Elem") or ""
        self.assertIn("Elem@", path)
        back = ctl.execute("cd ..") or ""
        self.assertIn("main@", back)

    def test_lsattr_shows_values_and_long_flags(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Speed")
        ctl.execute("set Speed.value 3.14")

        short_out = ctl.execute("lsattr") or ""
        self.assertIn("NAME", short_out)
        self.assertIn("updated_at", short_out)
        self.assertNotIn("|", short_out)
        self.assertNotIn("---", short_out)
        self.assertNotIn("=", short_out)
        self.assertIn("created_at", short_out)
        self.assertIn("+00:00", short_out)

        long_out = ctl.execute("lsattr -l") or ""
        self.assertIn("NAME", long_out)
        self.assertIn("VALUE", long_out)
        self.assertIn("VIRTUAL", long_out)
        self.assertIn("WRITABLE", long_out)
        self.assertIn("true", long_out)
        self.assertIn("false", long_out)
        self.assertNotIn("|", long_out)
        self.assertNotIn("---", long_out)
        self.assertNotIn("=", long_out)

    def test_lsattr_accepts_context_argument(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Speed")
        out = ctl.execute("lsattr Speed") or ""
        self.assertIn("NAME", out)
        self.assertIn("name", out)

    def test_load_script(self) -> None:
        ctl = MinimalController()
        script = "\n".join(
            [
                "new Variable V1",
                "set V1.value 1.5",
                "new BasicOperator + name=Op1",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "model.pyp"
            script_path.write_text(script, encoding="utf-8")
            ctl.execute(f'load "{script_path}"')
            self.assertIn("V1", ctl.execute("ls") or "")

    def test_load_rebinds_at_main_alias_for_root_attrs(self) -> None:
        """``load`` replaces ``model``; @main must target the new root or ``set @main.*`` affects the wrong tree."""
        ctl = MinimalController()
        root_before = ctl.model.root
        self.assertIs(ctl.alias_roots["@main"], root_before)
        script = "new Variable Vloaded"
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "m.syn"
            script_path.write_text(script, encoding="utf-8")
            ctl.execute(f'load "{script_path}"')
        self.assertIsNot(ctl.model.root, root_before)
        self.assertIs(ctl.alias_roots["@main"], ctl.model.root)
        ctl.execute("set @main.simulation_mode true")
        self.assertTrue(bool(ctl.model.root.get("simulation_mode")))

    def test_del_selected_removes_selection(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("new Variable B")
        ctl.execute("select A B")
        removed = ctl.execute("del @selected")
        self.assertEqual(removed, "2")
        ls_lines = [ln.strip() for ln in (ctl.execute("ls") or "").splitlines() if ln.strip()]
        self.assertNotIn("A", ls_lines)
        self.assertNotIn("B", ls_lines)
        self.assertEqual(len(ctl.selection), 0)

    def test_del_selected_empty_selection(self) -> None:
        ctl = MinimalController()
        self.assertEqual(ctl.execute("del @selected"), "0")

    def test_del_selected_rejects_extra_refs(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        with self.assertRaises(CommandError):
            ctl.execute("del @selected A")

    def test_del_prunes_selection_when_object_removed_by_ref(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("select A")
        ctl.execute("del A")
        self.assertEqual(len(ctl.selection), 0)

    def test_set_selection_delta_position(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("new Variable B")
        ctl.execute("select A B")
        n = ctl.execute("set -p @selection position 2 -1")
        self.assertEqual(n, "2")
        self.assertEqual(float(ctl.execute("get A.x")), 2.0)
        self.assertEqual(float(ctl.execute("get A.y")), -1.0)
        self.assertEqual(float(ctl.execute("get B.x")), 2.0)
        self.assertEqual(float(ctl.execute("get B.y")), -1.0)

    def test_set_selection_delta_scalar(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("set A.value 10")
        ctl.execute("select A")
        n = ctl.execute("set -p @selection value 0.5")
        self.assertEqual(n, "1")
        self.assertEqual(float(ctl.execute("get A.value")), 10.5)

    def test_set_selection_delta_rejects_operand_before_option(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("select A")
        with self.assertRaises(CommandError):
            ctl.execute("set @selection -p position 1 2")


if __name__ == "__main__":
    unittest.main()
