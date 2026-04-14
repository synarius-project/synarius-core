"""Backward-compatible entry point for the split model implementation.

Prefer importing from ``synarius_core.model`` (package ``__init__``) or from the
focused modules listed in ``STRUCTURE.md`` in this directory.
"""

from __future__ import annotations

from .base import (
    BaseObject,
    DetachedObjectError,
    DuplicateIdError,
    IdFactory,
    LocatableInstance,
    ModelContext,
)
from .clone import _clone_for_paste, _iter_subtree
from .complex_instance import ComplexInstance
from .connector import Connector
from .diagram_blocks import BasicOperator, DataViewer, Variable
from .elementary import (
    DEFAULT_FMU_LIBRARY_TYPE_KEY,
    BasicOperatorType,
    ElementaryInstance,
    elementary_diagram_subtitle_for_geometry,
    elementary_fmu_block,
)
from .geometry import Point2D, Size2D
from .pin_helpers import Pin, PinDataType, PinDirection, pin_map_from_fmu_ports, pin_map_from_library_ports
from .root_model import Model
from .signals import Signal, SignalContainer, VariableDatabase, VariableMappingEntry

__all__ = [
    "DEFAULT_FMU_LIBRARY_TYPE_KEY",
    "BaseObject",
    "BasicOperator",
    "BasicOperatorType",
    "ComplexInstance",
    "Connector",
    "DataViewer",
    "DetachedObjectError",
    "ElementaryInstance",
    "IdFactory",
    "LocatableInstance",
    "Model",
    "ModelContext",
    "Pin",
    "PinDataType",
    "PinDirection",
    "Point2D",
    "Size2D",
    "Variable",
    "Signal",
    "SignalContainer",
    "VariableDatabase",
    "VariableMappingEntry",
    "DuplicateIdError",
    "elementary_diagram_subtitle_for_geometry",
    "elementary_fmu_block",
    "pin_map_from_fmu_ports",
    "pin_map_from_library_ports",
    "_clone_for_paste",
    "_iter_subtree",
]
