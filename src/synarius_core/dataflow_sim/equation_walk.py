"""Shared traversal of :class:`~.compiler.CompiledDataflow` for FMFL / codegen (same order as runtime)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator
from uuid import UUID

from synarius_core.model import BasicOperator, ElementaryInstance, Variable

from .compiler import CompiledDataflow, elementary_has_fmu_path, unpack_wire_ref


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


@dataclass(frozen=True)
class EqOperatorIncomplete:
    target_uid: UUID
    target_label: str


@dataclass(frozen=True)
class EqFmu:
    target_uid: UUID
    target_label: str


@dataclass(frozen=True)
class EqGeneric:
    target_uid: UUID
    target_label: str


EquationItem = (
    EqVarWire | EqVarNoInput | EqOperator | EqOperatorIncomplete | EqFmu | EqGeneric
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
                yield EqVarWire(target_uid=uid, target_label=label(node), src_id=sid, src_pin=sp)
            else:
                yield EqVarNoInput(target_uid=uid, target_label=label(node))
        elif isinstance(node, BasicOperator):
            nm = label(node)
            pins = inc.get(uid, {})
            w1, w2 = pins.get("in1"), pins.get("in2")
            if w1 is None or w2 is None:
                yield EqOperatorIncomplete(target_uid=uid, target_label=nm)
            else:
                yield EqOperator(target_uid=uid, target_label=nm, op=node, in1=w1, in2=w2)
        elif isinstance(node, ElementaryInstance) and elementary_has_fmu_path(node):
            yield EqFmu(target_uid=uid, target_label=label(node))
        else:
            yield EqGeneric(target_uid=uid, target_label=label(node))
