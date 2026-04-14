from __future__ import annotations

from typing import Any
from uuid import UUID

from synarius_core.variable_naming import validate_python_variable_name

from .attribute_path import split_attribute_path
from .base import LocatableInstance
from .complex_instance import ComplexInstance
from .element_type import ModelElementType
from .elementary import BasicOperatorType, ElementaryInstance
from .geometry import Point2D, Size2D
from .pin_helpers import PinDataType, PinDirection


class Variable(ElementaryInstance):
    def __init__(
        self,
        *,
        name: str,
        type_key: str,
        value: Any = None,
        unit: str = "",
        obj_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = validate_python_variable_name(name)
        super().__init__(
            name=name,
            type_key=type_key,
            model_element_type=ModelElementType.MODEL_VARIABLE,
            obj_id=obj_id,
            **kwargs,
        )
        self.value: Any = value
        self.unit: str = unit
        self.attribute_dict.set_virtual(
            "diagram_block_width",
            getter=self._get_diagram_block_width,
            setter=None,
            exposed=False,
            writable=False,
        )
        self._install_stimulation_attributes()
        self._install_dataviewer_attributes()

    def _install_default_pins_for_element(self) -> None:
        pmap = self.get("pin")
        if pmap:
            return
        defaults = {
            "in": {"direction": PinDirection.IN.value, "data_type": PinDataType.FLOAT.value, "y": None},
            "out": {"direction": PinDirection.OUT.value, "data_type": PinDataType.FLOAT.value, "y": None},
        }
        self.attribute_dict.set_value("pin", defaults)

    def _install_dataviewer_attributes(self) -> None:
        """Which data viewer IDs tap this variable's output (measurement); see Studio diagram overlays."""
        dict.__setitem__(self.attribute_dict, "dataviewer_measure_ids", ([], None, None, True, True))

    def _install_stimulation_attributes(self) -> None:
        """Writable protocol attributes for generic time-based stimulation (see ``dataflow_sim.stimulation``)."""
        from synarius_core.dataflow_sim.stimulation import STIMULATION_INSTALL_ENTRIES

        for key, default in STIMULATION_INSTALL_ENTRIES:
            dict.__setitem__(self.attribute_dict, key, (default, None, None, True, True))

    def _get_diagram_block_width(self) -> float:
        from synarius_core.model.diagram_geometry import variable_diagram_block_width_scene

        return variable_diagram_block_width_scene(self.name)

    def set_name(self, name: str) -> None:
        vn = validate_python_variable_name(name)
        old = self.name
        if vn == old:
            return
        super().set_name(vn)
        model = self.get_root_model()
        if model is not None:
            model.variable_registry.on_renamed(old, self.name)
            model.sync_variable_mapping_entries()

    def set(self, key: str, value: Any) -> None:
        parts = split_attribute_path(key)
        if len(parts) == 1 and parts[0].startswith("stim_"):
            from synarius_core.dataflow_sim.stimulation import (
                LEGACY_STIM_P_KEYS,
                on_legacy_stim_parameter_set,
                register_stim_attribute_if_missing,
            )

            register_stim_attribute_if_missing(self, parts[0])
            super().set(key, value)
            if parts[0] in LEGACY_STIM_P_KEYS:
                on_legacy_stim_parameter_set(self)
            return
        super().set(key, value)


class DataViewer(LocatableInstance):
    """Logical data-viewer instance on the diagram; ``dataviewer_id`` is the displayed number.

    ``open_widget`` (bool): when set to true via CCP (``set <ref>.open_widget true``), Synarius Studio
    opens or focuses the live DataViewer window and resets the attribute to false.
    """

    def __init__(
        self,
        *,
        viewer_id: int,
        position: Point2D | tuple[float, float] = (50.0, 50.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        vid = int(viewer_id)
        super().__init__(
            name=f"DataViewer_{vid}",
            model_element_type=ModelElementType.MODEL_DATA_VIEWER,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        dict.__setitem__(self.attribute_dict, "dataviewer_id", (vid, None, None, True, True))
        # UI / CCP: ``set <DataViewerRef>.open_widget true`` requests opening the live DataViewer
        # (Studio clears this to false after handling).
        dict.__setitem__(self.attribute_dict, "open_widget", (False, None, None, True, True))


class BasicOperator(ElementaryInstance):
    def __init__(
        self,
        *,
        name: str,
        type_key: str,
        operation: BasicOperatorType,
        obj_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            type_key=type_key,
            model_element_type=ModelElementType.MODEL_BASIC_OPERATOR,
            obj_id=obj_id,
            **kwargs,
        )
        self.operation: BasicOperatorType = operation

    def _install_default_pins_for_element(self) -> None:
        pmap = self.get("pin")
        if pmap:
            return
        defaults = {
            "in1": {"direction": PinDirection.IN.value, "data_type": PinDataType.FLOAT.value, "y": None},
            "in2": {"direction": PinDirection.IN.value, "data_type": PinDataType.FLOAT.value, "y": None},
            "out": {"direction": PinDirection.OUT.value, "data_type": PinDataType.FLOAT.value, "y": None},
        }
        self.attribute_dict.set_value("pin", defaults)
