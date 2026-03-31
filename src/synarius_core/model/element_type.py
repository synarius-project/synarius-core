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
    MODEL_DATA_VIEWER = "MODEL.DATA_VIEWER"
    MODEL_MEASUREMENTS = "MODEL.MEASUREMENTS"
    MODEL_STIMULI = "MODEL.STIMULI"
    MODEL_RECORDING = "MODEL.RECORDING"
    MODEL_SIGNAL = "MODEL.SIGNAL"
    MODEL_VARIABLE_DATABASE = "MODEL.VARIABLE_DATABASE"
    MODEL_VARIABLE_MAPPING = "MODEL.VARIABLE_MAPPING"


__all__ = ["ModelElementType"]
