import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import MinimalController  # noqa: E402
from synarius_core.parameters.dcm_io import import_dcm_for_dataset, parse_dcm_specs  # noqa: E402


class DcmIoTest(unittest.TestCase):
    def test_parse_minimal_all_types(self) -> None:
        p = Path(__file__).resolve().parent / "testdata" / "parameter_formats" / "dcm" / "dcm2_minimal_all_types_once.dcm"
        text = p.read_text(encoding="utf-8")
        specs = parse_dcm_specs(text)
        names = [s.name for s in specs]
        self.assertEqual(
            names,
            ["K_MIN_SCALAR", "K_MIN_BLOCK", "K_MIN_LINE", "K_MIN_MAP", "K_MIN_AXIS"],
        )
        scalar = next(s for s in specs if s.name == "K_MIN_SCALAR")
        self.assertEqual(scalar.category, "VALUE")
        self.assertEqual(scalar.values.ndim, 0)
        self.assertEqual(float(scalar.values.item()), 42.0)

    def test_import_creates_cal_params(self) -> None:
        p = Path(__file__).resolve().parent / "testdata" / "parameter_formats" / "dcm" / "dcm2_minimal_all_types_once.dcm"
        ctl = MinimalController()
        ctl.execute("cd @main/parameters/data_sets")
        ds_ref = (ctl.execute(f'new DataSet DcmTest source_path="{p.as_posix()}" source_format=dcm') or "").strip()
        self.assertTrue(ds_ref)
        n = import_dcm_for_dataset(ctl, ds_ref, str(p))
        self.assertEqual(n, 5)
        out = ctl.execute("ls") or ""
        self.assertIn("K_MIN_SCALAR", out)
        self.assertIn("K_MIN_MAP", out)


if __name__ == "__main__":
    unittest.main()
