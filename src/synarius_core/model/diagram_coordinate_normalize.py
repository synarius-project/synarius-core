"""Normalize root-level diagram coordinates to a non-negative origin with padding.

Diagram block positions in ``.syn`` scripts (``new Variable … x y …`` etc.) are stored on
``LocatableInstance`` descendants under ``model.root``; see ``synarius_core.model.syn_script_export``
for export layout. After ``load``, Synarius shifts all such instances so the diagram's tight bounding box is
anchored at ``(padding, padding)`` (non-negative coordinates with a fixed margin), preserving
relative layout and connector routing (orthogonal bends are stored relative to the source pin;
see ``synarius_core.model.connector``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from synarius_core.model.base import LocatableInstance
from synarius_core.model.connector import Connector
from synarius_core.model.diagram_blocks import BasicOperator, DataViewer, Variable
from synarius_core.model.elementary import ElementaryInstance

if TYPE_CHECKING:
    from synarius_core.model.root_model import Model


def normalize_root_diagram_positions(model: Model, *, padding: float = 40.0) -> tuple[float, float] | None:
    """
    Shift every root-level diagram block so the tight bounding box of their ``(x, y)``
    positions lies in ``[padding, +∞)²``.

    Returns ``(dx, dy)`` applied in model space, or ``None`` if no diagram blocks exist or no
    shift was needed.
    """
    root = model.root
    locatables: list[LocatableInstance] = []
    for child in root.children:
        if isinstance(child, Connector):
            continue
        if isinstance(child, (Variable, BasicOperator, DataViewer, ElementaryInstance)):
            locatables.append(child)
    if not locatables:
        return None
    min_x = min(float(c.x) for c in locatables)
    min_y = min(float(c.y) for c in locatables)
    # Always align the tight bounding box to ``(padding, padding)``, not only when coordinates
    # are negative — large positive offsets would otherwise keep the diagram visually "floating".
    dx = float(padding) - min_x
    dy = float(padding) - min_y
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    for c in locatables:
        c.set_xy((c.x + dx, c.y + dy))
    return (dx, dy)
