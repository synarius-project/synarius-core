"""Shared lowering from :class:`~.compiler.CompiledDataflow` to FMFL text and Python kernel text.

Stage 1 is graph → ``CompiledDataflow`` (see :class:`~.compiler.DataflowCompilePass`). This module
implements **stage 2a**: parallel emission of FMFL and Python from the same lowered step list so
Studio views stay semantically aligned (v0.2 execution view comments). A full **FMFL → AST → Python**
pipeline is not implemented here (library ``.fmfl`` parsing is future work).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from synarius_core.model import BasicOperator, BasicOperatorType, ElementaryInstance, Variable

from .compiler import CompiledDataflow, elementary_has_fmu_path, unpack_wire_ref
from .equation_walk import (
    EqFmu,
    EqGeneric,
    EqOperator,
    EqOperatorIncomplete,
    EqStdArithmetic,
    EqVarNoInput,
    EqVarWire,
    iter_equation_items,
    iter_init_variables,
)


def _label(node: ElementaryInstance) -> str:
    try:
        return str(node.name)
    except Exception:
        return "node"


def _src_expr(node_by_id: dict[UUID, ElementaryInstance], src_id: UUID, src_pin: str) -> str:
    src = node_by_id.get(src_id)
    if src is None:
        return "?"
    if isinstance(src, Variable):
        return _label(src)
    if isinstance(src, BasicOperator):
        return f"{_label(src)}"
    if isinstance(src, ElementaryInstance) and elementary_has_fmu_path(src):
        sp = str(src_pin or "out")
        return f"{_label(src)}.{sp}"
    return _label(src)


def _op_symbol(op: BasicOperator) -> str:
    m = {
        BasicOperatorType.PLUS: "+",
        BasicOperatorType.MINUS: "-",
        BasicOperatorType.MULTIPLY: "*",
        BasicOperatorType.DIVIDE: "/",
    }
    return m.get(op.operation, "?")


@dataclass(frozen=True)
class _EquationLine:
    """One line under ``equations:`` in the FMFL-shaped listing."""

    text: str


def _collect_equation_lines(compiled: CompiledDataflow) -> tuple[list[tuple[str, float]], list[_EquationLine]]:
    """Return ``init`` assignments for variables (label, value) and ordered FMFL equation lines."""
    nb = compiled.node_by_id
    init_pairs = [(iv.name, iv.value) for iv in iter_init_variables(compiled)]
    lines: list[_EquationLine] = []

    for ev in iter_equation_items(compiled):
        if isinstance(ev, EqVarWire):
            rhs = _src_expr(nb, ev.src_id, ev.src_pin)
            if ev.read_src_from_previous:
                rhs = f"prev({rhs})"
            lines.append(_EquationLine(f"  {ev.target_label} = {rhs}"))
        elif isinstance(ev, EqVarNoInput):
            lines.append(
                _EquationLine(f"  # {ev.target_label}: no incoming edge (initial value / stimulation)")
            )
        elif isinstance(ev, EqOperatorIncomplete):
            lines.append(_EquationLine(f"  # {ev.target_label}: operator with incomplete inputs"))
        elif isinstance(ev, EqOperator):
            a_id, a_pin = unpack_wire_ref(ev.in1)
            b_id, b_pin = unpack_wire_ref(ev.in2)
            a = _src_expr(nb, a_id, a_pin)
            b = _src_expr(nb, b_id, b_pin)
            if ev.in1_from_previous:
                a = f"prev({a})"
            if ev.in2_from_previous:
                b = f"prev({b})"
            sym = _op_symbol(ev.op)
            lines.append(_EquationLine(f"  {ev.target_label} = {a} {sym} {b}"))
        elif isinstance(ev, EqStdArithmetic):
            a_id, a_pin = unpack_wire_ref(ev.in0)
            b_id, b_pin = unpack_wire_ref(ev.in1)
            a = _src_expr(nb, a_id, a_pin)
            b = _src_expr(nb, b_id, b_pin)
            if ev.in0_from_previous:
                a = f"prev({a})"
            if ev.in1_from_previous:
                b = f"prev({b})"
            lines.append(_EquationLine(f"  {ev.target_label} = {a} {ev.op_symbol} {b}"))
        elif isinstance(ev, EqFmu):
            lines.append(_EquationLine(f"  # {ev.target_label}: FMU step (runtime:fmu plugin)"))
        elif isinstance(ev, EqGeneric):
            lines.append(_EquationLine(f"  # {ev.target_label}: generic block (not evaluated by simple_scalar core)"))

    return init_pairs, lines


def _runtime_scalar_equations_source() -> str:
    """Source of the functions executed for the equations phase (same as :class:`~.engine.SimpleRunEngine`)."""
    from . import scalar_equations as se

    try:
        ev = inspect.getsource(se.eval_basic_operator)
        ap = inspect.getsource(se.apply_scalar_equations_topo)
    except (OSError, TypeError):
        return (
            "# (Could not load source via inspect.getsource — see synarius_core.dataflow_sim.scalar_equations)\n"
        )
    return f"{ev}\n\n{ap}\n"


def _diagram_uuid_comment_table(compiled: CompiledDataflow) -> str:
    nb = compiled.node_by_id
    rows = ["# Diagram node ids (UUID keys in the scalar workspace dict)", ""]
    for uid, node in sorted(nb.items(), key=lambda x: str(x[1].name) if hasattr(x[1], "name") else str(x[0])):
        try:
            lbl = _label(node)
        except Exception:
            lbl = "node"
        rows.append(f"#   {lbl!r} -> {uid!r}")
    return "\n".join(rows) + "\n"


def _fmfl_header_v02(dt_s: float) -> list[str]:
    return [
        "# v0.2 execution view (informative comments; see execution_semantics_v0_2)",
        "# [NORMATIVE] Logical step advances by the model-declared step for periodic mode.",
        f"# periodic: logical step size = {dt_s!r} s (mapping to physical time is [OUT-OF-SCOPE]).",
    ]


def _fmfl_cycle_document(dt_s: float, diagnostics: Sequence[str]) -> str:
    lines = [
        "fmfl 0.1",
        "",
        *_fmfl_header_v02(dt_s),
        "# [NORMATIVE] Cycle classification: cyclic dependencies (directed cycle in dependency graph).",
        "# No valid acyclic CompiledDataflow — equations block intentionally omitted.",
    ]
    for d in diagnostics:
        if "cycle" in d.lower():
            lines.append(f"# compiler: {d}")
            break
    else:
        if diagnostics:
            lines.append(f"# compiler: {diagnostics[0]}")
        else:
            lines.append("# compiler: Dataflow graph has a cycle; simulation is undefined.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _python_cycle_document(diagnostics: Sequence[str]) -> str:
    lines = [
        '"""Generated scalar step kernel (invalid graph — cycle).',
        "",
        "Runtime execution uses SimpleRunEngine; this fragment is not runnable for a cyclic graph.",
        '"""',
        "",
        "# [NORMATIVE] cyclic dependencies — no topological order for equations.",
    ]
    for d in diagnostics:
        if "cycle" in d.lower():
            lines.append(f"# {d}")
            break
    else:
        if diagnostics:
            lines.append(f"# {diagnostics[0]}")
        else:
            lines.append("# Dataflow graph has a cycle.")
    lines.extend(
        [
            "",
            "def step_equations(committed, candidate) -> None:",
            "    raise RuntimeError('invalid dataflow (cycle)')",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_fmfl_document(
    compiled: CompiledDataflow | None,
    *,
    dt_s: float = 0.02,
    diagnostics: Sequence[str] = (),
) -> str:
    """Emit FMFL-shaped text for the compiled scalar dataflow (informative; not a full FMFL compiler)."""
    if compiled is None:
        return _fmfl_cycle_document(dt_s, diagnostics)

    init_pairs, eq_lines = _collect_equation_lines(compiled)
    lines: list[str] = [
        "fmfl 0.1",
        "",
        *_fmfl_header_v02(dt_s),
        "",
        "init:",
    ]
    if init_pairs:
        for name, val in sorted(init_pairs, key=lambda p: p[0]):
            lines.append(f"  {name} = {val!r}")
    else:
        lines.append("  pass")

    lines.extend(["", "equations:"])
    for el in eq_lines:
        lines.append(el.text)
    return "\n".join(lines) + "\n"


def generate_python_kernel_document(
    compiled: CompiledDataflow | None,
    *,
    dt_s: float = 0.02,
    diagnostics: Sequence[str] = (),
) -> str:
    """Emit the **actual** Python source of the scalar equations phase (``inspect.getsource``)."""
    if compiled is None:
        return _python_cycle_document(diagnostics)

    header = [
        '"""Python: equations phase of the scalar dataflow (same source as runtime).',
        "",
        ":func:`~synarius_core.dataflow_sim.scalar_equations.apply_scalar_equations_topo` is what",
        ":meth:`synarius_core.dataflow_sim.engine.SimpleRunEngine.step` runs after stimulation,",
        "in-place on the engine workspace (``ctx.scalar_workspace``).",
        "",
        f"Logical step size (periodic): dt_s = {dt_s!r} s — mapping to physical time is [OUT-OF-SCOPE].",
        "",
        "Optional two-dict narrative (v0.2 commit discipline): shallow-copy committed to candidate,",
        "then run the same walk on candidate — see :func:`~synarius_core.dataflow_sim.scalar_equations.commit_candidate_workspace`.",
        '"""',
        "",
        _diagram_uuid_comment_table(compiled),
        "# --- source: synarius_core.dataflow_sim.scalar_equations ---",
        "",
        _runtime_scalar_equations_source(),
        "# --- orchestration in SimpleRunEngine.step (reference) ---",
        "# 1. Advance ctx.time_s; apply stimulation to stimulated Variable slots in workspace.",
        "# 2. apply_scalar_equations_topo(workspace, compiled, stimmed=stimmed, fmu_step=engine._invoke_runtime_fmu_step)",
        "# 3. Optional legacy FMU hook; copy workspace to Variable.value on diagram variables.",
        "",
    ]
    return "\n".join(header)
