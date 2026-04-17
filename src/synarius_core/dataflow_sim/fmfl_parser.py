"""FMFL Stage-1 output parser — AST types and :func:`parse_equations_block`.

Parses exactly the Minimal Normal Form emitted by
``codegen_kernel.generate_fmfl_document`` (section 2.2.2 of
``docs/specifications/fmf_fmfl/codegen_stage2_concept.rst``).

No import from ``synarius_core.dataflow_sim`` or any model type is permitted
in this module.  It is a zero-dependency text processor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union


# ---------------------------------------------------------------------------
# AST types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NameExpr:
    """A bare name reference, e.g. ``speed`` or ``@active_dataset.x.y``."""
    name: str


@dataclass(frozen=True)
class PrevExpr:
    """A delayed-feedback reference ``prev(inner)``."""
    inner: "Expr"


@dataclass(frozen=True)
class BinOpExpr:
    """A single binary expression ``left op right`` with op in ``{+, -, *, /}``."""
    left: "Expr"
    op: str
    right: "Expr"


@dataclass(frozen=True)
class CallExpr:
    """A single-level function call ``func(arg1, arg2, ...)``."""
    func: str
    args: tuple["Expr", ...]


@dataclass(frozen=True)
class AssignStmt:
    """A simple assignment ``target = rhs``."""
    target: str
    rhs: "Expr"


@dataclass(frozen=True)
class CommentStmt:
    """A comment line; ``text`` is the content after the leading ``# ``."""
    text: str


Expr = Union[NameExpr, PrevExpr, BinOpExpr, CallExpr]
Stmt = Union[AssignStmt, CommentStmt]


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class FmflParseError(ValueError):
    """Raised when *fmfl_text* does not conform to the Stage-1 output subset.

    The message identifies the offending line number and content.
    """


# ---------------------------------------------------------------------------
# Internal tokeniser patterns
# ---------------------------------------------------------------------------

# A valid FMFL identifier: alphanumeric + underscore, or a path starting with @
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_PATH  = r"@[A-Za-z0-9_.@]+"
_NAME  = rf"(?:{_PATH}|{_IDENT}(?:\.[A-Za-z_][A-Za-z0-9_]*)?)"  # e.g. fmu.out or @path

_PREV_RE   = re.compile(rf"^prev\(({_NAME})\)$")
_BINOP_RE  = re.compile(rf"^({_NAME})\s*([+\-*/])\s*({_NAME})$")
_CALL_RE   = re.compile(rf"^({_IDENT})\((.+)\)$", re.DOTALL)
_NAME_RE   = re.compile(rf"^{_NAME}$")
_ASSIGN_RE = re.compile(rf"^({_IDENT})\s*=\s*(.+)$", re.DOTALL)


def _parse_expr(raw: str, lineno: int) -> Expr:
    """Parse one expression token.  Raises :exc:`FmflParseError` on failure."""
    s = raw.strip()

    # prev(name)
    m = _PREV_RE.match(s)
    if m:
        return PrevExpr(NameExpr(m.group(1)))

    # a op b  — single binary operator, both operands are bare names or prev(name)
    m = _BINOP_RE.match(s)
    if m:
        left  = _parse_atomic(m.group(1), lineno)
        op    = m.group(2)
        right = _parse_atomic(m.group(3), lineno)
        return BinOpExpr(left, op, right)

    # func(arg1, arg2, ...)
    m = _CALL_RE.match(s)
    if m:
        func     = m.group(1)
        args_raw = m.group(2)
        args     = tuple(_parse_atomic(a.strip(), lineno) for a in _split_args(args_raw, lineno))
        return CallExpr(func, args)

    # bare name / path
    if _NAME_RE.match(s):
        return NameExpr(s)

    raise FmflParseError(f"line {lineno}: cannot parse expression: {s!r}")


def _parse_atomic(raw: str, lineno: int) -> Expr:
    """Parse an atomic expression: a bare name or ``prev(name)``."""
    s = raw.strip()
    m = _PREV_RE.match(s)
    if m:
        return PrevExpr(NameExpr(m.group(1)))
    if _NAME_RE.match(s):
        return NameExpr(s)
    raise FmflParseError(f"line {lineno}: expected name or prev(name), got: {s!r}")


def _split_args(raw: str, lineno: int) -> list[str]:
    """Split a comma-separated argument list (no nested parens expected in Stage-1 output)."""
    parts = [p.strip() for p in raw.split(",")]
    if not parts:
        raise FmflParseError(f"line {lineno}: empty argument list")
    return parts


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def parse_equations_block(fmfl_text: str) -> list[Stmt]:
    """Parse the ``equations:`` block of *fmfl_text* and return an ordered statement list.

    Accepts the complete FMFL document text produced by
    ``codegen_kernel.generate_fmfl_document``.  The ``init:`` block is parsed
    and discarded.  Only the ``equations:`` block is returned.

    Raises :exc:`FmflParseError` with a message identifying the offending line
    on any input that does not conform to the Minimal Normal Form.

    References: ``codegen_stage2_concept.rst`` §2.2.2, §3.3.1.
    """
    lines = fmfl_text.splitlines()

    # Locate the equations: block
    eq_start: int | None = None
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped == "equations:":
            eq_start = i
            break

    if eq_start is None:
        return []

    stmts: list[Stmt] = []
    for lineno, raw in enumerate(lines[eq_start + 1:], start=eq_start + 2):
        # Strip indentation; the block ends at the next un-indented non-empty line
        if raw and not raw[0].isspace():
            break

        line = raw.strip()

        if not line:
            continue

        if line.startswith("#"):
            stmts.append(CommentStmt(line[1:].lstrip()))
            continue

        m = _ASSIGN_RE.match(line)
        if not m:
            raise FmflParseError(f"line {lineno}: expected assignment or comment, got: {line!r}")

        target = m.group(1)
        rhs    = _parse_expr(m.group(2).strip(), lineno)
        stmts.append(AssignStmt(target, rhs))

    return stmts
