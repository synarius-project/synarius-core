"""Execution context for Synarius dataflow simulation (Plugin API–shaped context)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from synarius_core.model import Model


@dataclass
class SimulationContext:
    """Shared context for compile passes and runtime stepping."""

    model: Model
    artifacts: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    time_s: float = 0.0
