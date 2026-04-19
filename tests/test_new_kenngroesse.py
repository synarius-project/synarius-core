"""Tests for CCP shortcuts: new parameter / new curve / new map."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import SynariusController  # noqa: E402
from synarius_core.model import ElementaryInstance  # noqa: E402
from synarius_core.model.data_model import ComplexInstance  # noqa: E402


def _make_controller_with_dataset(dataset_name: str = "DS1") -> SynariusController:
    """Return a controller with an active dataset ready for use."""
    ctl = SynariusController()
    ctl.execute("cd @main/parameters/data_sets")
    ctl.execute(f"new DataSet {dataset_name}")
    ctl.execute("cd @main/parameters")
    ctl.execute(f"set active_dataset_name {dataset_name}")
    ctl.execute("cd @main")
    return ctl


class NewParameterTest(unittest.TestCase):
    # ------------------------------------------------------------------ #
    # new parameter (std.Kennwert)                                        #
    # ------------------------------------------------------------------ #

    def test_new_parameter_creates_elementary(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new parameter MyScalar")
        obj = ctl._resolve_ref("MyScalar")
        self.assertIsInstance(obj, ElementaryInstance)
        self.assertEqual(obj.type_key, "std.Kennwert")

    def test_new_parameter_sets_parameter_ref(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new parameter MyScalar")
        ref = ctl.execute("get MyScalar.parameter_ref")
        self.assertEqual(ref, "MyScalar")

    def test_new_parameter_creates_cal_param(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new parameter MyScalar")
        ds = ctl.model.parameter_runtime().active_dataset()
        cal_param = next(
            (c for c in ds.children if isinstance(c, ComplexInstance) and c.name == "MyScalar"),
            None,
        )
        self.assertIsNotNone(cal_param, "MODEL.CAL_PARAM not found under active dataset")
        self.assertEqual(str(cal_param.get("type")), "MODEL.CAL_PARAM")

    def test_new_parameter_default_value_is_zero(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new parameter MyScalar")
        ds = ctl.model.parameter_runtime().active_dataset()
        cal_param = next(c for c in ds.children if isinstance(c, ComplexInstance) and c.name == "MyScalar")
        rec = ctl.model.parameter_runtime().repo.get_record(cal_param.id)
        self.assertEqual(float(rec.values.flat[0]), 0.0)

    def test_new_parameter_no_active_dataset_creates_elementary_only(self) -> None:
        """Without an active dataset the block is still placed; no CalParam is created."""
        ctl = SynariusController()
        ctl.execute("new parameter MyScalar")
        obj = ctl._resolve_ref("MyScalar")
        self.assertIsInstance(obj, ElementaryInstance)
        self.assertEqual(obj.type_key, "std.Kennwert")
        # parameter_ref must NOT be set when there is no dataset to bind to
        self.assertNotIn("parameter_ref", obj.attribute_dict)

    # ------------------------------------------------------------------ #
    # new curve (std.Kennlinie)                                           #
    # ------------------------------------------------------------------ #

    def test_new_curve_creates_elementary(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new curve MyCurve")
        obj = ctl._resolve_ref("MyCurve")
        self.assertIsInstance(obj, ElementaryInstance)
        self.assertEqual(obj.type_key, "std.Kennlinie")

    def test_new_curve_default_values_and_axes(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new curve MyCurve")
        ds = ctl.model.parameter_runtime().active_dataset()
        cal_param = next(c for c in ds.children if isinstance(c, ComplexInstance) and c.name == "MyCurve")
        rec = ctl.model.parameter_runtime().repo.get_record(cal_param.id)
        np.testing.assert_array_equal(rec.values, np.zeros(4))
        np.testing.assert_array_equal(rec.axes[0].reshape(-1), np.array([1.0, 2.0, 3.0, 4.0]))

    def test_new_curve_has_x_input_port(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new curve MyCurve")
        obj = ctl._resolve_ref("MyCurve")
        self.assertIsInstance(obj, ElementaryInstance)
        pins: dict = obj.get("pin") or {}
        self.assertIn("x", pins)
        self.assertIn("out", pins)

    # ------------------------------------------------------------------ #
    # new map (std.Kennfeld)                                              #
    # ------------------------------------------------------------------ #

    def test_new_map_creates_elementary(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new map MyMap")
        obj = ctl._resolve_ref("MyMap")
        self.assertIsInstance(obj, ElementaryInstance)
        self.assertEqual(obj.type_key, "std.Kennfeld")

    def test_new_map_default_shape(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new map MyMap")
        ds = ctl.model.parameter_runtime().active_dataset()
        cal_param = next(c for c in ds.children if isinstance(c, ComplexInstance) and c.name == "MyMap")
        rec = ctl.model.parameter_runtime().repo.get_record(cal_param.id)
        self.assertEqual(rec.values.shape, (4, 4))
        np.testing.assert_array_equal(rec.values, np.zeros((4, 4)))
        np.testing.assert_array_equal(rec.axes[0].reshape(-1), np.array([1.0, 2.0, 3.0, 4.0]))
        np.testing.assert_array_equal(rec.axes[1].reshape(-1), np.array([1.0, 2.0, 3.0, 4.0]))

    def test_new_map_has_x_y_input_ports(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new map MyMap")
        obj = ctl._resolve_ref("MyMap")
        pins: dict = obj.get("pin") or {}
        self.assertIn("x", pins)
        self.assertIn("y", pins)
        self.assertIn("out", pins)

    # ------------------------------------------------------------------ #
    # Undo                                                                #
    # ------------------------------------------------------------------ #

    def test_new_parameter_undo_removes_elementary(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new parameter MyScalar")
        ctl.execute("undo")
        obj = next(
            (c for c in ctl.model.root.children if isinstance(c, ElementaryInstance) and c.name == "MyScalar"),
            None,
        )
        self.assertIsNone(obj, "Elementary should have been moved to trash on undo")

    def test_new_map_undo_removes_both(self) -> None:
        ctl = _make_controller_with_dataset()
        ctl.execute("new map MyMap")
        ds_before = ctl.model.parameter_runtime().active_dataset()
        {c.name for c in ds_before.children if isinstance(c, ComplexInstance)}
        ctl.execute("undo")
        # Elementary gone from diagram
        el_obj = next(
            (c for c in ctl.model.root.children if isinstance(c, ElementaryInstance) and c.name == "MyMap"),
            None,
        )
        self.assertIsNone(el_obj, "Elementary should be trashed after undo")
        # CalParam gone from active dataset
        ds_after = ctl.model.parameter_runtime().active_dataset()
        cal_names_after = {c.name for c in ds_after.children if isinstance(c, ComplexInstance)}
        self.assertNotIn("MyMap", cal_names_after, "CalParam should be trashed after undo")


if __name__ == "__main__":
    unittest.main()
