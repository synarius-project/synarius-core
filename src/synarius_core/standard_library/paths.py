"""Filesystem location of the bundled FMF standard library (``libraryDescription.xml``)."""

from __future__ import annotations

from pathlib import Path

STANDARD_LIBRARY_VERSION = "1.0.0"


def standard_library_root() -> Path:
    """Directory that contains ``libraryDescription.xml`` for the standard library.

    Library assets live under the repository ``Lib/std`` directory (separate from Python
    source under ``src/synarius_core``). Wheels copy those files next to this module at build time.
    SVG triples follow C.3.1; hosts that load one file **SHOULD** use ``*_16.svg``. Icons match Studio BasicOperator glyphs (``#2468dc`` / ``#16161c``).
    """
    here = Path(__file__).resolve().parent
    if (here / "libraryDescription.xml").is_file():
        return here
    cur = here
    for _ in range(10):
        cand = cur / "Lib" / "std"
        if (cand / "libraryDescription.xml").is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    msg = "Synarius standard library not found (expected Lib/std or wheel copy)."
    raise RuntimeError(msg)
