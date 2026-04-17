"""Unit tests for python_backend — Stage-2 code-generation backend."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim.codegen_backend import (  # noqa: E402
    BuildPolicy,
    CodegenContext,
    TargetBinding,
)
from synarius_core.dataflow_sim.fmfl_parser import FmflParseError  # noqa: E402
from synarius_core.dataflow_sim.python_backend import (  # noqa: E402
    PROFILE_ID,
    PythonBackend,
    emit_function_header,
)

_PROFILE = PROFILE_ID
_BINDING = TargetBinding()
_POLICY = BuildPolicy()

_UID_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_UID_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _ctx(
    fmfl_text: str = "equations:\n",
    *,
    param_node_ids: frozenset[UUID] | None = None,
    variable_labels: frozenset[str] | None = None,
    fmu_node_ids: frozenset[UUID] | None = None,
    node_labels: dict[UUID, str] | None = None,
) -> CodegenContext:
    return CodegenContext(
        fmfl_text=fmfl_text,
        profile=_PROFILE,
        binding=_BINDING,
        policy=_POLICY,
        node_labels=node_labels or {},
        param_node_ids=param_node_ids or frozenset(),
        variable_labels=variable_labels or frozenset(),
        fmu_node_ids=fmu_node_ids or frozenset(),
    )


def _parse_single(src: str):
    """Parse one FMFL equation line and return the first statement."""
    from synarius_core.dataflow_sim.fmfl_parser import parse_equations_block
    doc = f"equations:\n  {src}\n"
    stmts = parse_equations_block(doc)
    assert len(stmts) == 1, f"expected 1 stmt, got {len(stmts)}"
    return stmts[0]


class EmitHeaderTest(unittest.TestCase):

    def setUp(self) -> None:
        self.backend = PythonBackend()

    def test_minimal_header_has_imports(self) -> None:
        header = self.backend.emit_header(_ctx())
        self.assertIn("from synarius_core.dataflow_sim.step_exchange import RunStepExchange", header)
        self.assertIn("from uuid import UUID", header)

    def test_no_params_no_lookup_import(self) -> None:
        header = self.backend.emit_header(_ctx())
        self.assertNotIn("lookup_ops", header)

    def test_param_node_adds_lookup_import(self) -> None:
        ctx = _ctx(
            param_node_ids=frozenset({_UID_A}),
            node_labels={_UID_A: "kl1"},
        )
        header = self.backend.emit_header(ctx)
        self.assertIn("lookup_ops", header)
        self.assertIn("syn_curve_lookup_linear_clamp", header)
        self.assertIn("syn_map_lookup_bilinear_clamp", header)

    def test_param_node_emits_uuid_constant(self) -> None:
        ctx = _ctx(
            param_node_ids=frozenset({_UID_A}),
            node_labels={_UID_A: "kl1"},
        )
        header = self.backend.emit_header(ctx)
        self.assertIn("_P_kl1 = UUID(", header)
        self.assertIn(str(_UID_A), header)

    def test_fmu_node_emits_fmu_uuid_constant(self) -> None:
        ctx = _ctx(
            fmu_node_ids=frozenset({_UID_B}),
            node_labels={_UID_B: "bb"},
        )
        header = self.backend.emit_header(ctx)
        self.assertIn("_FMU_bb = UUID(", header)
        self.assertIn(str(_UID_B), header)

    def test_wrong_profile_raises(self) -> None:
        ctx = CodegenContext(
            fmfl_text="equations:\n",
            profile="wrong_profile",
            binding=_BINDING,
            policy=_POLICY,
        )
        with self.assertRaises(FmflParseError):
            self.backend.emit_header(ctx)


class EmitStatementCommentTest(unittest.TestCase):

    def setUp(self) -> None:
        self.backend = PythonBackend()
        self.ctx = _ctx()

    def test_plain_comment_emitted(self) -> None:
        stmt = _parse_single("# hello world")
        lines = self.backend.emit_statement(stmt, self.ctx)
        self.assertEqual(lines, ["# hello world"])

    def test_fmu_step_comment_known_label_emits_call(self) -> None:
        stmt = _parse_single("# bb: FMU step (runtime:fmu plugin)")
        ctx = _ctx(
            fmu_node_ids=frozenset({_UID_B}),
            node_labels={_UID_B: "bb"},
            fmfl_text="equations:\n  # bb: FMU step (runtime:fmu plugin)\n",
        )
        lines = self.backend.emit_statement(stmt, ctx)
        combined = "\n".join(lines)
        self.assertIn("_fmu_step", combined)
        self.assertIn("_FMU_bb", combined)

    def test_fmu_step_comment_unknown_label_emits_skip_comment(self) -> None:
        stmt = _parse_single("# bb: FMU step (runtime:fmu plugin)")
        lines = self.backend.emit_statement(stmt, self.ctx)
        self.assertEqual(len(lines), 1)
        self.assertIn("skipped", lines[0])


class EmitStatementAssignTest(unittest.TestCase):

    def setUp(self) -> None:
        self.backend = PythonBackend()
        self.ctx = _ctx()

    def test_simple_name_assignment(self) -> None:
        stmt = _parse_single("out = speed")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertIn("ws['out']", combined)
        self.assertIn("ws.get('speed'", combined)

    def test_binop_addition_assignment(self) -> None:
        stmt = _parse_single("z = a + b")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertIn("ws['z']", combined)
        self.assertIn("+", combined)

    def test_division_emits_nan_guard(self) -> None:
        stmt = _parse_single("z = a / b")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertIn("nan", combined)
        self.assertIn("abs(", combined)

    def test_prev_reads_from_w_prev(self) -> None:
        stmt = _parse_single("x = prev(y)")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertIn("w_prev.get('y'", combined)

    def test_variable_label_emits_stimulation_guard(self) -> None:
        stmt = _parse_single("speed = other")
        ctx = _ctx(variable_labels=frozenset({"speed"}))
        lines = self.backend.emit_statement(stmt, ctx)
        combined = "\n".join(lines)
        self.assertIn("stimmed", combined)
        self.assertIn("'speed' not in stimmed", combined)

    def test_non_variable_no_stimulation_guard(self) -> None:
        stmt = _parse_single("out = speed")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertNotIn("stimmed", combined)


class EmitStatementCallTest(unittest.TestCase):

    def setUp(self) -> None:
        self.backend = PythonBackend()
        self.ctx = _ctx(
            param_node_ids=frozenset({_UID_A}),
            node_labels={_UID_A: "kl1"},
        )

    def test_param_scalar_reads_from_param_cache(self) -> None:
        stmt = _parse_single("x = param_scalar(kl1)")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertIn("_pc.get(_P_kl1", combined)

    def test_curve_lookup_emits_lookup_call(self) -> None:
        stmt = _parse_single("y = curve_lookup(kl1, x)")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertIn("syn_curve_lookup_linear_clamp", combined)
        self.assertIn("_P_kl1", combined)

    def test_map_lookup_emits_bilinear_call(self) -> None:
        ctx = _ctx(
            param_node_ids=frozenset({_UID_A}),
            node_labels={_UID_A: "kf1"},
        )
        stmt = _parse_single("z = map_lookup(kf1, x, y)")
        lines = self.backend.emit_statement(stmt, ctx)
        combined = "\n".join(lines)
        self.assertIn("syn_map_lookup_bilinear_clamp", combined)
        self.assertIn("_P_kf1", combined)

    def test_unknown_call_emits_comment_and_zero(self) -> None:
        stmt = _parse_single("z = unknown_fn(a, b)")
        lines = self.backend.emit_statement(stmt, self.ctx)
        combined = "\n".join(lines)
        self.assertIn("unsupported call", combined)
        self.assertIn("0.0", combined)


class EmitFooterTest(unittest.TestCase):

    def test_footer_is_empty_string(self) -> None:
        backend = PythonBackend()
        self.assertEqual(backend.emit_footer(_ctx()), "")


class EmitFunctionHeaderTest(unittest.TestCase):

    def test_function_header_has_def_line(self) -> None:
        lines = emit_function_header(_ctx())
        combined = "\n".join(lines)
        self.assertIn("def run_equations(", combined)

    def test_no_prev_no_w_prev(self) -> None:
        lines = emit_function_header(_ctx(fmfl_text="equations:\n  x = y\n"))
        combined = "\n".join(lines)
        self.assertNotIn("w_prev", combined)

    def test_prev_in_fmfl_adds_w_prev(self) -> None:
        lines = emit_function_header(_ctx(fmfl_text="equations:\n  x = prev(y)\n"))
        combined = "\n".join(lines)
        self.assertIn("w_prev", combined)
        self.assertIn("workspace_previous", combined)

    def test_param_nodes_add_param_cache_line(self) -> None:
        ctx = _ctx(
            param_node_ids=frozenset({_UID_A}),
            node_labels={_UID_A: "kl1"},
        )
        lines = emit_function_header(ctx)
        combined = "\n".join(lines)
        self.assertIn("_pc = exchange.param_cache", combined)

    def test_fmu_nodes_add_fmu_step_line(self) -> None:
        ctx = _ctx(
            fmu_node_ids=frozenset({_UID_B}),
            node_labels={_UID_B: "bb"},
        )
        lines = emit_function_header(ctx)
        combined = "\n".join(lines)
        self.assertIn("_fmu_step = exchange.fmu_step", combined)

    def test_no_params_no_param_cache_line(self) -> None:
        lines = emit_function_header(_ctx())
        combined = "\n".join(lines)
        self.assertNotIn("_pc", combined)


if __name__ == "__main__":
    unittest.main()
