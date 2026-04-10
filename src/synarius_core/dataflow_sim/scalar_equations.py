"""Topological scalar evaluation for a :class:`~.compiler.CompiledDataflow`.

This is the **equations-phase** kernel shared by :class:`~.engine.SimpleRunEngine` and Studio
codegen: same logic, in-place on the workspace mapping. Stimulation is applied **before** calling
:func:`apply_scalar_equations_topo` (see :meth:`~.engine.SimpleRunEngine.step`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import TYPE_CHECKING, AbstractSet
from uuid import UUID

from synarius_core.model import BasicOperator, BasicOperatorType, ElementaryInstance, Variable

from .compiler import CompiledDataflow, elementary_has_fmu_path, scalar_ws_read

if TYPE_CHECKING:
    pass


def eval_basic_operator(op: BasicOperator, a: float, b: float) -> float:
    """Scalar binary operator used by the dataflow runtime and tests."""
    if op.operation == BasicOperatorType.PLUS:
        return a + b
    if op.operation == BasicOperatorType.MINUS:
        return a - b
    if op.operation == BasicOperatorType.MULTIPLY:
        return a * b
    if op.operation == BasicOperatorType.DIVIDE:
        if abs(b) < 1e-15:
            return float("nan")
        return a / b
    return float("nan")


def apply_scalar_equations_topo(
    workspace: MutableMapping[UUID, float],
    compiled: CompiledDataflow,
    *,
    stimmed: AbstractSet[UUID],
    fmu_step: Callable[[UUID], None] | None = None,
) -> None:
    """
    Walk ``compiled.topo_order`` and update ``workspace`` in place.

    * **Variable** with incoming edge: copy from source (unless ``uid`` is in ``stimmed``).
    * **BasicOperator**: combine ``in1`` / ``in2`` via :func:`eval_basic_operator`.
    * **FMU** diagram node: call ``fmu_step(uid)`` if provided; otherwise leave slot unchanged.

    ``workspace`` must be the same mapping used as ``ctx.scalar_workspace`` when ``fmu_step`` reads
    or writes FMU-related entries (including ``(node_id, pin)`` keys where applicable).
    """
    incoming = compiled.incoming
    nb = compiled.node_by_id
    for uid in compiled.topo_order:
        node = nb.get(uid)
        if node is None:
            continue
        if isinstance(node, ElementaryInstance) and elementary_has_fmu_path(node):
            if fmu_step is not None:
                fmu_step(uid)
            continue
        if isinstance(node, BasicOperator):
            pins = incoming.get(uid, {})
            a = scalar_ws_read(workspace, pins.get("in1"), node_by_id=nb)
            b = scalar_ws_read(workspace, pins.get("in2"), node_by_id=nb)
            workspace[uid] = eval_basic_operator(node, a, b)
        elif isinstance(node, Variable):
            if uid in stimmed:
                continue
            pins = incoming.get(uid, {})
            if "in" in pins:
                raw = pins["in"]
                workspace[uid] = scalar_ws_read(workspace, raw, node_by_id=nb)


def commit_candidate_workspace(
    committed: Mapping[UUID, float],
    candidate: MutableMapping[UUID, float],
    compiled: CompiledDataflow,
    *,
    stimmed: AbstractSet[UUID],
    fmu_step: Callable[[UUID], None] | None = None,
) -> None:
    """
    Two-buffer v0.2 view: read only from ``committed``, write results into ``candidate``.

    Used for documentation / tests; :class:`~.engine.SimpleRunEngine` uses in-place
    :func:`apply_scalar_equations_topo` on a single workspace, which is equivalent for acyclic
    graphs when ``candidate`` is a shallow copy of ``committed`` before the walk (not used by the
    engine).
    """
    candidate.clear()
    candidate.update(committed)
    apply_scalar_equations_topo(candidate, compiled, stimmed=stimmed, fmu_step=fmu_step)
