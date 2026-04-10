"""Unrolled Python source for one scalar **equations** step (literal operators).

Generated ``run_equations(exchange: RunStepExchange)`` matches the walk in
:func:`~synarius_core.dataflow_sim.scalar_equations.apply_scalar_equations_topo` for the same
``CompiledDataflow``. Stimulation is applied by the host **before** calling ``run_equations``.
"""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from synarius_core.model import BasicOperator, BasicOperatorType, ElementaryInstance

from .compiler import CompiledDataflow, elementary_has_fmu_path, unpack_wire_ref
from .equation_walk import (
    EqFmu,
    EqGeneric,
    EqOperator,
    EqOperatorIncomplete,
    EqVarNoInput,
    EqVarWire,
    iter_equation_items,
)
from .step_exchange import RunStepExchange


def _label(node: ElementaryInstance) -> str:
    try:
        return str(node.name)
    except Exception:
        return "node"


def _nid(uid: UUID) -> str:
    """Stable Python identifier for a node UUID (``N_`` + hex, always valid)."""
    return "N_" + uid.hex


def _read_operand_expr(
    ws: str,
    ws_prev: str | None,
    src_id: UUID,
    src_pin: str,
    nb: dict[UUID, ElementaryInstance],
    names: dict[UUID, str],
    workspace_key_uid: dict[UUID, UUID],
    use_previous: bool,
) -> str:
    """Read operand from ``ws`` or ``ws_prev`` (committed previous step) for delayed feedback."""
    src = nb.get(src_id)
    slot = workspace_key_uid.get(src_id, src_id)
    key_scalar = names[slot]
    bucket = ws_prev if (use_previous and ws_prev is not None) else ws
    if isinstance(src, ElementaryInstance) and elementary_has_fmu_path(src):
        key_fmu = names[src_id]
        return f"float({bucket}.get(({key_fmu}, {src_pin!r}), 0.0))"
    return f"float({bucket}.get({key_scalar}, 0.0))"


def _emit_operator_assign(
    ws: str,
    ws_prev: str | None,
    op: BasicOperator,
    uid: UUID,
    pins: dict,
    nb: dict[UUID, ElementaryInstance],
    names: dict[UUID, str],
    workspace_key_uid: dict[UUID, UUID],
    in1_prev: bool,
    in2_prev: bool,
    tmp_i: list[int],
) -> list[str]:
    w1, w2 = pins.get("in1"), pins.get("in2")
    if w1 is None or w2 is None:
        return [f"    # operator {names[uid]}: incomplete inputs"]
    a_id, a_pin = unpack_wire_ref(w1)
    b_id, b_pin = unpack_wire_ref(w2)
    ra = _read_operand_expr(ws, ws_prev, a_id, a_pin, nb, names, workspace_key_uid, in1_prev)
    rb = _read_operand_expr(ws, ws_prev, b_id, b_pin, nb, names, workspace_key_uid, in2_prev)
    slot = workspace_key_uid.get(uid, uid)
    nk = names[slot]
    if op.operation == BasicOperatorType.PLUS:
        return [f"    {ws}[{nk}] = {ra} + {rb}"]
    if op.operation == BasicOperatorType.MINUS:
        return [f"    {ws}[{nk}] = {ra} - {rb}"]
    if op.operation == BasicOperatorType.MULTIPLY:
        return [f"    {ws}[{nk}] = {ra} * {rb}"]
    if op.operation == BasicOperatorType.DIVIDE:
        tid = tmp_i[0]
        tmp_i[0] += 1
        ta, tb = f"_a{tid}", f"_b{tid}"
        return [
            f"    {ta} = {ra}",
            f"    {tb} = {rb}",
            f"    {ws}[{nk}] = float('nan') if abs({tb}) < 1e-15 else {ta} / {tb}",
        ]
    return [f"    {ws}[{nk}] = float('nan')"]


def generate_unrolled_python_step_document(
    compiled: CompiledDataflow | None,
    *,
    dt_s: float = 0.02,
    diagnostics: Sequence[str] = (),
) -> str:
    """Return UTF-8 text: imports, UUID constants, ``def run_equations(exchange: RunStepExchange) -> None``."""
    if compiled is None:
        return _unrolled_cycle_document(dt_s, diagnostics)

    nb = compiled.node_by_id
    names = {uid: _nid(uid) for uid in nb}
    wk_map = compiled.workspace_key_uid or {}

    const_lines: list[str] = [
        '"""Unrolled scalar equations for one step (host applies stimulation before this runs)."""',
        "",
        "# v0.2 view: equations phase only; logical dt_s (periodic) is informational for the host.",
        f"# dt_s = {dt_s!r}",
        "",
        "from __future__ import annotations",
        "",
        "from uuid import UUID",
        "",
        "from synarius_core.dataflow_sim.step_exchange import RunStepExchange",
        "",
        "# --- diagram node ids (UUID constants) ---",
    ]
    for uid, node in sorted(nb.items(), key=lambda x: (_label(x[1]), str(x[0]))):
        const_lines.append(f"{names[uid]} = UUID({str(uid)!r})  # {_label(node)}")

    needs_prev = bool(compiled.feedback_edges)
    body: list[str] = [
        "",
        "",
        "def run_equations(exchange: RunStepExchange) -> None:",
        '    """One equations pass: same order as apply_scalar_equations_topo."""',
        "    ws = exchange.workspace",
        "    stimmed = exchange.stimmed",
    ]
    if needs_prev:
        body.extend(
            [
                "    w_prev = exchange.workspace_previous",
                "    if w_prev is None:",
                "        raise RuntimeError('workspace_previous is required when the graph has delayed feedback edges')",
            ]
        )
    body.append("")
    tmp_i = [0]
    ws_prev_arg: str | None = "w_prev" if needs_prev else None

    for ev in iter_equation_items(compiled):
        if isinstance(ev, EqFmu):
            body.append(f"    # FMU: {ev.target_label} — host/plugin step")
            body.append("    if exchange.fmu_step is not None:")
            body.append(f"        exchange.fmu_step({names[ev.target_uid]})")
            body.append("")
            continue
        if isinstance(ev, EqOperator):
            pins = compiled.incoming.get(ev.target_uid, {})
            body.extend(
                _emit_operator_assign(
                    "ws",
                    ws_prev_arg,
                    ev.op,
                    ev.target_uid,
                    pins,
                    nb,
                    names,
                    wk_map,
                    ev.in1_from_previous,
                    ev.in2_from_previous,
                    tmp_i,
                )
            )
            body.append("")
            continue
        if isinstance(ev, EqOperatorIncomplete):
            body.append(f"    # operator {names[ev.target_uid]}: incomplete inputs")
            body.append("")
            continue
        if isinstance(ev, EqVarNoInput):
            body.append(f"    # {ev.target_label}: no incoming edge (init / stimulation only)")
            body.append("")
            continue
        if isinstance(ev, EqVarWire):
            rhs = _read_operand_expr(
                "ws",
                ws_prev_arg,
                ev.src_id,
                ev.src_pin,
                nb,
                names,
                wk_map,
                ev.read_src_from_previous,
            )
            diagram_id = names[ev.target_uid]
            slot_key = names[wk_map.get(ev.target_uid, ev.target_uid)]
            body.append(f"    if {diagram_id} not in stimmed:")
            body.append(f"        ws[{slot_key}] = {rhs}")
            body.append("")
            continue
        if isinstance(ev, EqGeneric):
            body.append(f"    # {ev.target_label}: generic block (not evaluated)")
            body.append("")

    # trim trailing blank from last block
    while body and body[-1] == "":
        body.pop()

    return "\n".join(const_lines + body) + "\n"


def _unrolled_cycle_document(dt_s: float, diagnostics: Sequence[str]) -> str:
    lines = [
        '"""No unrolled step: graph has a cycle (no CompiledDataflow)."""',
        "",
        f"# dt_s = {dt_s!r} (informative)",
        "",
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
            "from synarius_core.dataflow_sim.step_exchange import RunStepExchange",
            "",
            "def run_equations(exchange: RunStepExchange) -> None:",
            "    raise RuntimeError('invalid dataflow (cycle)')",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
