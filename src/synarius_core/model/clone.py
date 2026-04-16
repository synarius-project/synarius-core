from __future__ import annotations

from typing import Iterable, cast

from .attribute_dict import AttributeEntry
from .attribute_path import deep_copy_mapping_tree
from .base import BaseObject
from .complex_instance import ComplexInstance
from .connector import Connector
from .diagram_blocks import BasicOperator, DataViewer, Variable
from .elementary import ElementaryInstance
from .pin_helpers import _shallow_nested_pin_copy
from .signals import VariableDatabase, VariableMappingEntry


def _iter_subtree(root: BaseObject) -> Iterable[BaseObject]:
    yield root
    if isinstance(root, ComplexInstance):
        for child in root.children:
            yield from _iter_subtree(child)


def _clone_for_paste(obj: BaseObject, *, keep_ids: bool) -> BaseObject:
    obj_id = obj.id if keep_ids else None

    def clone_variable() -> Variable:
        v = Variable(
            name=obj.name,
            type_key=obj.type_key,
            value=obj.value,
            unit=obj.unit,
            pin=_shallow_nested_pin_copy(obj.get("pin")),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
        from synarius_core.dataflow_sim.stimulation import STIMULATION_PASTE_KEYS

        for key in STIMULATION_PASTE_KEYS:
            if key in obj.attribute_dict:
                try:
                    v.set(key, obj.get(key))
                except (KeyError, PermissionError, TypeError, ValueError):
                    pass
        if "dataviewer_measure_ids" in obj.attribute_dict:
            try:
                v.set("dataviewer_measure_ids", list(obj.get("dataviewer_measure_ids") or []))
            except (KeyError, PermissionError, TypeError, ValueError):
                pass
        return v

    def clone_dataviewer() -> DataViewer:
        return DataViewer(
            viewer_id=int(obj.get("dataviewer_id")),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )

    def clone_basic_operator() -> BasicOperator:
        return BasicOperator(
            name=obj.name,
            type_key=obj.type_key,
            operation=obj.operation,
            pin=_shallow_nested_pin_copy(obj.get("pin")),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )

    def clone_elementary() -> ElementaryInstance:
        el = ElementaryInstance(
            name=obj.name,
            type_key=obj.type_key,
            pin=_shallow_nested_pin_copy(obj.get("pin")),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
        try:
            fm = obj.get("fmu")
        except KeyError:
            fm = None
        if isinstance(fm, dict):
            dict.__setitem__(
                el.attribute_dict,
                "fmu",
                AttributeEntry.stored(deep_copy_mapping_tree(fm), writable=True),
            )
        return el

    def clone_var_mapping_entry() -> VariableMappingEntry:
        mapped_signal = "None"
        try:
            mapped_signal = str(obj.get("mapped_signal"))
        except Exception:
            pass
        return VariableMappingEntry(
            variable_name=obj.name,
            mapped_signal=mapped_signal,
            obj_id=obj_id,
        )

    def clone_var_database() -> VariableDatabase:
        o = cast(VariableDatabase, obj)
        cloned_db = VariableDatabase(
            name=o.name,
            position=o.position,
            size=o.size,
            obj_id=obj_id,
        )
        for child in o.children:
            cloned_db.paste(_clone_for_paste(child, keep_ids=keep_ids))
        return cloned_db

    def clone_complex() -> ComplexInstance:
        o = cast(ComplexInstance, obj)
        cloned = ComplexInstance(
            name=o.name,
            position=o.position,
            size=o.size,
            obj_id=obj_id,
        )
        for child in o.children:
            cloned.paste(_clone_for_paste(child, keep_ids=keep_ids))
        if "simulation_mode" in o.attribute_dict:
            try:
                cloned.set("simulation_mode", o.get("simulation_mode"))
            except (KeyError, PermissionError, TypeError, ValueError):
                pass
        return cloned

    def clone_connector() -> Connector:
        c = cast(Connector, obj)
        return Connector(
            name=c.name,
            source_instance_id=c.source_instance_id,
            source_pin=c.source_pin,
            target_instance_id=c.target_instance_id,
            target_pin=c.target_pin,
            directed=c.directed,
            orthogonal_bends=list(c._orthogonal_bends),
            obj_id=obj_id,
        )

    if isinstance(obj, Variable):
        return clone_variable()
    if isinstance(obj, DataViewer):
        return clone_dataviewer()
    if isinstance(obj, BasicOperator):
        return clone_basic_operator()
    if isinstance(obj, ElementaryInstance):
        return clone_elementary()
    if isinstance(obj, VariableMappingEntry):
        return clone_var_mapping_entry()
    if isinstance(obj, VariableDatabase):
        return clone_var_database()
    if isinstance(obj, ComplexInstance):
        return clone_complex()
    if isinstance(obj, Connector):
        return clone_connector()
    raise TypeError(f"Unsupported object type for cloning: {type(obj)!r}")
