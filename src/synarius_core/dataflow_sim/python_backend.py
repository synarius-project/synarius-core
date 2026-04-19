"""Python code-generation backend for the default profile ``"python_float64"``.

Implements :class:`~.codegen_backend.FmflCodegenBackend` and converts a
parsed FMFL equations AST into a ``run_equations(exchange: RunStepExchange)``
Python function.

**Workspace keys are human-readable label strings** — not UUID hex constants.
UUID constants appear only for param-cache lookups (``std.Kennwert``,
``std.Kennlinie``, ``std.Kennfeld``), keyed by the node label.

No import from ``equation_walk``, ``compiler``, or any ``Eq*`` dataclass
appears in this module.  All semantic information is read from the FMFL AST.

References: ``codegen_stage2_concept.rst`` §3.3.5.
"""

from __future__ import annotations

import re
from uuid import UUID

from .codegen_backend import CodegenContext, FmflCodegenBackend
from .fmfl_parser import (
    AssignStmt,
    BinOpExpr,
    CallExpr,
    CommentStmt,
    Expr,
    FmflParseError,
    NameExpr,
    PrevExpr,
)

PROFILE_ID = "python_float64"

# Constant prefix for param-node UUID identifiers in the generated file.
_PARAM_PREFIX = "_P_"
# Constant prefix for FMU-node UUID identifiers in the generated file.
_FMU_PREFIX = "_FMU_"

_FMU_STEP_RE = re.compile(r"^(.+?): FMU step \(runtime:fmu plugin\)$")


class PythonBackend(FmflCodegenBackend):
    """Backend for profile ``"python_float64"``.

    Emits a ``run_equations(exchange: RunStepExchange) -> None`` function
    whose workspace and stimmed set use human-readable label strings as keys.

    References: ``codegen_stage2_concept.rst`` §3.3.5.
    """

    # ------------------------------------------------------------------
    # FmflCodegenBackend interface
    # ------------------------------------------------------------------

    def emit_header(self, ctx: CodegenContext) -> str:
        """Return the file header: docstring, imports, param-UUID constants."""
        _check_profile(ctx)
        lines: list[str] = [
            '"""Unrolled scalar equations for one step (host applies stimulation before this runs)."""',
            "",
            "from __future__ import annotations",
            "",
            "from uuid import UUID",
            "",
            "from synarius_core.dataflow_sim.step_exchange import RunStepExchange",
        ]

        # Param-node imports: lookup_ops only when at least one param node exists.
        param_labels = _param_label_to_uuid(ctx)
        if param_labels:
            lines += [
                "from synarius_core.dataflow_sim.lookup_ops import (",
                "    syn_curve_lookup_linear_clamp,",
                "    syn_map_lookup_bilinear_clamp,",
                ")",
            ]

        # UUID constants for param-cache lookups — only for param nodes.
        if param_labels:
            lines += ["", "# Param-node UUIDs (param-cache lookup keys)"]
            for label, uid in sorted(param_labels.items()):
                lines.append(f"{_PARAM_PREFIX}{label} = UUID({str(uid)!r})")

        # UUID constants for FMU step dispatch — only for FMU nodes.
        fmu_labels = _fmu_label_to_uuid(ctx)
        if fmu_labels:
            lines += ["", "# FMU-node UUIDs (fmu_step dispatch keys)"]
            for label, uid in sorted(fmu_labels.items()):
                lines.append(f"{_FMU_PREFIX}{label} = UUID({str(uid)!r})")

        return "\n".join(lines)

    def emit_statement(
        self,
        stmt: AssignStmt | CommentStmt,
        ctx: CodegenContext,
    ) -> list[str]:
        """Return source lines for one FMFL statement."""
        _check_profile(ctx)
        if isinstance(stmt, CommentStmt):
            m = _FMU_STEP_RE.match(stmt.text)
            if m:
                return _emit_fmu_step_call(m.group(1), ctx)
            return [f"# {stmt.text}"] if stmt.text else ["#"]
        return _emit_assign(stmt, ctx)

    def emit_footer(self, ctx: CodegenContext) -> str:
        """Return the function closing lines."""
        _check_profile(ctx)
        return ""  # function body is complete after last statement


# ------------------------------------------------------------------
# run_equations function header — emitted once by the orchestrator
# ------------------------------------------------------------------

def emit_function_header(ctx: CodegenContext) -> list[str]:
    """Return the ``def run_equations`` signature and workspace setup lines."""
    param_labels = _param_label_to_uuid(ctx)
    fmu_labels   = _fmu_label_to_uuid(ctx)
    needs_prev   = _fmfl_has_prev(ctx.fmfl_text)

    lines = [
        "",
        "",
        "def run_equations(exchange: RunStepExchange) -> None:",
        '    """One equations pass: stimulation is applied by the host before this runs."""',
        "    ws      = exchange.workspace",
        "    stimmed = exchange.stimmed",
    ]
    if needs_prev:
        lines += [
            "    w_prev = exchange.workspace_previous",
            "    if w_prev is None:",
            "        raise RuntimeError(",
            "            'workspace_previous is required when the graph has delayed feedback edges'",
            "        )",
        ]
    if param_labels:
        lines.append("    _pc = exchange.param_cache or {}")
    if fmu_labels:
        lines.append("    _fmu_step = exchange.fmu_step")
    return lines


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _check_profile(ctx: CodegenContext) -> None:
    if ctx.profile != PROFILE_ID:
        raise FmflParseError(
            f"PythonBackend only supports profile {PROFILE_ID!r}, got {ctx.profile!r}"
        )


def _param_label_to_uuid(ctx: CodegenContext) -> dict[str, UUID]:
    """Return ``{label: uuid}`` for all param-bound nodes."""
    reverse = {v: k for k, v in ctx.node_labels.items()}
    return {
        lbl: uid
        for lbl, uid in (
            (lbl, reverse.get(lbl))
            for lbl in (ctx.node_labels.get(uid, "") for uid in ctx.param_node_ids)
        )
        if uid is not None
    }


def _fmu_label_to_uuid(ctx: CodegenContext) -> dict[str, UUID]:
    """Return ``{label: uuid}`` for all FMU diagram nodes."""
    return {
        lbl: uid
        for uid in ctx.fmu_node_ids
        if (lbl := ctx.node_labels.get(uid)) is not None
    }


def _emit_fmu_step_call(node_label: str, ctx: CodegenContext) -> list[str]:
    """Emit ``exchange.fmu_step(UUID(...))`` for an FMU step comment."""
    fmu_labels = _fmu_label_to_uuid(ctx)
    if node_label not in fmu_labels:
        return [f"    # fmu_step: unknown label {node_label!r} — skipped"]
    return [
        "    if _fmu_step is not None:",
        f"        _fmu_step({_FMU_PREFIX}{node_label})",
        "",
    ]


def _fmfl_has_prev(fmfl_text: str) -> bool:
    return "prev(" in fmfl_text


def _ws_read(name: str, use_prev: bool) -> str:
    """Emit a workspace read for *name*."""
    bucket = "w_prev" if use_prev else "ws"
    return f"float({bucket}.get({name!r}, 0.0))"


def _render_expr(expr: Expr, ctx: CodegenContext, tmp: list[int]) -> tuple[list[str], str]:
    """Render *expr* to ``(pre_lines, inline_str)``.

    *pre_lines* contains any temporary variable assignments needed before the
    inline expression can be used.
    """
    if isinstance(expr, NameExpr):
        return [], _ws_read(expr.name, use_prev=False)

    if isinstance(expr, PrevExpr):
        inner = expr.inner
        if isinstance(inner, NameExpr):
            return [], _ws_read(inner.name, use_prev=True)
        raise FmflParseError(f"prev() must wrap a bare name, got {inner!r}")

    if isinstance(expr, BinOpExpr):
        pre_l, la = _render_expr(expr.left,  ctx, tmp)
        pre_r, ra = _render_expr(expr.right, ctx, tmp)
        pre = pre_l + pre_r
        if expr.op == "/":
            i = tmp[0]
            tmp[0] += 1
            ta, tb = f"_a{i}", f"_b{i}"
            pre += [
                f"    {ta} = {la}",
                f"    {tb} = {ra}",
            ]
            return pre, f"(float('nan') if abs({tb}) < 1e-15 else {ta} / {tb})"
        return pre, f"({la} {expr.op} {ra})"

    if isinstance(expr, CallExpr):
        return _render_call(expr, ctx, tmp)

    raise FmflParseError(f"unknown expression type: {type(expr).__name__}")


def _render_call(expr: CallExpr, ctx: CodegenContext, tmp: list[int]) -> tuple[list[str], str]:
    """Render a ``CallExpr`` to ``(pre_lines, inline_str)``."""
    func = expr.func
    args = expr.args

    if func == "param_scalar":
        if len(args) != 1:
            raise FmflParseError(f"param_scalar expects 1 argument, got {len(args)}")
        ref = _extract_name(args[0])
        # ref is the label of the param node
        return [], f"float(_pc.get({_PARAM_PREFIX}{ref}, 0.0))"

    if func == "curve_lookup":
        if len(args) != 2:
            raise FmflParseError(f"curve_lookup expects 2 arguments, got {len(args)}")
        ref = _extract_name(args[0])
        _, x_expr = _render_expr(args[1], ctx, tmp)
        pre: list[str] = []
        i = tmp[0]
        tmp[0] += 1
        kl = f"_kl{i}"
        pre += [
            f"    {kl} = _pc.get({_PARAM_PREFIX}{ref})",
            f"    if {kl} is None:",
            f"        _kl_result{i} = 0.0",
            "    else:",
            f"        _kl_result{i} = syn_curve_lookup_linear_clamp({kl}[0], {kl}[1], {x_expr})",
        ]
        return pre, f"_kl_result{i}"

    if func == "map_lookup":
        if len(args) != 3:
            raise FmflParseError(f"map_lookup expects 3 arguments, got {len(args)}")
        ref = _extract_name(args[0])
        _, x_expr = _render_expr(args[1], ctx, tmp)
        _, y_expr = _render_expr(args[2], ctx, tmp)
        pre = []
        i = tmp[0]
        tmp[0] += 1
        km = f"_km{i}"
        pre += [
            f"    {km} = _pc.get({_PARAM_PREFIX}{ref})",
            f"    if {km} is None:",
            f"        _km_result{i} = 0.0",
            "    else:",
            f"        _km_result{i} = syn_map_lookup_bilinear_clamp({km}[0], {km}[1], {km}[2], {x_expr}, {y_expr})",
        ]
        return pre, f"_km_result{i}"

    # Unknown function: emit as comment + zero
    return [f"    # unsupported call: {func}(...)"], "0.0"


def _extract_name(expr: Expr) -> str:
    """Extract the string name from a NameExpr (param reference)."""
    if isinstance(expr, NameExpr):
        return expr.name
    raise FmflParseError(f"expected name expression for parameter reference, got {type(expr).__name__}")


def _emit_assign(stmt: AssignStmt, ctx: CodegenContext) -> list[str]:
    """Return Python lines for one ``AssignStmt``."""
    tmp: list[int] = [0]
    pre, rhs = _render_expr(stmt.rhs, ctx, tmp)
    target = stmt.target
    slot   = f"ws[{target!r}]"

    if target in ctx.variable_labels:
        # Variable node: wrap in stimulation guard
        guard_lines = [f"    if {target!r} not in stimmed:"]
        # Indent pre-lines inside the guard
        indented_pre = [
            ("        " + ln.lstrip()) if ln.strip() else ln
            for ln in pre
        ]
        return guard_lines + indented_pre + [f"        {slot} = {rhs}", ""]
    else:
        return pre + [f"    {slot} = {rhs}", ""]
