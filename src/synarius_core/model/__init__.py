"""Core data model classes for synarius-core."""

from synarius_core.variable_naming import validate_pin_name
from synarius_core.variable_registry import VariableNameRegistry

from .attribute_dict import AttributeDict
from .attribute_path import join_attribute_path, split_attribute_path
from .element_type import ModelElementType
from .data_model import (
    DEFAULT_FMU_LIBRARY_TYPE_KEY,
    BaseObject,
    BasicOperator,
    BasicOperatorType,
    ComplexInstance,
    Connector,
    DataViewer,
    DetachedObjectError,
    ElementaryInstance,
    IdFactory,
    LocatableInstance,
    Model,
    ModelContext,
    Pin,
    PinDataType,
    PinDirection,
    Point2D,
    Size2D,
    Variable,
    Signal,
    SignalContainer,
    VariableDatabase,
    VariableMappingEntry,
    DuplicateIdError,
    elementary_fmu_block,
    pin_map_from_fmu_ports,
    pin_map_from_library_ports,
)

__all__ = [
    "VariableNameRegistry",
    "AttributeDict",
    "split_attribute_path",
    "join_attribute_path",
    "validate_pin_name",
    "ModelElementType",
    "BaseObject",
    "LocatableInstance",
    "ElementaryInstance",
    "DEFAULT_FMU_LIBRARY_TYPE_KEY",
    "elementary_fmu_block",
    "pin_map_from_fmu_ports",
    "pin_map_from_library_ports",
    "Variable",
    "DataViewer",
    "BasicOperator",
    "BasicOperatorType",
    "IdFactory",
    "ModelContext",
    "Model",
    "ComplexInstance",
    "Connector",
    "DuplicateIdError",
    "DetachedObjectError",
    "Pin",
    "PinDataType",
    "PinDirection",
    "Point2D",
    "Size2D",
    "Signal",
    "SignalContainer",
    "VariableDatabase",
    "VariableMappingEntry",
]

