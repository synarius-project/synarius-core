import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import MinimalController  # noqa: E402
from synarius_core.model.data_model import ComplexInstance  # noqa: E402
from synarius_core.parameters.dcm_io import import_dcm_for_dataset, parse_dcm_specs  # noqa: E402


class DcmIoTest(unittest.TestCase):
    def test_parse_minimal_all_types(self) -> None:
        p = Path(__file__).resolve().parent / "testdata" / "parameter_formats" / "dcm" / "dcm2_minimal_all_types_once.dcm"
        text = p.read_text(encoding="utf-8")
        specs = parse_dcm_specs(text)
        names = [s.name for s in specs]
        self.assertEqual(
            names,
            [
                "K_MIN_SCALAR",
                "K_MIN_BLOCK",
                "K_MIN_LINE",
                "K_MIN_LINE_NL5",
                "K_MIN_LINE_NL11",
                "K_MIN_MAP",
                "K_MIN_MAP_3X5",
                "K_MIN_MAP_4X7",
                "K_MIN_MAP_5X8",
                "K_MIN_AXIS",
            ],
        )
        scalar = next(s for s in specs if s.name == "K_MIN_SCALAR")
        self.assertEqual(scalar.category, "VALUE")
        self.assertEqual(scalar.values.ndim, 0)
        self.assertEqual(float(scalar.values.item()), 42.0)
        self.assertEqual(scalar.display_name, "High-voltage bus reference voltage")
        self.assertEqual(scalar.unit, "V")
        self.assertIn("VAR=K_MIN_SCALAR", scalar.source_identifier)
        self.assertIn("FUNKTION=VehicleEnergyCalibration", scalar.source_identifier)

        curve = next(s for s in specs if s.name == "K_MIN_LINE")
        self.assertEqual(curve.axis_names.get(0), "Wheel angular velocity")
        self.assertEqual(curve.axis_units.get(0), "rpm")
        block = next(s for s in specs if s.name == "K_MIN_BLOCK")
        self.assertEqual(block.category, "MATRIX")
        self.assertEqual(tuple(block.values.shape), (4, 2))

        m = next(s for s in specs if s.name == "K_MIN_MAP")
        self.assertEqual(m.axis_names.get(0), "Crankshaft velocity")
        self.assertEqual(m.axis_names.get(1), "Indicated torque demand fraction")
        self.assertEqual(m.axis_units.get(0), "rpm")
        self.assertEqual(m.axis_units.get(1), "%")

        nl5 = next(s for s in specs if s.name == "K_MIN_LINE_NL5")
        self.assertEqual(nl5.category, "CURVE")
        self.assertEqual(tuple(nl5.values.shape), (5,))
        m58 = next(s for s in specs if s.name == "K_MIN_MAP_5X8")
        self.assertEqual(m58.category, "MAP")
        self.assertEqual(tuple(m58.values.shape), (5, 8))
        axis = next(s for s in specs if s.name == "K_MIN_AXIS")
        self.assertEqual(axis.category, "NODE_ARRAY")

    def test_import_creates_cal_params(self) -> None:
        p = Path(__file__).resolve().parent / "testdata" / "parameter_formats" / "dcm" / "dcm2_minimal_all_types_once.dcm"
        ctl = MinimalController()
        ctl.execute("cd @main/parameters/data_sets")
        ds_ref = (ctl.execute(f'new DataSet DcmTest source_path="{p.as_posix()}" source_format=dcm') or "").strip()
        self.assertTrue(ds_ref)
        n = import_dcm_for_dataset(ctl, ds_ref, str(p))
        self.assertEqual(n, 10)
        ctl.execute(f"cd {ds_ref}")
        out = ctl.execute("ls") or ""
        self.assertIn("K_MIN_SCALAR", out)
        self.assertIn("K_MIN_MAP", out)
        self.assertEqual((ctl.execute("get K_MIN_SCALAR.display_name") or "").strip(), "High-voltage bus reference voltage")
        self.assertEqual((ctl.execute("get K_MIN_SCALAR.unit") or "").strip(), "V")
        self.assertEqual((ctl.execute("get K_MIN_LINE.x1_name") or "").strip(), "Wheel angular velocity")
        self.assertEqual((ctl.execute("get K_MIN_LINE.x1_unit") or "").strip(), "rpm")
        self.assertEqual((ctl.execute("get K_MIN_MAP.x1_name") or "").strip(), "Crankshaft velocity")
        self.assertEqual((ctl.execute("get K_MIN_MAP.x2_name") or "").strip(), "Indicated torque demand fraction")
        self.assertEqual((ctl.execute("get K_MIN_MAP.x2_unit") or "").strip(), "%")

        repo = ctl.model.parameter_runtime().repo

        def _pid(nm: str):
            for node in ctl.model.iter_objects():
                if not isinstance(node, ComplexInstance):
                    continue
                if node.name == nm and str(node.get("type")) == "MODEL.CAL_PARAM":
                    return node.id
            raise AssertionError(nm)

        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_SCALAR")).value_label, "42.0")
        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_BLOCK")).value_label, "4X2 Values")
        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_LINE")).value_label, "8 Values")
        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_MAP")).value_label, "6X10 Values")
        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_MAP_3X5")).value_label, "5X3 Values")
        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_MAP_4X7")).value_label, "4X7 Values")
        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_MAP_5X8")).value_label, "5X8 Values")
        self.assertEqual(repo.get_parameter_table_summary(_pid("K_MIN_AXIS")).value_label, "8 Values")

    def test_write_roundtrip_minimal_all_types(self) -> None:
        p = Path(__file__).resolve().parent / "testdata" / "parameter_formats" / "dcm" / "dcm2_minimal_all_types_once.dcm"
        ctl = MinimalController()
        ctl.execute("cd @main/parameters/data_sets")
        ds_ref = (ctl.execute(f'new DataSet DcmWriteRt source_path="{p.as_posix()}" source_format=dcm') or "").strip()
        self.assertTrue(ds_ref)
        n = import_dcm_for_dataset(ctl, ds_ref, str(p))
        self.assertEqual(n, 10)
        ctl.model.parameter_runtime().set_active_dataset_name("DcmWriteRt")
        fd, out_path = tempfile.mkstemp(suffix=".dcm")
        os.close(fd)
        try:
            r = ctl.execute(f'write "{out_path}"')
            self.assertEqual(r, "10")
            text = Path(out_path).read_text(encoding="utf-8")
            wspec = parse_dcm_specs(text)
            ospec = parse_dcm_specs(p.read_text(encoding="utf-8"))
        finally:
            os.unlink(out_path)
        self.assertEqual({s.name for s in wspec}, {s.name for s in ospec})

        def _by_name(specs):
            return {s.name: s for s in specs}

        wo, oo = _by_name(wspec), _by_name(ospec)
        for nm in oo:
            a, b = wo[nm], oo[nm]
            self.assertEqual(a.category, b.category)
            np.testing.assert_allclose(np.asarray(a.values), np.asarray(b.values), rtol=0, atol=1e-9)
            self.assertEqual(set(a.axes.keys()), set(b.axes.keys()))
            for k in a.axes:
                np.testing.assert_allclose(np.asarray(a.axes[k]), np.asarray(b.axes[k]), rtol=0, atol=1e-9)
            self.assertEqual(a.display_name, b.display_name)
            self.assertEqual(a.unit, b.unit)

            def _nonempty_str_dict(d):
                return {k: v for k, v in d.items() if str(v).strip() != ""}

            self.assertEqual(_nonempty_str_dict(a.axis_names), _nonempty_str_dict(b.axis_names))
            self.assertEqual(_nonempty_str_dict(a.axis_units), _nonempty_str_dict(b.axis_units))

    def test_invalid_metadata_line_raises(self) -> None:
        p = Path(__file__).resolve().parent / "testdata" / "parameter_formats" / "dcm" / "dcm2_invalid_example.dcm"
        text = p.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            parse_dcm_specs(text)


if __name__ == "__main__":
    unittest.main()
