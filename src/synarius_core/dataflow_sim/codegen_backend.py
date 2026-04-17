"""Backend interface and context for Stage-2 FMFL code generation.

Defines the four-layer :class:`CodegenContext` and the
:class:`FmflCodegenBackend` Protocol that all code-generation backends must
implement.

No semantic data from :class:`~.compiler.CompiledDataflow` may appear here.
``node_labels``, ``param_node_ids``, and ``variable_labels`` are structural
identity data only — see ``codegen_stage2_concept.rst`` §3.3.4 and §3.4.

References: ``codegen_stage2_concept.rst`` §1.3, §3.3.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from .fmfl_parser import AssignStmt, CommentStmt


# ---------------------------------------------------------------------------
# Layer 3 — Target Binding
# ---------------------------------------------------------------------------

@dataclass
class TargetBinding:
    """Platform integration descriptor (Layer 3).

    Identifies the execution environment into which the generated code is
    integrated.  Does not carry numeric precision or semantic information.

    References: ``codegen_stage2_concept.rst`` §1.3.3.
    """
    name: str = "python_default"


# ---------------------------------------------------------------------------
# Layer 4 — Build Policy
# ---------------------------------------------------------------------------

@dataclass
class BuildPolicy:
    """Output configuration descriptor (Layer 4).

    Controls the structure and formatting of the generated artifact.  Has no
    effect on any computed value.

    References: ``codegen_stage2_concept.rst`` §1.3.4.
    """
    name: str = "python_default"


# ---------------------------------------------------------------------------
# CodegenContext
# ---------------------------------------------------------------------------

@dataclass
class CodegenContext:
    """All inputs available to a Stage-2 backend for one code-generation run.

    **Layer assignment**

    * ``fmfl_text`` — Layer 1 (FMFL): the sole semantic input to Stage 2.
    * ``profile``   — Layer 2 (Implementation Profile): realization identifier.
    * ``binding``   — Layer 3 (Target Binding): platform integration descriptor.
    * ``policy``    — Layer 4 (Build Policy): output configuration.

    **Structural identity fields (TEMPORARY — see §3.4 of concept document)**

    These fields are derived from :class:`~.compiler.CompiledDataflow` but
    carry no semantic information.  They are name-binding data only.

    * ``node_labels``     — UUID → human-readable label.  Used for comment
      annotations and to derive the UUID constants for param-cache lookups.
      Must not influence any emitted expression.
    * ``param_node_ids``  — UUIDs of ``std.Kennwert``/``Kennlinie``/``Kennfeld``
      nodes.  Used exclusively to emit UUID constants in the generated file
      header for param-cache key resolution.
    * ``variable_labels`` — labels of ``Variable`` nodes.  Used exclusively to
      decide whether to emit a stimulation guard
      (``if "name" not in stimmed:``) for a given assignment.
    * ``fmu_node_ids``    — UUIDs of FMU diagram nodes.  Used exclusively to
      emit UUID constants in the generated file header for ``exchange.fmu_step``
      call resolution.

    References: ``codegen_stage2_concept.rst`` §3.3.4, §3.4.
    """

    fmfl_text: str
    profile: str
    binding: TargetBinding
    policy: BuildPolicy

    # Structural identity data — not semantic
    node_labels: dict[UUID, str] = field(default_factory=dict)
    param_node_ids: frozenset[UUID] = field(default_factory=frozenset)
    variable_labels: frozenset[str] = field(default_factory=frozenset)
    fmu_node_ids: frozenset[UUID] = field(default_factory=frozenset)


# ---------------------------------------------------------------------------
# FmflCodegenBackend Protocol
# ---------------------------------------------------------------------------

class FmflCodegenBackend:
    """Protocol for Stage-2 code-generation backends.

    A backend receives the FMFL AST statement by statement.  It must not
    access :class:`~.compiler.CompiledDataflow` or any ``Eq*`` dataclass.
    All semantic information is obtained exclusively from the FMFL AST.

    References: ``codegen_stage2_concept.rst`` §3.3.4.
    """

    def emit_header(self, ctx: CodegenContext) -> str:
        """Return the file header (imports, UUID constants, function signature)."""
        raise NotImplementedError

    def emit_statement(
        self,
        stmt: AssignStmt | CommentStmt,
        ctx: CodegenContext,
    ) -> list[str]:
        """Return zero or more source lines for one FMFL statement."""
        raise NotImplementedError

    def emit_footer(self, ctx: CodegenContext) -> str:
        """Return any closing source lines (function close, trailing newline)."""
        raise NotImplementedError
