"""Bundled FMF Standard Library (v0.1): Add, Sub, Mul, Div.

Use :func:`standard_library_root` for paths; implementation in :mod:`synarius_core.standard_library.paths`.
"""

from __future__ import annotations

from .paths import STANDARD_LIBRARY_VERSION, standard_library_root

__all__ = ["standard_library_root", "STANDARD_LIBRARY_VERSION"]
