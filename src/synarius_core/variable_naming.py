"""Validation rules for logical variable *names* (Python identifiers)."""

from __future__ import annotations

import keyword


class InvalidVariableNameError(ValueError):
    """Raised when a name is not usable as a Python variable identifier."""


def validate_python_variable_name(name: str) -> str:
    """Return stripped ``name`` if it is a non-keyword Python identifier; otherwise raise."""
    n = name.strip()
    if not n:
        raise InvalidVariableNameError("Variable name is empty.")
    if not n.isidentifier():
        raise InvalidVariableNameError(f"Variable name {n!r} is not a valid Python identifier.")
    if keyword.iskeyword(n):
        raise InvalidVariableNameError(f"Variable name {n!r} is a reserved Python keyword.")
    return n
