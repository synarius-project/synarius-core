from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Size2D:
    width: float
    height: float
