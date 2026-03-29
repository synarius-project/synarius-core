"""Core data model classes for synarius-core."""

from synarius_core.variable_registry import VariableNameRegistry

from .attribute_dict import AttributeDict
from .element_type import ModelElementType
from .data_model import (
    BaseObject,
    BasicOperator,
    BasicOperatorType,
    ComplexInstance,
    Connector,
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
    DuplicateIdError,
)

__all__ = [
    "VariableNameRegistry",
    "AttributeDict",
    "ModelElementType",
    "BaseObject",
    "LocatableInstance",
    "ElementaryInstance",
    "Variable",
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
]

