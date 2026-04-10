"""Readable snapshots of Python sources actually executed for scalar dataflow simulation."""

from __future__ import annotations

from pathlib import Path


def read_simple_run_engine_module_source() -> str:
    """
    Return the full UTF-8 source of ``synarius_core.dataflow_sim.engine`` — the module that defines
    :class:`~synarius_core.dataflow_sim.engine.SimpleRunEngine`, including ``init`` / ``step`` / ``reset``
    as executed by the Studio worker thread.
    """
    import synarius_core.dataflow_sim.engine as engine_mod

    path = Path(engine_mod.__file__)
    body = path.read_text(encoding="utf-8")
    return f"# Source file: {path.as_posix()}\n# (executed implementation — SimpleRunEngine)\n\n{body}"
