"""Shared constant: std-library arithmetic type_key → Python operator symbol.

Both :mod:`~synarius_core.dataflow_sim.equation_walk` and
:mod:`~synarius_core.dataflow_sim.compiler` import from here to avoid duplication
and circular imports.  The mapping is intentionally a plain ``dict`` so callers
can do both membership tests and symbol lookups in O(1).
"""

from __future__ import annotations

# Maps every type_key that refers to a std-library arithmetic element to the
# corresponding Python operator symbol used during code generation and runtime.
# Pin convention for these elements: inputs are "in0" and "in1", output is "out".
STD_ARITHMETIC_OP: dict[str, str] = {
    "std.Add": "+",
    "std.Sub": "-",
    "std.Mul": "*",
    "std.Div": "/",
}

# Parameter-bound lookup blocks.  All three share active-dataset binding semantics;
# each maps to a different lookup primitive during DataflowCompilePass lowering.
STD_PARAM_LOOKUP: frozenset[str] = frozenset({
    "std.Kennwert",
    "std.Kennlinie",
    "std.Kennfeld",
})
