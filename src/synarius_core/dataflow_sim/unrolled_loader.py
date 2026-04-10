"""Load ``run_equations`` from generated unrolled Python source (in-process ``compile`` + ``exec``)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .step_exchange import RunStepExchange


def load_run_equations_from_source(src: str) -> Callable[[RunStepExchange], None]:
    """
    Execute *src* (output of :func:`synarius_core.dataflow_sim.python_step_emit.generate_unrolled_python_step_document`)
    and return the ``run_equations`` callable.

    The generated module imports ``UUID`` and ``RunStepExchange``; normal import resolution applies.
    """
    g: dict[str, Any] = {"__builtins__": __builtins__, "__name__": "unrolled_step"}
    code = compile(src, "<unrolled_step>", "exec")
    exec(code, g, g)
    fn = g.get("run_equations")
    if not callable(fn):
        raise RuntimeError("unrolled source did not define a callable run_equations")
    return fn  # type: ignore[return-value]
