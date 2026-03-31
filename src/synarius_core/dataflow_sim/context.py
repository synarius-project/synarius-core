"""Execution context for Synarius dataflow simulation (Plugin API–shaped context)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from synarius_core.model import Model


@dataclass
class SimulationContext:
    """Shared context for compile passes and runtime stepping."""

    model: Model
    artifacts: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    time_s: float = 0.0
    #: Set by :class:`SimpleRunEngine` during ``init``/``step`` for ``runtime:fmu`` plugins.
    scalar_workspace: dict[UUID, float] | None = None
