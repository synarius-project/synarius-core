"""Namespace-qualified types for Synarius core model objects (``MODEL.*``).

These values are distinct from FMF library element references (e.g. ``std.Add``) and from
``ElementaryInstance.type_key``, which names the functional/library element implementation.
"""

from __future__ import annotations

from enum import Enum


class ModelElementType(str, Enum):
    """Canonical ``type`` strings for :class:`~synarius_core.model.data_model.BaseObject` instances."""

    MODEL_COMPLEX = "MODEL.COMPLEX"
    MODEL_ELEMENTARY = "MODEL.ELEMENTARY"
    MODEL_VARIABLE = "MODEL.VARIABLE"
    MODEL_BASIC_OPERATOR = "MODEL.BASIC_OPERATOR"
    MODEL_CONNECTOR = "MODEL.CONNECTOR"


__all__ = ["ModelElementType"]
