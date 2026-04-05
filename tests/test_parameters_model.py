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

        p = (ctl.execute(f"new CalParam Kp data_set={ds} category=MAP") or "").strip()
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
        p = (ctl.execute(f"new CalParam Km data_set={ds} category=CURVE") or "").strip()
        ctl.execute(f"set {p}.shape [3]")
        with self.assertRaises((CommandError, ValueError)):
            ctl.execute(f"set {p}.x1_axis [0,0,1]")

    def test_ndarray_reads_do_not_bypass_guarded_writes(self) -> None:
        ctl = MinimalController()
        ctl.execute("cd parameters/data_sets")
        ds = (ctl.execute("new DataSet DsNd") or "").strip()
        p = (ctl.execute(f"new CalParam Kn data_set={ds} category=MAP") or "").strip()
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
        p = (ctl.execute(f"new CalParam Kprint data_set={ds} category=CURVE") or "").strip()
        ctl.execute(f"set {p}.shape [3]")
        out = (ctl.execute(f"print {p}") or "").strip()
        self.assertIn("Kenngröße: Kprint", out)
        self.assertIn("Kategorie: CURVE", out)
        self.assertIn("Werte:", out)
        ds_out = (ctl.execute(f"print {ds}") or "").strip()
        self.assertIn("Datensatz: DsPrint", ds_out)
        self.assertIn("PARAMETER_DATA_SET", ds_out)


if __name__ == "__main__":
    unittest.main()

