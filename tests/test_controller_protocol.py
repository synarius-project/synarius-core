import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import UUID


sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import CommandError, MinimalController  # noqa: E402
from synarius_core.model import ElementaryInstance  # noqa: E402
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

    def test_new_fmu_instance(self) -> None:
        ctl = MinimalController()
        hn = (ctl.execute('new FmuInstance myFmu fmu_path=/tmp/a.fmu fmi_version=2.0 fmu_type=CoSimulation') or "").strip()
        self.assertTrue(hn)
        obj = ctl._resolve_ref(hn)
        self.assertIsInstance(obj, ElementaryInstance)
        self.assertEqual(obj.get("type"), "MODEL.ELEMENTARY")
        self.assertEqual(obj.get("fmu.path"), "/tmp/a.fmu")
        self.assertEqual(obj.get("fmu.fmi_version"), "2.0")
        self.assertEqual(obj.get("fmu.fmu_type"), "CoSimulation")

    def test_new_elementary_fmu_block_via_library_type_key(self) -> None:
        ctl = MinimalController()
        hn = (
            ctl.execute(
                "new Elementary ef type_key=custom.Fmu fmu_path=/tmp/c.fmu fmi_version=3.0 fmu_type=ModelExchange"
            )
            or ""
        ).strip()
        obj = ctl._resolve_ref(hn)
        self.assertIsInstance(obj, ElementaryInstance)
        self.assertEqual(obj.type_key, "custom.Fmu")
        self.assertEqual(obj.get("fmu.path"), "/tmp/c.fmu")
        self.assertEqual(obj.get("fmu.fmi_version"), "3.0")

    def test_new_fmu_instance_with_ports_literal(self) -> None:
        ctl = MinimalController()
        ports_json = (
            '[{"name":"u","value_reference":1,'
            '"causality":"input","variability":"continuous","data_type":"float"}]'
        )
        line = "new FmuInstance f2 fmu_path=/tmp/b.fmu " f"fmu_ports={shlex.quote(ports_json)}"
        hn = (ctl.execute(line) or "").strip()
        obj = ctl._resolve_ref(hn)
        self.assertIsInstance(obj, ElementaryInstance)
        pmap = obj.get("pin")
        self.assertIn("u", pmap)
        self.assertEqual(pmap["u"].get("value_reference"), 1)

    def test_new_fmu_instance_with_fmu_variables_literal(self) -> None:
        ctl = MinimalController()
        ports_json = (
            '[{"name":"u","value_reference":1,'
            '"causality":"input","variability":"continuous","data_type":"float"}]'
        )
        vars_json = (
            '[{"name":"u","value_reference":1,"causality":"input"},'
            '{"name":"y","value_reference":2,"causality":"output"}]'
        )
        line = (
            "new FmuInstance f3 fmu_path=/tmp/c.fmu "
            f"fmu_ports={shlex.quote(ports_json)} "
            f"fmu_variables={shlex.quote(vars_json)}"
        )
        hn = (ctl.execute(line) or "").strip()
        obj = ctl._resolve_ref(hn)
        self.assertIsInstance(obj, ElementaryInstance)
        vlist = obj.get("fmu.variables")
        self.assertEqual(len(vlist), 2)
        self.assertEqual(vlist[0]["name"], "u")
        self.assertEqual(vlist[1]["causality"], "output")

    def test_set_get_fmu_extra_meta_nested(self) -> None:
        ctl = MinimalController()
        hn = (ctl.execute("new FmuInstance metaBlk fmu_path=/tmp/x.fmu") or "").strip()
        ctl.execute(f"set {hn}.fmu.extra_meta.note hello")
        self.assertEqual((ctl.execute(f"get {hn}.fmu.extra_meta.note") or "").strip(), "hello")

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

    def test_dataviewer_open_widget_set_get(self) -> None:
        """CCP: DataViewer exposes ``open_widget`` for Studio to open the live widget."""
        ctl = MinimalController()
        hn = (ctl.execute("new DataViewer") or "").strip()
        self.assertTrue(hn)
        self.assertEqual((ctl.execute(f"get {hn}.open_widget") or "").strip().lower(), "false")
        ctl.execute(f"set {hn}.open_widget true")
        self.assertEqual((ctl.execute(f"get {hn}.open_widget") or "").strip().lower(), "true")

    def test_new_with_explicit_id_replay_same_hash_name(self) -> None:
        fixed = UUID("aaaaaaaa-bbbb-cccc-dddd-000000000001")
        ctl_a = MinimalController()
        hn_a = (ctl_a.execute(f"new Variable ReplayV id={fixed}") or "").strip()
        ctl_b = MinimalController()
        hn_b = (ctl_b.execute(f"new Variable ReplayV id={fixed}") or "").strip()
        self.assertEqual(hn_a, hn_b)
        obj_a = ctl_a.model.find_by_id(fixed)
        self.assertIsNotNone(obj_a)
        self.assertEqual(obj_a.hash_name, hn_a)
        obj_b = ctl_b.model.find_by_id(fixed)
        self.assertIsNotNone(obj_b)
        self.assertEqual(obj_b.hash_name, hn_b)

    def test_new_duplicate_explicit_id_raises_command_error(self) -> None:
        fixed = UUID("aaaaaaaa-bbbb-cccc-dddd-000000000002")
        ctl = MinimalController()
        ctl.execute(f"new Variable First id={fixed}")
        with self.assertRaises(CommandError):
            ctl.execute(f"new Variable Second id={fixed}")

    def test_new_invalid_id_raises_command_error(self) -> None:
        ctl = MinimalController()
        with self.assertRaises(CommandError):
            ctl.execute("new Variable Bad id=not-a-uuid")

    def test_new_explicit_id_accepts_hex_without_hyphens(self) -> None:
        ctl = MinimalController()
        hx = "0123456789abcdef0123456789abcdef"
        u = UUID(hex=hx)
        hn = (ctl.execute(f"new Variable HexId id={hx}") or "").strip()
        obj = ctl.model.find_by_id(u)
        self.assertIsNotNone(obj)
        self.assertEqual(obj.hash_name, hn)

    def test_new_dataviewer_explicit_dataviewer_id_and_uuid(self) -> None:
        ctl = MinimalController()
        fixed = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        hn = (ctl.execute(f"new DataViewer dataviewer_id=7 id={fixed}") or "").strip()
        obj = ctl.model.find_by_id(fixed)
        self.assertIsNotNone(obj)
        self.assertEqual(int(obj.get("dataviewer_id")), 7)
        self.assertEqual(obj.name, "DataViewer_7")
        self.assertEqual(obj.hash_name, hn)


if __name__ == "__main__":
    unittest.main()
