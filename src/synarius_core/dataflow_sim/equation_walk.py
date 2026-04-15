"""Shared traversal of :class:`~.compiler.CompiledDataflow` for FMFL / codegen (same order as runtime)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator
from uuid import UUID

from synarius_core.model import BasicOperator, ElementaryInstance, Variable

from ._std_type_keys import STD_ARITHMETIC_OP, STD_PARAM_LOOKUP
from .compiler import CompiledDataflow, FeedbackWire, elementary_has_fmu_path, unpack_wire_ref


def _is_feedback(compiled: CompiledDataflow, wire: FeedbackWire) -> bool:
    return wire in compiled.feedback_edges


def label(node: ElementaryInstance) -> str:
    try:
        return str(node.name)
    except Exception:
        return "node"


@dataclass(frozen=True)
class InitVariable:
    name: str
    value: float


@dataclass(frozen=True)
class EqVarWire:
    target_uid: UUID
    target_label: str
    src_id: UUID
    src_pin: str
    read_src_from_previous: bool


@dataclass(frozen=True)
class EqVarNoInput:
    target_uid: UUID
    target_label: str


@dataclass(frozen=True)
class EqOperator:
    target_uid: UUID
    target_label: str
    op: BasicOperator
    in1: object
    in2: object
    in1_from_previous: bool
    in2_from_previous: bool


@dataclass(frozen=True)
class EqOperatorIncomplete:
    target_uid: UUID
    target_label: str


@dataclass(frozen=True)
class EqFmu:
    target_uid: UUID
    target_label: str


@dataclass(frozen=True)
class EqStdArithmetic:
    """Lib element from ``STD_ARITHMETIC_OP``: two inputs ``in0``/``in1``, one output ``out``."""

    target_uid: UUID
    target_label: str
    op_symbol: str
    in0: object
    in1: object
    in0_from_previous: bool
    in1_from_previous: bool


@dataclass(frozen=True)
class EqGeneric:
    target_uid: UUID
    target_label: str


@dataclass(frozen=True)
class EqKennwert:
    """``std.Kennwert``: scalar parameter lookup — no inputs, one output ``out``."""

    target_uid: UUID
    target_label: str
    parameter_ref: str


@dataclass(frozen=True)
class EqKennlinie:
    """``std.Kennlinie``: 1-D curve lookup — input ``x``, output ``out``."""

    target_uid: UUID
    target_label: str
    parameter_ref: str
    in_x: object  # incoming wire-ref for pin "x"
    in_x_from_previous: bool


@dataclass(frozen=True)
class EqKennfeld:
    """``std.Kennfeld``: 2-D map lookup — inputs ``x`` and ``y``, output ``out``."""

    target_uid: UUID
    target_label: str
    parameter_ref: str
    in_x: object  # incoming wire-ref for pin "x"
    in_y: object  # incoming wire-ref for pin "y"
    in_x_from_previous: bool
    in_y_from_previous: bool


EquationItem = (
    EqVarWire
    | EqVarNoInput
    | EqOperator
    | EqOperatorIncomplete
    | EqFmu
    | EqStdArithmetic
    | EqKennwert
    | EqKennlinie
    | EqKennfeld
    | EqGeneric
)


def iter_init_variables(compiled: CompiledDataflow) -> list[InitVariable]:
    out: list[InitVariable] = []
    for uid, node in compiled.node_by_id.items():
        if isinstance(node, Variable):
            try:
                v = float(node.value)
            except (TypeError, ValueError):
                v = 0.0
            out.append(InitVariable(name=label(node), value=v))
    return out


def iter_equation_items(compiled: CompiledDataflow) -> Iterator[EquationItem]:
    """Yield one item per node in ``topo_order`` (same as scalar equations walk)."""
    nb = compiled.node_by_id
    inc = compiled.incoming
    for uid in compiled.topo_order:
        node = nb.get(uid)
        if node is None:
            continue
        if isinstance(node, Variable):
            pins = inc.get(uid, {})
            if "in" in pins:
                raw = pins["in"]
                sid, sp = unpack_wire_ref(raw)
                fb = _is_feedback(compiled, (sid, uid, "in"))
                yield EqVarWire(
                    target_uid=uid,
                    target_label=label(node),
                    src_id=sid,
                    src_pin=sp,
                    read_src_from_previous=fb,
                )
            else:
                yield EqVarNoInput(target_uid=uid, target_label=label(node))
        elif isinstance(node, BasicOperator):
            nm = label(node)
            pins = inc.get(uid, {})
            w1, w2 = pins.get("in1"), pins.get("in2")
            if w1 is None or w2 is None:
                yield EqOperatorIncomplete(target_uid=uid, target_label=nm)
            else:
                a_id, a_pin = unpack_wire_ref(w1)
                b_id, b_pin = unpack_wire_ref(w2)
                yield EqOperator(
                    target_uid=uid,
                    target_label=nm,
                    op=node,
                    in1=w1,
                    in2=w2,
                    in1_from_previous=_is_feedback(compiled, (a_id, uid, "in1")),
                    in2_from_previous=_is_feedback(compiled, (b_id, uid, "in2")),
                )
        elif isinstance(node, ElementaryInstance) and elementary_has_fmu_path(node):
            yield EqFmu(target_uid=uid, target_label=label(node))
        elif isinstance(node, ElementaryInstance) and node.type_key in STD_ARITHMETIC_OP:
            nm = label(node)
            pins = inc.get(uid, {})
            w0, w1 = pins.get("in0"), pins.get("in1")
            if w0 is None or w1 is None:
                yield EqOperatorIncomplete(target_uid=uid, target_label=nm)
            else:
                a_id, _ = unpack_wire_ref(w0)
                b_id, _ = unpack_wire_ref(w1)
                yield EqStdArithmetic(
                    target_uid=uid,
                    target_label=nm,
                    op_symbol=STD_ARITHMETIC_OP[node.type_key],
                    in0=w0,
                    in1=w1,
                    in0_from_previous=_is_feedback(compiled, (a_id, uid, "in0")),
                    in1_from_previous=_is_feedback(compiled, (b_id, uid, "in1")),
                )
        elif isinstance(node, ElementaryInstance) and node.type_key in STD_PARAM_LOOKUP:
            nm = label(node)
            try:
                parameter_ref = str(node.get("parameter_ref") or "").strip()
            except Exception:
                parameter_ref = ""
            pins = inc.get(uid, {})
            tk = node.type_key
            if tk == "std.Kennwert":
                yield EqKennwert(target_uid=uid, target_label=nm, parameter_ref=parameter_ref)
            elif tk == "std.Kennlinie":
                wx = pins.get("x")
                if wx is None:
                    yield EqOperatorIncomplete(target_uid=uid, target_label=nm)
                else:
                    x_id, _ = unpack_wire_ref(wx)
                    yield EqKennlinie(
                        target_uid=uid,
                        target_label=nm,
                        parameter_ref=parameter_ref,
                        in_x=wx,
                        in_x_from_previous=_is_feedback(compiled, (x_id, uid, "x")),
                    )
            elif tk == "std.Kennfeld":
                wx = pins.get("x")
                wy = pins.get("y")
                if wx is None or wy is None:
                    yield EqOperatorIncomplete(target_uid=uid, target_label=nm)
                else:
                    x_id, _ = unpack_wire_ref(wx)
                    y_id, _ = unpack_wire_ref(wy)
                    yield EqKennfeld(
                        target_uid=uid,
                        target_label=nm,
                        parameter_ref=parameter_ref,
                        in_x=wx,
                        in_y=wy,
                        in_x_from_previous=_is_feedback(compiled, (x_id, uid, "x")),
                        in_y_from_previous=_is_feedback(compiled, (y_id, uid, "y")),
                    )
            else:
                yield EqGeneric(target_uid=uid, target_label=nm)
        else:
            yield EqGeneric(target_uid=uid, target_label=label(node))
