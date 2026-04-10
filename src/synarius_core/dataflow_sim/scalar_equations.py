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

from .compiler import CompiledDataflow, elementary_has_fmu_path, unpack_wire_ref

if TYPE_CHECKING:
    pass


def scalar_ws_read_step(
    workspace: MutableMapping[object, float],
    committed: Mapping[object, float] | None,
    raw: object,
    *,
    node_by_id: dict[UUID, ElementaryInstance],
    workspace_key_uid: dict[UUID, UUID],
    use_previous: bool,
) -> float:
    """Read one operand; ``use_previous`` selects the snapshot taken at step start (delayed feedback)."""
    if raw is None:
        return 0.0
    src_id, src_pin = unpack_wire_ref(raw)
    src_node = node_by_id.get(src_id)
    bucket: Mapping[object, float] = (
        committed if (use_previous and committed is not None) else workspace
    )
    if isinstance(src_node, ElementaryInstance) and elementary_has_fmu_path(src_node):
        return float(bucket.get((src_id, src_pin), 0.0))
    sk = workspace_key_uid.get(src_id, src_id)
    return float(bucket.get(sk, 0.0))


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
    workspace: MutableMapping[object, float],
    compiled: CompiledDataflow,
    *,
    stimmed: AbstractSet[UUID],
    fmu_step: Callable[[UUID], None] | None = None,
    workspace_committed: Mapping[object, float] | None = None,
) -> None:
    """
    Walk ``compiled.topo_order`` and update ``workspace`` in place.

    * **Variable** with incoming edge: copy from source (unless ``uid`` is in ``stimmed``).
    * **BasicOperator**: combine ``in1`` / ``in2`` via :func:`eval_basic_operator`.
    * **FMU** diagram node: call ``fmu_step(uid)`` if provided; otherwise leave slot unchanged.

    ``workspace_committed`` — snapshot at step start (before stimulation) used only when reading
    **feedback edges** (``compiled.feedback_edges``); omit for purely acyclic graphs.

    ``workspace`` must be the same mapping used as ``ctx.scalar_workspace`` when ``fmu_step`` reads
    or writes FMU-related entries (including ``(node_id, pin)`` keys where applicable).
    """
    incoming = compiled.incoming
    nb = compiled.node_by_id
    wk = compiled.workspace_key_uid or {}
    fb = compiled.feedback_edges
    for uid in compiled.topo_order:
        node = nb.get(uid)
        if node is None:
            continue
        slot = wk.get(uid, uid)
        if isinstance(node, ElementaryInstance) and elementary_has_fmu_path(node):
            if fmu_step is not None:
                fmu_step(uid)
            continue
        if isinstance(node, BasicOperator):
            pins = incoming.get(uid, {})
            w1, w2 = pins.get("in1"), pins.get("in2")
            if w1 is None or w2 is None:
                continue
            a_id, _ = unpack_wire_ref(w1)
            b_id, _ = unpack_wire_ref(w2)
            a = scalar_ws_read_step(
                workspace,
                workspace_committed,
                w1,
                node_by_id=nb,
                workspace_key_uid=wk,
                use_previous=(a_id, uid, "in1") in fb,
            )
            b = scalar_ws_read_step(
                workspace,
                workspace_committed,
                w2,
                node_by_id=nb,
                workspace_key_uid=wk,
                use_previous=(b_id, uid, "in2") in fb,
            )
            workspace[slot] = eval_basic_operator(node, a, b)
        elif isinstance(node, Variable):
            if uid in stimmed:
                continue
            pins = incoming.get(uid, {})
            if "in" in pins:
                raw = pins["in"]
                sid, _ = unpack_wire_ref(raw)
                workspace[slot] = scalar_ws_read_step(
                    workspace,
                    workspace_committed,
                    raw,
                    node_by_id=nb,
                    workspace_key_uid=wk,
                    use_previous=(sid, uid, "in") in fb,
                )


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
    apply_scalar_equations_topo(
        candidate,
        compiled,
        stimmed=stimmed,
        fmu_step=fmu_step,
        workspace_committed=committed,
    )
