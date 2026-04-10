"""FMFL document generation — re-exports :mod:`codegen_kernel` (single canonical emitter)."""

from __future__ import annotations

from .codegen_kernel import generate_fmfl_document, generate_python_kernel_document

__all__ = ["generate_fmfl_document", "generate_python_kernel_document"]
