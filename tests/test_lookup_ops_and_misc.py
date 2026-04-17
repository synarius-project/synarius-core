"""Tests for lookup_ops, runtime_source_text, and error paths in fmfl_parser / python_backend."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ---------------------------------------------------------------------------
# lookup_ops
# ---------------------------------------------------------------------------

class CurveLookupTest(unittest.TestCase):

    def setUp(self) -> None:
        from synarius_core.dataflow_sim.lookup_ops import syn_curve_lookup_linear_clamp
        self._f = syn_curve_lookup_linear_clamp
        self._axis = np.array([0.0, 1.0, 2.0, 3.0])
        self._vals = np.array([10.0, 20.0, 30.0, 40.0])

    def test_exact_breakpoint_first(self) -> None:
        self.assertAlmostEqual(self._f(self._axis, self._vals, 0.0), 10.0)

    def test_exact_breakpoint_last(self) -> None:
        self.assertAlmostEqual(self._f(self._axis, self._vals, 3.0), 40.0)

    def test_exact_breakpoint_middle(self) -> None:
        self.assertAlmostEqual(self._f(self._axis, self._vals, 1.0), 20.0)

    def test_interpolation_midpoint(self) -> None:
        self.assertAlmostEqual(self._f(self._axis, self._vals, 1.5), 25.0)

    def test_clamp_below_axis(self) -> None:
        self.assertAlmostEqual(self._f(self._axis, self._vals, -5.0), 10.0)

    def test_clamp_above_axis(self) -> None:
        self.assertAlmostEqual(self._f(self._axis, self._vals, 99.0), 40.0)

    def test_two_breakpoints_linear(self) -> None:
        ax = np.array([0.0, 1.0])
        v  = np.array([0.0, 100.0])
        from synarius_core.dataflow_sim.lookup_ops import syn_curve_lookup_linear_clamp as f
        self.assertAlmostEqual(f(ax, v, 0.5), 50.0)


class MapLookupTest(unittest.TestCase):

    def setUp(self) -> None:
        from synarius_core.dataflow_sim.lookup_ops import syn_map_lookup_bilinear_clamp
        self._f = syn_map_lookup_bilinear_clamp
        # 3×3 map: values[i,j] = i * 10 + j
        self._ax0 = np.array([0.0, 1.0, 2.0])
        self._ax1 = np.array([0.0, 1.0, 2.0])
        self._v   = np.array([[0.0, 1.0, 2.0],
                               [10.0, 11.0, 12.0],
                               [20.0, 21.0, 22.0]])

    def test_exact_corner_origin(self) -> None:
        self.assertAlmostEqual(self._f(self._ax0, self._ax1, self._v, 0.0, 0.0), 0.0)

    def test_exact_corner_max(self) -> None:
        self.assertAlmostEqual(self._f(self._ax0, self._ax1, self._v, 2.0, 2.0), 22.0)

    def test_interpolation_center(self) -> None:
        # Exact cell midpoint (0.5, 0.5) → bilinear avg of corners (0,1,10,11)
        result = self._f(self._ax0, self._ax1, self._v, 0.5, 0.5)
        self.assertAlmostEqual(result, 5.5)

    def test_clamp_below(self) -> None:
        result = self._f(self._ax0, self._ax1, self._v, -1.0, -1.0)
        self.assertAlmostEqual(result, 0.0)

    def test_clamp_above(self) -> None:
        result = self._f(self._ax0, self._ax1, self._v, 99.0, 99.0)
        self.assertAlmostEqual(result, 22.0)

    def test_interpolation_row_axis_only(self) -> None:
        result = self._f(self._ax0, self._ax1, self._v, 1.0, 0.0)
        self.assertAlmostEqual(result, 10.0)


# ---------------------------------------------------------------------------
# runtime_source_text
# ---------------------------------------------------------------------------

class RuntimeSourceTextTest(unittest.TestCase):

    def test_returns_string(self) -> None:
        from synarius_core.dataflow_sim.runtime_source_text import read_simple_run_engine_module_source
        src = read_simple_run_engine_module_source()
        self.assertIsInstance(src, str)

    def test_contains_engine_header(self) -> None:
        from synarius_core.dataflow_sim.runtime_source_text import read_simple_run_engine_module_source
        src = read_simple_run_engine_module_source()
        self.assertIn("SimpleRunEngine", src)


# ---------------------------------------------------------------------------
# fmfl_parser edge cases (error paths)
# ---------------------------------------------------------------------------

class FmflParserEdgeCaseTest(unittest.TestCase):

    def _parse(self, doc: str):
        from synarius_core.dataflow_sim.fmfl_parser import parse_equations_block
        return parse_equations_block(f"equations:\n  {doc}\n")

    def test_prev_as_function_argument_parses(self) -> None:
        """prev(name) used as a function argument must parse successfully (hits _parse_atomic line 130)."""
        from synarius_core.dataflow_sim.fmfl_parser import CallExpr, PrevExpr
        result = self._parse("y = curve_lookup(kl1, prev(x))")
        self.assertEqual(len(result), 1)
        stmt = result[0]
        from synarius_core.dataflow_sim.fmfl_parser import AssignStmt
        assert isinstance(stmt, AssignStmt)
        assert isinstance(stmt.rhs, CallExpr)
        self.assertIsInstance(stmt.rhs.args[1], PrevExpr)

    def test_invalid_atom_in_function_arg_raises(self) -> None:
        """Non-name, non-prev atom as function arg raises FmflParseError (line 133)."""
        from synarius_core.dataflow_sim.fmfl_parser import FmflParseError
        with self.assertRaises(FmflParseError):
            self._parse("y = curve_lookup(kl1, 123)")


# ---------------------------------------------------------------------------
# python_backend error paths (direct AST construction)
# ---------------------------------------------------------------------------

class PythonBackendErrorPathTest(unittest.TestCase):

    def _make_ctx(self):
        from synarius_core.dataflow_sim.codegen_backend import (
            BuildPolicy, CodegenContext, TargetBinding)
        from synarius_core.dataflow_sim.python_backend import PROFILE_ID
        return CodegenContext(
            fmfl_text="equations:\n",
            profile=PROFILE_ID,
            binding=TargetBinding(),
            policy=BuildPolicy(),
        )

    def test_param_scalar_wrong_arg_count_raises(self) -> None:
        from synarius_core.dataflow_sim.fmfl_parser import AssignStmt, CallExpr, FmflParseError, NameExpr
        from synarius_core.dataflow_sim.python_backend import PythonBackend
        stmt = AssignStmt(
            target="x",
            rhs=CallExpr("param_scalar", (NameExpr("a"), NameExpr("b"))),
        )
        with self.assertRaises(FmflParseError):
            PythonBackend().emit_statement(stmt, self._make_ctx())

    def test_curve_lookup_wrong_arg_count_raises(self) -> None:
        from synarius_core.dataflow_sim.fmfl_parser import AssignStmt, CallExpr, FmflParseError, NameExpr
        from synarius_core.dataflow_sim.python_backend import PythonBackend
        stmt = AssignStmt(
            target="x",
            rhs=CallExpr("curve_lookup", (NameExpr("kl1"),)),
        )
        with self.assertRaises(FmflParseError):
            PythonBackend().emit_statement(stmt, self._make_ctx())

    def test_map_lookup_wrong_arg_count_raises(self) -> None:
        from synarius_core.dataflow_sim.fmfl_parser import AssignStmt, CallExpr, FmflParseError, NameExpr
        from synarius_core.dataflow_sim.python_backend import PythonBackend
        stmt = AssignStmt(
            target="x",
            rhs=CallExpr("map_lookup", (NameExpr("kf1"), NameExpr("x"))),
        )
        with self.assertRaises(FmflParseError):
            PythonBackend().emit_statement(stmt, self._make_ctx())

    def test_extract_name_non_name_arg_raises(self) -> None:
        from synarius_core.dataflow_sim.fmfl_parser import (
            AssignStmt, BinOpExpr, CallExpr, FmflParseError, NameExpr)
        from synarius_core.dataflow_sim.python_backend import PythonBackend
        stmt = AssignStmt(
            target="x",
            rhs=CallExpr("param_scalar", (BinOpExpr(NameExpr("a"), "+", NameExpr("b")),)),
        )
        with self.assertRaises(FmflParseError):
            PythonBackend().emit_statement(stmt, self._make_ctx())

    def test_prev_with_non_name_inner_raises(self) -> None:
        from synarius_core.dataflow_sim.fmfl_parser import (
            AssignStmt, BinOpExpr, FmflParseError, NameExpr, PrevExpr)
        from synarius_core.dataflow_sim.python_backend import PythonBackend
        stmt = AssignStmt(
            target="x",
            rhs=PrevExpr(BinOpExpr(NameExpr("a"), "+", NameExpr("b"))),
        )
        with self.assertRaises(FmflParseError):
            PythonBackend().emit_statement(stmt, self._make_ctx())


# ---------------------------------------------------------------------------
# fmfl_emit (re-export module — importing covers all 3 statements)
# ---------------------------------------------------------------------------

class FmflEmitImportTest(unittest.TestCase):

    def test_fmfl_emit_exports_generate_functions(self) -> None:
        from synarius_core.dataflow_sim.fmfl_emit import (  # noqa: F401
            generate_fmfl_document,
            generate_python_kernel_document,
        )
        self.assertTrue(callable(generate_fmfl_document))
        self.assertTrue(callable(generate_python_kernel_document))


# ---------------------------------------------------------------------------
# unrolled_loader error path
# ---------------------------------------------------------------------------

class UnrolledLoaderTest(unittest.TestCase):

    def test_source_without_run_equations_raises(self) -> None:
        from synarius_core.dataflow_sim.unrolled_loader import load_run_equations_from_source
        with self.assertRaises(RuntimeError):
            load_run_equations_from_source("x = 1  # no run_equations here")


# ---------------------------------------------------------------------------
# FmflCodegenBackend base class NotImplementedError paths
# ---------------------------------------------------------------------------

class FmflCodegenBackendBaseTest(unittest.TestCase):

    def setUp(self) -> None:
        from synarius_core.dataflow_sim.codegen_backend import (
            BuildPolicy, CodegenContext, FmflCodegenBackend, TargetBinding)
        self._backend = FmflCodegenBackend()
        self._ctx = CodegenContext(
            fmfl_text="equations:\n",
            profile="python_float64",
            binding=TargetBinding(),
            policy=BuildPolicy(),
        )

    def test_emit_header_raises_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            self._backend.emit_header(self._ctx)

    def test_emit_statement_raises_not_implemented(self) -> None:
        from synarius_core.dataflow_sim.fmfl_parser import CommentStmt
        with self.assertRaises(NotImplementedError):
            self._backend.emit_statement(CommentStmt("test"), self._ctx)

    def test_emit_footer_raises_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            self._backend.emit_footer(self._ctx)


# ---------------------------------------------------------------------------
# python_backend unknown expression type (line 235)
# ---------------------------------------------------------------------------

class PythonBackendUnknownExprTest(unittest.TestCase):

    def test_unknown_expr_type_raises(self) -> None:
        from dataclasses import dataclass
        from synarius_core.dataflow_sim.codegen_backend import (
            BuildPolicy, CodegenContext, TargetBinding)
        from synarius_core.dataflow_sim.fmfl_parser import AssignStmt, FmflParseError
        from synarius_core.dataflow_sim.python_backend import PROFILE_ID, PythonBackend

        @dataclass
        class _StrangeExpr:
            pass

        ctx = CodegenContext(
            fmfl_text="equations:\n",
            profile=PROFILE_ID,
            binding=TargetBinding(),
            policy=BuildPolicy(),
        )
        stmt = AssignStmt(target="x", rhs=_StrangeExpr())  # type: ignore[arg-type]
        with self.assertRaises(FmflParseError):
            PythonBackend().emit_statement(stmt, ctx)


if __name__ == "__main__":
    unittest.main()
