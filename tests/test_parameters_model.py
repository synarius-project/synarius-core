import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import CommandError, MinimalController  # noqa: E402


class ParametersModelTest(unittest.TestCase):
    def test_parameters_tree_exists_on_main_model(self) -> None:
        ctl = MinimalController()
        out = ctl.execute("ls") or ""
        self.assertIn("parameters", out)

    def test_cal_param_requires_dataset_subtree(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        _ = ctl.execute("new DataSet DsCtx")
        with self.assertRaises((CommandError, ValueError)):
            ctl.execute("new CalParam Outside category=VALUE")

    def test_dataset_owned_cal_param_and_shape_updates(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds = (
            ctl.execute('new DataSet DsA source_path="H:/Pfad/datei.dcm" source_format=dcm source_hash=abc123')
            or ""
        ).strip()
        self.assertTrue(ds)
        self.assertIn("datei.dcm", (ctl.execute(f"get {ds}.source_path") or ""))
        self.assertEqual((ctl.execute(f"get {ds}.source_format") or "").strip(), "dcm")

        ctl.execute(f"cd {ds}")
        p = (ctl.execute("new CalParam Kp category=MAP") or "").strip()
        self.assertTrue(p)

        ctl.execute(f"set {p}.shape [2,3]")
        self.assertEqual((ctl.execute(f"get {p}.shape") or "").strip(), "[2, 3]")

        ctl.execute(f"set {p}.x2_dim 4")
        self.assertEqual((ctl.execute(f"get {p}.shape") or "").strip(), "[2, 4]")

        ctl.execute(f"set {p}.x1_axis [1,2]")
        axis = (ctl.execute(f"get {p}.x1_axis") or "").strip()
        self.assertEqual(axis, "[1.0, 2.0]")
        ctl.execute(f'set {p}.x1_name "Engine speed"')
        ctl.execute(f'set {p}.x1_unit rpm')
        self.assertEqual((ctl.execute(f"get {p}.x1_name") or "").strip(), "Engine speed")
        self.assertEqual((ctl.execute(f"get {p}.x1_unit") or "").strip(), "rpm")

    def test_axis_must_be_strictly_monotonic(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds = (ctl.execute("new DataSet Dsm") or "").strip()
        ctl.execute(f"cd {ds}")
        p = (ctl.execute("new CalParam Km category=CURVE") or "").strip()
        ctl.execute(f"set {p}.shape [3]")
        with self.assertRaises((CommandError, ValueError)):
            ctl.execute(f"set {p}.x1_axis [0,0,1]")

    def test_ndarray_reads_do_not_bypass_guarded_writes(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds = (ctl.execute("new DataSet DsNd") or "").strip()
        ctl.execute(f"cd {ds}")
        p = (ctl.execute("new CalParam Kn category=MAP") or "").strip()
        ctl.execute(f"set {p}.shape [2,2]")
        rec = ctl.model.parameter_runtime().repo.get_record(ctl._resolve_ref(p).id)
        arr = ctl.model.parameter_runtime().repo.get_value(rec.parameter_id)
        # Must be read-only ndarray copy/view.
        self.assertFalse(bool(arr.flags.writeable))
        with self.assertRaises(ValueError):
            arr[0, 0] = 42.0

    def test_print_cal_param_and_dataset(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds = (ctl.execute("new DataSet DsPrint") or "").strip()
        ctl.execute(f"cd {ds}")
        p = (ctl.execute("new CalParam Kprint category=CURVE") or "").strip()
        ctl.execute(f"set {p}.shape [3]")
        out = (ctl.execute(f"print {p}") or "").strip()
        self.assertIn("Kenngröße: Kprint", out)
        self.assertIn("Kategorie: CURVE", out)
        self.assertIn("Werte:", out)
        ds_out = (ctl.execute(f"print {ds}") or "").strip()
        self.assertIn("Datensatz: DsPrint", ds_out)
        self.assertIn("PARAMETER_DATA_SET", ds_out)

    def test_cp_cal_param_ccp(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds_a = (ctl.execute("new DataSet DsCopyA") or "").strip()
        ds_b = (ctl.execute("new DataSet DsCopyB") or "").strip()
        ctl.execute(f"cd {ds_a}")
        pa = (ctl.execute("new CalParam Kcopy category=VALUE") or "").strip()
        ctl.execute(f"set {pa}.value 3.25")
        ctl.execute("cd ..")
        ctl.execute(f"cd {ds_b}")
        pb = (ctl.execute("new CalParam Kcopy category=VALUE") or "").strip()
        ctl.execute(f"set {pb}.value 0.0")
        out = (ctl.execute(f"cp cal_param {pa} {pb}") or "").strip()
        self.assertTrue(out.startswith("ok"))
        self.assertEqual(float((ctl.execute(f"get {pb}.value") or "").strip()), 3.25)

    def test_cp_cal_param_preserves_dest_source_identifier(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds_a = (ctl.execute("new DataSet DsCpSidA") or "").strip()
        ds_b = (ctl.execute("new DataSet DsCpSidB") or "").strip()
        ctl.execute(f"cd {ds_a}")
        pa = (ctl.execute("new CalParam Ksid category=VALUE") or "").strip()
        ctl.execute(f"set {pa}.value 1.0")
        ctl.execute("cd ..")
        ctl.execute(f"cd {ds_b}")
        pb = (ctl.execute("new CalParam Ksid category=VALUE") or "").strip()
        ctl.execute(f"set {pb}.value 9.0")
        repo = ctl.model.parameter_runtime().repo
        id_a = ctl._resolve_ref(pa).id
        id_b = ctl._resolve_ref(pb).id
        repo._con.execute(
            "UPDATE parameters_all SET source_identifier = ? WHERE parameter_id = ?",
            ["src_a", str(id_a)],
        )
        repo._con.execute(
            "UPDATE parameters_all SET source_identifier = ? WHERE parameter_id = ?",
            ["keep_dest_b", str(id_b)],
        )
        ctl.execute(f"cp cal_param {pa} {pb}")
        rec_b = repo.get_record(id_b)
        self.assertEqual(rec_b.source_identifier, "keep_dest_b")
        self.assertEqual(float((ctl.execute(f"get {pb}.value") or "").strip()), 1.0)

    def test_del_parameter_data_set_cascades_model_and_duckdb(self) -> None:
        from uuid import UUID

        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds_h = (ctl.execute("new DataSet DsCascadeDel") or "").strip()
        ds_node = ctl._resolve_ref(ds_h)
        self.assertIsInstance(ds_node.id, UUID)
        ds_id = ds_node.id
        ctl.execute(f"cd {ds_h}")
        p_h = (ctl.execute("new CalParam Kcascade category=VALUE") or "").strip()
        pid = ctl._resolve_ref(p_h).id
        repo = ctl.model.parameter_runtime().repo
        self.assertIsNotNone(repo.get_dataset_name(ds_id))
        self.assertIsNotNone(repo.get_record(pid))
        removed = int((ctl.execute(f"del {ds_h}") or "0").strip())
        self.assertGreaterEqual(removed, 1)
        self.assertIsNone(repo.get_dataset_name(ds_id))
        with self.assertRaises(ValueError):
            repo.get_record(pid)
        with self.assertRaises(CommandError):
            ctl._resolve_ref(ds_h)
        with self.assertRaises(CommandError):
            ctl._resolve_ref(p_h)


if __name__ == "__main__":
    unittest.main()

