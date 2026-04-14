"""Tests for :func:`synarius_core.parameters.ndarray_format.format_ndarray_summary`."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.parameters.ndarray_format import format_ndarray_summary  # noqa: E402


class FormatNdarraySummaryTest(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(format_ndarray_summary(np.array([])), "(leer)")
        self.assertEqual(format_ndarray_summary(np.zeros((0, 3))), "(leer)")

    def test_scalar_finite(self) -> None:
        self.assertEqual(format_ndarray_summary(np.array([2.5])), "2.5")
        self.assertEqual(format_ndarray_summary(np.array(7.0)), "7")

    def test_scalar_non_finite(self) -> None:
        self.assertEqual(format_ndarray_summary(np.array([np.nan])), str(float(np.nan)))
        self.assertEqual(format_ndarray_summary(np.array([np.inf])), str(float(np.inf)))

    def test_multi_with_finite_stats(self) -> None:
        a = np.array([[1.0, 2.0], [3.0, 4.0]])
        s = format_ndarray_summary(a)
        self.assertIn("shape=(2, 2)", s)
        self.assertIn("min=1", s)
        self.assertIn("max=4", s)
        self.assertIn("mean=2.5", s)

    def test_multi_no_finite_values(self) -> None:
        a = np.array([np.nan, np.inf, -np.inf]).reshape(1, 3)
        self.assertEqual(format_ndarray_summary(a), "shape=(1, 3) (keine endlichen Werte)")


if __name__ == "__main__":
    unittest.main()
