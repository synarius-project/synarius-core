"""Orchestrator: Stage 1 → FMFL → AST → Python step function.

Generates ``run_equations(exchange: RunStepExchange) -> None`` by running the
two-stage pipeline defined in ``codegen_stage2_concept.rst``:

1. **Stage 1** — :func:`~.codegen_kernel.generate_fmfl_document` lowers
   ``CompiledDataflow`` to complete FMFL text.
2. **Stage 2** — :func:`~.fmfl_parser.parse_equations_block` parses the FMFL
   text into an AST; :class:`~.python_backend.PythonBackend` emits Python.

This module contains **no** imports from :mod:`equation_walk`, no access to
any ``Eq*`` dataclass, and no traversal of ``CompiledDataflow`` for semantic
data.  The only ``CompiledDataflow`` fields read here are structural identity
data passed through :class:`~.codegen_backend.CodegenContext` (see §3.4 of
the concept document).
"""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from synarius_core.model import Variable

from .codegen_backend import BuildPolicy, CodegenContext, TargetBinding
from .compiler import elementary_has_fmu_path
from .codegen_kernel import generate_fmfl_document
from .compiler import CompiledDataflow
from .equation_walk import label
from .fmfl_parser import FmflParseError, parse_equations_block
from .python_backend import (
    PROFILE_ID,
    PythonBackend,
    emit_function_header,
)


def generate_unrolled_python_step_document(
    compiled: CompiledDataflow | None,
    *,
    dt_s: float = 0.02,
    diagnostics: Sequence[str] = (),
) -> str:
    """Return UTF-8 source text for ``run_equations(exchange: RunStepExchange) -> None``.

    When *compiled* is ``None`` (cyclic graph), a stub that raises
    ``RuntimeError`` is returned.

    The generated workspace uses **human-readable label strings** as keys,
    matching the label-keyed workspace maintained by
    :class:`~.engine.SimpleRunEngine`.
    """
    if compiled is None:
        return _unrolled_cycle_document(dt_s, diagnostics)

    fmfl_text = generate_fmfl_document(compiled, dt_s=dt_s, diagnostics=diagnostics)
    ctx       = _build_codegen_context(compiled, fmfl_text)
    stmts     = parse_equations_block(fmfl_text)
    backend   = PythonBackend()

    parts: list[str] = [backend.emit_header(ctx)]
    parts += emit_function_header(ctx)
    for stmt in stmts:
        parts.extend(backend.emit_statement(stmt, ctx))

    footer = backend.emit_footer(ctx)
    if footer:
        parts.append(footer)

    # Trim trailing blank lines from the function body before the final newline.
    while parts and parts[-1] == "":
        parts.pop()

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_codegen_context(compiled: CompiledDataflow, fmfl_text: str) -> CodegenContext:
    """Build a :class:`CodegenContext` from *compiled* structural identity data.

    Raises :exc:`~.fmfl_parser.FmflParseError` when two nodes share the same
    label, because label-keyed workspaces require unique labels.
    """
    node_labels: dict[UUID, str] = {}
    seen_labels: dict[str, UUID] = {}

    for uid, node in compiled.node_by_id.items():
        lbl = label(node)
        if lbl in seen_labels:
            raise FmflParseError(
                f"Label collision: nodes {seen_labels[lbl]!r} and {uid!r} "
                f"both have label {lbl!r}. "
                "Stage 1 must guarantee unique labels."
            )
        node_labels[uid] = lbl
        seen_labels[lbl] = uid

    variable_labels: frozenset[str] = frozenset(
        label(node)
        for node in compiled.node_by_id.values()
        if isinstance(node, Variable)
    )

    fmu_node_ids: frozenset[UUID] = frozenset(
        uid
        for uid, node in compiled.node_by_id.items()
        if elementary_has_fmu_path(node)
    )

    return CodegenContext(
        fmfl_text=fmfl_text,
        profile=PROFILE_ID,
        binding=TargetBinding(),
        policy=BuildPolicy(),
        node_labels=node_labels,
        param_node_ids=compiled.param_bound_node_ids,
        variable_labels=variable_labels,
        fmu_node_ids=fmu_node_ids,
    )


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
    lines.extend([
        "",
        "from synarius_core.dataflow_sim.step_exchange import RunStepExchange",
        "",
        "def run_equations(exchange: RunStepExchange) -> None:",
        "    raise RuntimeError('invalid dataflow (cycle)')",
        "",
    ])
    return "\n".join(lines) + "\n"
