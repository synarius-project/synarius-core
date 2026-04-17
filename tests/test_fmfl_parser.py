"""Unit tests for fmfl_parser — pure text parser, zero external dependencies."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim.fmfl_parser import (  # noqa: E402
    AssignStmt,
    BinOpExpr,
    CallExpr,
    CommentStmt,
    FmflParseError,
    NameExpr,
    PrevExpr,
    parse_equations_block,
)


def _fmfl(equations_body: str) -> str:
    """Wrap equation lines in a minimal FMFL document."""
    return f"init:\n\nequations:\n{equations_body}"


class ParseEquationsBlockTest(unittest.TestCase):

    # ------------------------------------------------------------------
    # Trivial / boundary cases
    # ------------------------------------------------------------------

    def test_no_equations_block_returns_empty(self) -> None:
        self.assertEqual(parse_equations_block("init:\n  x = 1.0\n"), [])

    def test_empty_document_returns_empty(self) -> None:
        self.assertEqual(parse_equations_block(""), [])

    def test_empty_equations_block_returns_empty(self) -> None:
        self.assertEqual(parse_equations_block("equations:\n"), [])

    def test_blank_lines_inside_block_are_skipped(self) -> None:
        result = parse_equations_block(_fmfl("  x = y\n\n  z = w\n"))
        self.assertEqual(len(result), 2)

    # ------------------------------------------------------------------
    # Comment statements
    # ------------------------------------------------------------------

    def test_comment_line_parsed_as_comment_stmt(self) -> None:
        result = parse_equations_block(_fmfl("  # hello world\n"))
        self.assertEqual(result, [CommentStmt("hello world")])

    def test_comment_without_space_after_hash(self) -> None:
        result = parse_equations_block(_fmfl("  #nospace\n"))
        self.assertIsInstance(result[0], CommentStmt)

    def test_fmu_step_comment_is_comment_stmt(self) -> None:
        result = parse_equations_block(_fmfl("  # bb: FMU step (runtime:fmu plugin)\n"))
        self.assertEqual(result, [CommentStmt("bb: FMU step (runtime:fmu plugin)")])

    # ------------------------------------------------------------------
    # Name expressions
    # ------------------------------------------------------------------

    def test_simple_name_assignment(self) -> None:
        result = parse_equations_block(_fmfl("  out = speed\n"))
        self.assertEqual(len(result), 1)
        stmt = result[0]
        self.assertIsInstance(stmt, AssignStmt)
        assert isinstance(stmt, AssignStmt)
        self.assertEqual(stmt.target, "out")
        self.assertIsInstance(stmt.rhs, NameExpr)
        assert isinstance(stmt.rhs, NameExpr)
        self.assertEqual(stmt.rhs.name, "speed")

    def test_dotted_name_assignment(self) -> None:
        result = parse_equations_block(_fmfl("  out = fmu1.h\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt) and isinstance(stmt.rhs, NameExpr)
        self.assertEqual(stmt.rhs.name, "fmu1.h")

    def test_path_name_at_prefix(self) -> None:
        result = parse_equations_block(_fmfl("  x = @dataset.signal.value\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt) and isinstance(stmt.rhs, NameExpr)
        self.assertTrue(stmt.rhs.name.startswith("@"))

    # ------------------------------------------------------------------
    # prev() expressions
    # ------------------------------------------------------------------

    def test_prev_expression(self) -> None:
        result = parse_equations_block(_fmfl("  x = prev(y)\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt)
        self.assertIsInstance(stmt.rhs, PrevExpr)
        assert isinstance(stmt.rhs, PrevExpr)
        self.assertIsInstance(stmt.rhs.inner, NameExpr)
        assert isinstance(stmt.rhs.inner, NameExpr)
        self.assertEqual(stmt.rhs.inner.name, "y")

    # ------------------------------------------------------------------
    # Binary expressions
    # ------------------------------------------------------------------

    def test_binop_addition(self) -> None:
        result = parse_equations_block(_fmfl("  z = a + b\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt)
        rhs = stmt.rhs
        self.assertIsInstance(rhs, BinOpExpr)
        assert isinstance(rhs, BinOpExpr)
        self.assertEqual(rhs.op, "+")
        self.assertIsInstance(rhs.left, NameExpr)
        self.assertIsInstance(rhs.right, NameExpr)

    def test_binop_subtraction(self) -> None:
        r = parse_equations_block(_fmfl("  z = a - b\n"))[0]
        assert isinstance(r, AssignStmt) and isinstance(r.rhs, BinOpExpr)
        self.assertEqual(r.rhs.op, "-")

    def test_binop_multiplication(self) -> None:
        r = parse_equations_block(_fmfl("  z = a * b\n"))[0]
        assert isinstance(r, AssignStmt) and isinstance(r.rhs, BinOpExpr)
        self.assertEqual(r.rhs.op, "*")

    def test_binop_division(self) -> None:
        r = parse_equations_block(_fmfl("  z = a / b\n"))[0]
        assert isinstance(r, AssignStmt) and isinstance(r.rhs, BinOpExpr)
        self.assertEqual(r.rhs.op, "/")

    # ------------------------------------------------------------------
    # Function call expressions
    # ------------------------------------------------------------------

    def test_param_scalar_call(self) -> None:
        result = parse_equations_block(_fmfl("  x = param_scalar(ref1)\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt)
        self.assertIsInstance(stmt.rhs, CallExpr)
        assert isinstance(stmt.rhs, CallExpr)
        self.assertEqual(stmt.rhs.func, "param_scalar")
        self.assertEqual(len(stmt.rhs.args), 1)
        self.assertIsInstance(stmt.rhs.args[0], NameExpr)

    def test_curve_lookup_call(self) -> None:
        result = parse_equations_block(_fmfl("  y = curve_lookup(kl1, x)\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt) and isinstance(stmt.rhs, CallExpr)
        self.assertEqual(stmt.rhs.func, "curve_lookup")
        self.assertEqual(len(stmt.rhs.args), 2)

    def test_map_lookup_call(self) -> None:
        result = parse_equations_block(_fmfl("  z = map_lookup(kf1, x, y)\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt) and isinstance(stmt.rhs, CallExpr)
        self.assertEqual(stmt.rhs.func, "map_lookup")
        self.assertEqual(len(stmt.rhs.args), 3)

    def test_unknown_function_call_parsed(self) -> None:
        result = parse_equations_block(_fmfl("  z = unknown_fn(a, b)\n"))
        stmt = result[0]
        assert isinstance(stmt, AssignStmt) and isinstance(stmt.rhs, CallExpr)
        self.assertEqual(stmt.rhs.func, "unknown_fn")

    # ------------------------------------------------------------------
    # Multiple statements
    # ------------------------------------------------------------------

    def test_multiple_statements_order_preserved(self) -> None:
        doc = _fmfl("  # header comment\n  a = b\n  c = d + e\n")
        result = parse_equations_block(doc)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], CommentStmt)
        self.assertIsInstance(result[1], AssignStmt)
        self.assertIsInstance(result[2], AssignStmt)

    # ------------------------------------------------------------------
    # Block termination
    # ------------------------------------------------------------------

    def test_block_ends_at_unindented_line(self) -> None:
        doc = "equations:\n  x = y\nnext_section:\n  ignored\n"
        result = parse_equations_block(doc)
        self.assertEqual(len(result), 1)

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    def test_invalid_expression_raises(self) -> None:
        with self.assertRaises(FmflParseError):
            parse_equations_block(_fmfl("  x = (unclosed\n"))

    def test_invalid_assignment_raises(self) -> None:
        with self.assertRaises(FmflParseError):
            parse_equations_block(_fmfl("  not valid syntax here\n"))

    def test_prev_of_non_name_raises(self) -> None:
        # prev() only wraps bare names in Stage-1 output; nested prev is invalid
        with self.assertRaises(FmflParseError):
            parse_equations_block(_fmfl("  x = a + prev(b)\n"))


if __name__ == "__main__":
    unittest.main()
