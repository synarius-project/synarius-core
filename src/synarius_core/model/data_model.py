from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Iterator
from uuid import UUID, uuid4

from synarius_core.variable_naming import validate_pin_name, validate_python_variable_name
from synarius_core.variable_registry import VariableNameRegistry

from .attribute_dict import AttributeDict
from .attribute_path import deep_copy_mapping_tree, split_attribute_path
from .element_type import ModelElementType
from .connector_routing import (
    auto_orthogonal_bends,
    bends_absolute_to_relative,
    bends_relative_to_absolute,
    encode_bends_from_polyline,
    polyline_for_endpoints,
)


@dataclass(frozen=True, slots=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Size2D:
    width: float
    height: float


class PinDirection(str, Enum):
    IN = "IN"
    OUT = "OUT"


class PinDataType(str, Enum):
    FLOAT = "float"


@dataclass(slots=True)
class Pin:
    name: str
    direction: PinDirection
    data_type: PinDataType


def _pin_map_from_legacy(
    *,
    pin: dict[str, dict[str, Any]] | None,
    in_pins: Iterable[Pin] | None,
    out_pins: Iterable[Pin] | None,
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if pin:
        for pname, meta in pin.items():
            validate_pin_name(pname)
            merged[pname] = dict(meta)
    if in_pins:
        for p in in_pins:
            merged[p.name] = {
                "direction": p.direction.value,
                "data_type": p.data_type.value,
                "y": None,
            }
    if out_pins:
        for p in out_pins:
            merged[p.name] = {
                "direction": p.direction.value,
                "data_type": p.data_type.value,
                "y": None,
            }
    return merged


def pin_map_from_library_ports(ports: list[tuple[str, str, str]]) -> dict[str, dict[str, Any]]:
    """Build ``pin`` entries from FMF ``libraryDescription`` port tuples (kind, name, type)."""
    out: dict[str, dict[str, Any]] = {}
    for kind, pname, typ in ports:
        if not pname:
            continue
        validate_pin_name(pname)
        k = (kind or "").lower()
        if k in ("in", "input"):
            direction = PinDirection.IN.value
        elif k in ("out", "output"):
            direction = PinDirection.OUT.value
        else:
            direction = PinDirection.IN.value
        dt = str(typ or PinDataType.FLOAT.value).lower()
        if dt in ("real", "float", "double"):
            data_type = PinDataType.FLOAT.value
        elif dt in ("int", "integer"):
            data_type = "int"
        elif dt == "bool":
            data_type = "bool"
        elif dt == "string":
            data_type = "string"
        else:
            data_type = PinDataType.FLOAT.value
        out[pname] = {"direction": direction, "data_type": data_type, "y": None}
    return out


def _normalize_fmu_variable_rows(raw_list: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Build persisted ``fmu.variables`` list: FMI-like scalar metadata (name, value_reference, causality, …)."""
    out: list[dict[str, Any]] = []
    for raw in raw_list or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        row: dict[str, Any] = {"name": name}
        vr = raw.get("value_reference")
        if vr is not None:
            try:
                row["value_reference"] = int(vr)
            except (TypeError, ValueError):
                row["value_reference"] = vr
        for key in ("causality", "variability"):
            if key in raw and raw[key] is not None and raw[key] != "":
                row[key] = str(raw[key]).strip().lower()
        for key in ("data_type", "description", "unit", "declared_type"):
            if key in raw and raw[key] is not None and raw[key] != "":
                row[key] = raw[key]
        for key in ("initial", "start"):
            if key in raw:
                row[key] = raw[key]
        for k, v in raw.items():
            if k in row or k == "name":
                continue
            row[k] = v
        out.append(row)
    return out


def pin_map_from_fmu_ports(ports: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in ports or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        validate_pin_name(name)
        causality = str(raw.get("causality", "")).lower()
        direction = PinDirection.OUT.value if causality in ("output",) else PinDirection.IN.value
        row: dict[str, Any] = {
            "direction": direction,
            "data_type": str(raw.get("data_type", PinDataType.FLOAT.value)),
            "y": raw.get("y", None),
        }
        for k, v in raw.items():
            if k in ("name", "causality", "direction", "data_type", "y"):
                continue
            row[k] = v
        out[name] = row
    return out


def _shallow_nested_pin_copy(pmap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(k): dict(v) for k, v in pmap.items() if isinstance(v, dict)}


class BasicOperatorType(str, Enum):
    PLUS = "+"
    MINUS = "-"
    MULTIPLY = "*"
    DIVIDE = "/"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_name(name: str) -> str:
    return name.strip()


class DuplicateIdError(ValueError):
    """Raised if an ID is reserved twice in one model context."""


class DetachedObjectError(RuntimeError):
    """Raised if a model operation requires an attached object."""


class IdFactory:
    """Registry-backed UUID factory for model-unique IDs."""

    def __init__(self) -> None:
        self._used_ids: set[UUID] = set()

    def contains(self, id_: UUID) -> bool:
        return id_ in self._used_ids

    def reserve(self, id_: UUID) -> None:
        if id_ in self._used_ids:
            raise DuplicateIdError(f"ID '{id_}' is already reserved.")
        self._used_ids.add(id_)

    def unregister(self, id_: UUID) -> None:
        self._used_ids.discard(id_)

    def new_id(self) -> UUID:
        while True:
            candidate = uuid4()
            if candidate not in self._used_ids:
                self._used_ids.add(candidate)
                return candidate


@dataclass(slots=True)
class ModelContext:
    id_factory: IdFactory
    model: Model | None

    def __init__(self, id_factory: IdFactory | None = None) -> None:
        self.id_factory = id_factory or IdFactory()
        self.model = None


class BaseObject:
    """Base class for all model objects.

    Persistence rules:
    - ``type`` (``MODEL.*`` string) and ``_id`` / ``_hash_name`` are persistent.
    - ``type`` is stored in ``attribute_dict``, **exposed**, and **not writable** (spec: ``core_type_system``).
    - ``_name`` is transient (only exposed virtually via AttributeDict).
    - ``created_at`` and ``updated_at`` are stored/managed inside ``attribute_dict`` only.
    """

    def __init__(
        self,
        *,
        name: str,
        model_element_type: ModelElementType,
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        self.context: ModelContext | None = None
        self.parent: ComplexInstance | None = parent
        self._id: UUID | None = obj_id
        self._name: str = _normalize_name(name)
        self._hash_name: str = ""
        self.attribute_dict: AttributeDict = AttributeDict()

        self.attribute_dict["type"] = model_element_type.value

        # Managed inside AttributeDict only.
        self.attribute_dict["created_at"] = _utcnow()
        self.attribute_dict["updated_at"] = _utcnow()

        self._refresh_hash_name()
        self._install_virtual_attributes()

    # ---- virtual attributes -------------------------------------------------

    @property
    def id(self) -> UUID | None:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def hash_name(self) -> str:
        return self._hash_name

    def _install_virtual_attributes(self) -> None:
        self.attribute_dict.set_virtual(
            "id",
            getter=lambda: self._id,
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "hash_name",
            getter=lambda: self._hash_name,
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "name",
            getter=lambda: self._name,
            setter=lambda v: self.set_name(str(v)),
            writable=True,
        )
        self.attribute_dict.set_virtual(
            "path",
            getter=self._compute_path,
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "id_short",
            getter=self._compute_id_short,
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "prompt_path",
            getter=self._compute_prompt_path,
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "created_at",
            getter=lambda: dict.__getitem__(self.attribute_dict, "created_at")[0],
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "updated_at",
            getter=lambda: dict.__getitem__(self.attribute_dict, "updated_at")[0],
            setter=None,
            writable=False,
        )

    def _compute_path(self) -> str:
        if self.parent is None:
            return self._hash_name
        return f"{self.parent.path}/{self._hash_name}"

    def _compute_id_short(self) -> str:
        if self._id is None:
            return ""
        model = self.get_root_model()
        if model is None:
            return self._id.hex[:8]
        return model.short_id(self._id, min_len=1)

    def _compute_prompt_path(self) -> str:
        if self.parent is None:
            return f"{self._name}@{self._compute_id_short()}"
        parent_path = self.parent.get("prompt_path")
        return f"{parent_path}/{self._name}@{self._compute_id_short()}"

    @property
    def path(self) -> str:
        return self._compute_path()

    # ---- API ----------------------------------------------------------------

    def set_name(self, name: str) -> None:
        old_hash = self._hash_name
        self._name = _normalize_name(name)
        self._refresh_hash_name()
        if self.parent is not None:
            self.parent._on_child_hash_name_changed(self, old_hash, self._hash_name)
        self._touch()

    def _refresh_hash_name(self) -> None:
        # Always keep @<id> suffix stable.
        id_suffix = str(self._id) if self._id is not None else "<detached>"
        self._hash_name = f"{self._name}@{id_suffix}"

    def _touch(self) -> None:
        # Stored/managed in AttributeDict only.
        dict.__setitem__(
            self.attribute_dict,
            "updated_at",
            (_utcnow(), None, None, True, False),
        )

    def get(self, key: str) -> Any:
        parts = split_attribute_path(key)
        if len(parts) == 1:
            return self.attribute_dict[parts[0]]
        cur: Any = self.attribute_dict[parts[0]]
        for seg in parts[1:]:
            if not isinstance(cur, dict):
                raise TypeError(
                    f"Cannot traverse attribute path {key!r}: {seg!r} is not inside a mapping."
                )
            if seg not in cur:
                raise KeyError(key)
            cur = cur[seg]
        return cur

    def set(self, key: str, value: Any) -> None:
        parts = split_attribute_path(key)
        if len(parts) == 1:
            self.attribute_dict.set_value(parts[0], value)
            self._touch()
            return
        root = parts[0]
        if root == "pin" and len(parts) >= 2:
            validate_pin_name(parts[1])
        if not self._root_is_writable_for_nested_update(root):
            raise PermissionError(f"Attribute '{root}' is not writable.")
        base_val = self.attribute_dict.stored_value(root)
        if not isinstance(base_val, dict):
            raise TypeError(
                f"Attribute '{root}' is not a mapping; cannot use hierarchical path {key!r}."
            )
        new_tree = deep_copy_mapping_tree(base_val)
        cur: dict[str, Any] = new_tree
        for seg in parts[1:-1]:
            nxt = cur.get(seg)
            if nxt is None:
                cur[seg] = {}
            elif not isinstance(nxt, dict):
                raise TypeError(f"Cannot traverse {key!r}: {seg!r} is not a mapping.")
            cur = cur[seg]
        cur[parts[-1]] = value
        self.attribute_dict.set_value(root, new_tree)
        self._touch()

    def _root_is_writable_for_nested_update(self, root: str) -> bool:
        return self.attribute_dict.allows_structural_value_replace(root)

    @property
    def is_attached(self) -> bool:
        return self.context is not None and self._id is not None

    def _assign_context(self, context: ModelContext) -> None:
        self.context = context

    def _detach_context(self) -> None:
        self.context = None

    def get_root(self) -> BaseObject:
        """Return the root object of this object's current tree."""
        node: BaseObject = self
        while node.parent is not None:
            node = node.parent
        return node

    def get_root_model(self) -> Model | None:
        """Return the model owning this object, if attached."""
        if self.context is None:
            return None
        return self.context.model


class LocatableInstance(BaseObject):
    def __init__(
        self,
        *,
        name: str,
        model_element_type: ModelElementType,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(name=name, model_element_type=model_element_type, obj_id=obj_id, parent=parent)
        self.position: Point2D = self._coerce_point(position)
        self.size: Size2D = size
        self._install_locatable_virtuals()

    def _coerce_point(self, pos: Point2D | tuple[float, float]) -> Point2D:
        if isinstance(pos, Point2D):
            return pos
        x, y = pos
        return Point2D(float(x), float(y))

    @property
    def x(self) -> float:
        return self.position.x

    @property
    def y(self) -> float:
        return self.position.y

    def _install_locatable_virtuals(self) -> None:
        self.attribute_dict.set_virtual(
            "x",
            getter=lambda: self.position.x,
            setter=lambda v: self.set_xy((float(v), self.position.y)),
            writable=True,
        )
        self.attribute_dict.set_virtual(
            "y",
            getter=lambda: self.position.y,
            setter=lambda v: self.set_xy((self.position.x, float(v))),
            writable=True,
        )

    def set_xy(self, pos: Point2D | tuple[float, float]) -> None:
        self.position = self._coerce_point(pos)
        self._touch()


class ElementaryInstance(LocatableInstance):
    def __init__(
        self,
        *,
        name: str,
        type_key: str,
        model_element_type: ModelElementType = ModelElementType.MODEL_ELEMENTARY,
        pin: dict[str, dict[str, Any]] | None = None,
        in_pins: Iterable[Pin] | None = None,
        out_pins: Iterable[Pin] | None = None,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model_element_type=model_element_type,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        self.type_key = type_key
        merged = _pin_map_from_legacy(pin=pin, in_pins=in_pins, out_pins=out_pins)
        dict.__setitem__(self.attribute_dict, "pin", (merged, None, None, True, True))
        self._install_default_pins_for_element()

    def _install_default_pins_for_element(self) -> None:
        """Populate built-in pins for leaf diagram element types (override in subclasses)."""
        return

    def _pins_filtered(self, direction: PinDirection) -> list[Pin]:
        pmap = self.get("pin")
        out: list[Pin] = []
        for pname, meta in sorted(pmap.items(), key=lambda kv: kv[0]):
            if meta.get("direction") == direction.value:
                dt_raw = meta.get("data_type", PinDataType.FLOAT.value)
                try:
                    dt = PinDataType(dt_raw)
                except ValueError:
                    dt = PinDataType.FLOAT
                out.append(Pin(name=pname, direction=direction, data_type=dt))
        return out

    @property
    def in_pins(self) -> list[Pin]:
        return self._pins_filtered(PinDirection.IN)

    @property
    def out_pins(self) -> list[Pin]:
        return self._pins_filtered(PinDirection.OUT)


DEFAULT_FMU_LIBRARY_TYPE_KEY = "std.FmuCoSimulation"
"""Default ``type_key`` for FMU co-simulation blocks (FMF library element when bundled)."""


def elementary_fmu_block(
    *,
    name: str,
    type_key: str,
    fmu_path: str,
    fmi_version: str,
    fmu_type: str,
    guid: str = "",
    model_identifier: str = "",
    fmu_description: str = "",
    fmu_author: str = "",
    fmu_model_version: str = "",
    fmu_generation_tool: str = "",
    fmu_generation_date: str = "",
    step_size_hint: float | None = None,
    tolerance: float | None = None,
    start_time: float | None = None,
    stop_time: float | None = None,
    fmu_ports: list[dict[str, Any]] | None = None,
    fmu_variables: list[dict[str, Any]] | None = None,
    pin: dict[str, dict[str, Any]] | None = None,
    fmu_extra_meta: dict[str, Any] | None = None,
    library_pin_seed: dict[str, dict[str, Any]] | None = None,
    in_pins: Iterable[Pin] | None = None,
    out_pins: Iterable[Pin] | None = None,
    position: Point2D | tuple[float, float] = (0.0, 0.0),
    size: Size2D = Size2D(1.0, 1.0),
    obj_id: UUID | None = None,
    parent: ComplexInstance | None = None,
) -> ElementaryInstance:
    """Diagram block carrying FMU configuration under the ``fmu`` attribute subtree (``MODEL.ELEMENTARY``).

    * ``fmu_ports`` — defines diagram :attr:`pin` entries (connector endpoint names, direction, ``value_reference``, …).
    * ``fmu_variables`` — optional full variable catalog under ``fmu.variables`` (FMI scalar metadata); diagram wires
      use **the same** ``name`` strings as in :attr:`pin` / ``fmu_ports`` when a port maps to an FMU variable.
    """
    port_pin = pin_map_from_fmu_ports(fmu_ports)
    explicit_pin = {str(k): dict(v) for k, v in (pin or {}).items()}
    for pname in explicit_pin:
        validate_pin_name(pname)
    seed = {**dict(library_pin_seed or {}), **port_pin, **explicit_pin}
    merged_for_ctor: dict[str, dict[str, Any]] | None = seed if seed else None
    el = ElementaryInstance(
        name=name,
        type_key=type_key,
        pin=merged_for_ctor,
        in_pins=in_pins,
        out_pins=out_pins,
        position=position,
        size=size,
        obj_id=obj_id,
        parent=parent,
    )
    fmu_body: dict[str, Any] = {
        "path": fmu_path,
        "fmi_version": fmi_version,
        "fmu_type": fmu_type,
        "guid": guid,
        "model_identifier": model_identifier,
        "description": fmu_description,
        "author": fmu_author,
        "model_version": fmu_model_version,
        "generation_tool": fmu_generation_tool,
        "generation_date": fmu_generation_date,
        "step_size_hint": step_size_hint,
        "tolerance": tolerance,
        "start_time": start_time,
        "stop_time": stop_time,
        "extra_meta": dict(fmu_extra_meta or {}),
        "variables": _normalize_fmu_variable_rows(fmu_variables),
    }
    dict.__setitem__(el.attribute_dict, "fmu", (fmu_body, None, None, True, True))
    return el


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
        for key, default in (
            ("stim_kind", "none"),
            ("stim_p0", 0.0),
            ("stim_p1", 1.0),
            ("stim_p2", 1.0),
            ("stim_p3", 0.0),
        ):
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


class DataViewer(LocatableInstance):
    """Logical data-viewer instance on the diagram; ``dataviewer_id`` is the displayed number."""

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


class ComplexInstance(LocatableInstance):
    def __init__(
        self,
        *,
        name: str,
        children: Iterable[BaseObject] | None = None,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model_element_type=ModelElementType.MODEL_COMPLEX,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        self.children: list[BaseObject] = []
        self.children_by_hash_name: dict[str, BaseObject] = {}
        for child in children or []:
            self.paste(child)

    def paste(self, obj: BaseObject) -> None:
        if obj in self.children:
            return
        obj.parent = self
        self.children.append(obj)
        if obj.hash_name in self.children_by_hash_name:
            raise ValueError(f"Duplicate child hash_name '{obj.hash_name}' in ComplexInstance.")
        self.children_by_hash_name[obj.hash_name] = obj
        self._touch()

    def del_(self, obj_id: UUID) -> None:
        victim = next((c for c in self.children if c.id == obj_id), None)
        if victim is None:
            return
        self.children.remove(victim)
        self.children_by_hash_name.pop(victim.hash_name, None)
        victim.parent = None
        self._touch()

    def get_child(self, ref: str) -> BaseObject | None:
        # 1) hash_name direct lookup
        direct = self.children_by_hash_name.get(ref)
        if direct is not None:
            return direct

        # 2) UUID string lookup
        try:
            as_uuid = UUID(ref)
        except Exception:
            as_uuid = None
        if as_uuid is not None:
            return next((c for c in self.children if c.id == as_uuid), None)

        return None

    def _on_child_hash_name_changed(self, child: BaseObject, old_hash: str, new_hash: str) -> None:
        if old_hash in self.children_by_hash_name:
            self.children_by_hash_name.pop(old_hash, None)
        self.children_by_hash_name[new_hash] = child


def _iter_subtree(root: BaseObject) -> Iterable[BaseObject]:
    yield root
    if isinstance(root, ComplexInstance):
        for child in root.children:
            yield from _iter_subtree(child)


def _clone_for_paste(obj: BaseObject, *, keep_ids: bool) -> BaseObject:
    obj_id = obj.id if keep_ids else None
    if isinstance(obj, Variable):
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
        for key in ("stim_kind", "stim_p0", "stim_p1", "stim_p2", "stim_p3"):
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
    if isinstance(obj, DataViewer):
        return DataViewer(
            viewer_id=int(obj.get("dataviewer_id")),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
    if isinstance(obj, BasicOperator):
        return BasicOperator(
            name=obj.name,
            type_key=obj.type_key,
            operation=obj.operation,
            pin=_shallow_nested_pin_copy(obj.get("pin")),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
    if isinstance(obj, ElementaryInstance):
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
                (deep_copy_mapping_tree(fm), None, None, True, True),
            )
        return el
    if isinstance(obj, VariableMappingEntry):
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
    if isinstance(obj, VariableDatabase):
        cloned_db = VariableDatabase(
            name=obj.name,
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
        for child in obj.children:
            cloned_db.paste(_clone_for_paste(child, keep_ids=keep_ids))
        return cloned_db
    if isinstance(obj, ComplexInstance):
        cloned = ComplexInstance(
            name=obj.name,
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
        for child in obj.children:
            cloned.paste(_clone_for_paste(child, keep_ids=keep_ids))
        if "simulation_mode" in obj.attribute_dict:
            try:
                cloned.set("simulation_mode", obj.get("simulation_mode"))
            except (KeyError, PermissionError, TypeError, ValueError):
                pass
        return cloned
    if isinstance(obj, Connector):
        # Connector endpoints remain as-is; a future remapping pass can adjust them.
        return Connector(
            name=obj.name,
            source_instance_id=obj.source_instance_id,
            source_pin=obj.source_pin,
            target_instance_id=obj.target_instance_id,
            target_pin=obj.target_pin,
            directed=obj.directed,
            orthogonal_bends=list(obj._orthogonal_bends),
            obj_id=obj_id,
        )
    raise TypeError(f"Unsupported object type for cloning: {type(obj)!r}")


class Signal(BaseObject):
    """Logical signal/measurement channel metadata object.

    Time-series ownership and storage are managed by the parent container
    (e.g. ``stimuli`` or ``recording``); this object exposes per-channel
    metadata through ``attribute_dict``.
    """

    def __init__(
        self,
        *,
        name: str,
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model_element_type=ModelElementType.MODEL_SIGNAL,
            obj_id=obj_id,
            parent=parent,
        )


class VariableMappingEntry(BaseObject):
    """One mapping row in ``variables_db``: variable name -> mapped stimuli signal."""

    def __init__(
        self,
        *,
        variable_name: str,
        mapped_signal: str = "None",
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=variable_name,
            model_element_type=ModelElementType.MODEL_VARIABLE_MAPPING,
            obj_id=obj_id,
            parent=parent,
        )
        dict.__setitem__(self.attribute_dict, "variable_name", (variable_name, None, None, True, False))
        dict.__setitem__(self.attribute_dict, "mapped_signal", (mapped_signal, None, None, True, True))


class VariableDatabase(ComplexInstance):
    """Container for variable-name keyed mapping entries."""

    def __init__(
        self,
        *,
        name: str = "variables_db",
        children: Iterable[BaseObject] | None = None,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            children=children,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        self.attribute_dict["type"] = ModelElementType.MODEL_VARIABLE_DATABASE.value

    def entry_for_name(self, variable_name: str) -> VariableMappingEntry | None:
        key = variable_name.strip()
        for child in self.children:
            if isinstance(child, VariableMappingEntry) and child.name == key:
                return child
        return None


class SignalContainer(ComplexInstance):
    """Container for ``Signal`` children and their time-series data.

    The container owns the sample storage for all descendant signals; signals
    themselves only carry metadata. Storage layout and lifecycle policies
    (e.g. run-based recording reset) are implemented here.
    """

    def __init__(
        self,
        *,
        name: str,
        children: Iterable[BaseObject] | None = None,
        position: Point2D | tuple[float, float] = (0.0, 0.0),
        size: Size2D = Size2D(1.0, 1.0),
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
        model_element_type: ModelElementType = ModelElementType.MODEL_MEASUREMENTS,
    ) -> None:
        super().__init__(
            name=name,
            children=children,
            position=position,
            size=size,
            obj_id=obj_id,
            parent=parent,
        )
        # Override the container's logical type (ComplexInstance sets MODEL_COMPLEX).
        self.attribute_dict["type"] = model_element_type.value
        # Internal storage for time-series per signal hash_name.
        # Each entry maps to a tuple (t_values, y_values), both as plain Python lists.
        self._series_store: dict[str, tuple[list[float], list[float]]] = {}

    # ---- signal / data API ---------------------------------------------------

    def clear_all_series(self) -> None:
        """Drop all stored samples for all signals in this container."""
        self._series_store.clear()

    def clear_series(self, signal: Signal) -> None:
        """Drop stored samples for a single signal."""
        self._series_store.pop(signal.hash_name, None)

    def set_series(
        self,
        signal: Signal,
        t_values: Iterable[float],
        y_values: Iterable[float],
    ) -> None:
        """Replace the full time-series for ``signal``.

        Callers are responsible for monotonically increasing ``t_values`` and
        length matching between ``t_values`` and ``y_values``.
        """
        t_list = [float(v) for v in t_values]
        y_list = [float(v) for v in y_values]
        if len(t_list) != len(y_list):
            raise ValueError("t_values and y_values must have the same length.")
        self._series_store[signal.hash_name] = (t_list, y_list)

    def append_samples(
        self,
        signal: Signal,
        t_new: Iterable[float],
        y_new: Iterable[float],
        *,
        max_points: int | None = None,
    ) -> None:
        """Append new samples to an existing series, with optional truncation."""
        t_add = [float(v) for v in t_new]
        y_add = [float(v) for v in y_new]
        if not t_add:
            return
        if len(t_add) != len(y_add):
            raise ValueError("t_new and y_new must have the same length.")

        old = self._series_store.get(signal.hash_name)
        if old is None:
            t_all, y_all = t_add, y_add
        else:
            t_old, y_old = old
            t_all = list(t_old) + t_add
            y_all = list(y_old) + y_add

        if max_points is not None and max_points > 0 and len(t_all) > max_points:
            start = len(t_all) - max_points
            t_all = t_all[start:]
            y_all = y_all[start:]

        self._series_store[signal.hash_name] = (t_all, y_all)

    def get_series(self, signal: Signal) -> tuple[list[float], list[float]]:
        """Return copies of the stored series for a signal (t, y)."""
        pair = self._series_store.get(signal.hash_name)
        if pair is None:
            return ([], [])
        t, y = pair
        return (list(t), list(y))


class Model:
    """Model aggregate owning root object and shared context."""

    def __init__(self, root: ComplexInstance, *, context: ModelContext | None = None, load_existing_ids: bool = True) -> None:
        self.context = context or ModelContext()
        self.context.model = self
        self.root = root
        self.variable_registry = VariableNameRegistry()
        self.attach(root, parent=None, reserve_existing=load_existing_ids, remap_ids=not load_existing_ids)
        self._ensure_main_output_color()
        self._ensure_trash_folder()
        self._ensure_simulation_mode_attribute()
        self._ensure_last_selected_dataviewer_attribute()
        self._ensure_measurements_tree()
        self._ensure_variable_database_tree()
        self.sync_variable_mapping_entries()

    @classmethod
    def new(cls, root_name: str = "root") -> Model:
        return cls(ComplexInstance(name=root_name), load_existing_ids=False)

    def _ensure_main_output_color(self) -> None:
        # CLI output color configured on the root object ("main"), HTML-style hex code.
        if self.root.name != "main":
            return
        if "output_color" in self.root.attribute_dict:
            return
        dict.__setitem__(
            self.root.attribute_dict,
            "output_color",
            ("#ADD8E6", None, None, True, True),  # default: light blue
        )

    def _ensure_simulation_mode_attribute(self) -> None:
        """Studio/console: ``set @main.simulation_mode true|false`` toggles diagram simulation mode."""
        if "simulation_mode" in self.root.attribute_dict:
            return
        dict.__setitem__(self.root.attribute_dict, "simulation_mode", (False, None, None, True, True))

    def _ensure_last_selected_dataviewer_attribute(self) -> None:
        """Default data viewer for the measure dialog; ``-1`` means none."""
        if self.root.name != "main":
            return
        if "last_selected_dataviewer_id" in self.root.attribute_dict:
            return
        dict.__setitem__(self.root.attribute_dict, "last_selected_dataviewer_id", (-1, None, None, True, True))

    # ---- measurements / stimuli / recording ---------------------------------

    def _ensure_measurements_tree(self) -> None:
        """Ensure ``measurements`` subtree with ``stimuli`` and ``recording`` containers exists."""
        if self.root.name != "main":
            return

        measurements = None
        for c in self.root.children:
            if isinstance(c, ComplexInstance) and c.name == "measurements":
                measurements = c
                break

        if measurements is None:
            measurements = ComplexInstance(name="measurements")
            self.attach(measurements, parent=self.root, reserve_existing=False, remap_ids=False)

        # Create or reuse dedicated signal containers for stimuli/recording.
        stimuli = None
        recording = None
        for c in measurements.children:
            if isinstance(c, SignalContainer) and c.name == "stimuli":
                stimuli = c
            elif isinstance(c, SignalContainer) and c.name == "recording":
                recording = c

        if stimuli is None:
            stimuli = SignalContainer(
                name="stimuli",
                model_element_type=ModelElementType.MODEL_STIMULI,
            )
            self.attach(stimuli, parent=measurements, reserve_existing=False, remap_ids=False)

        if recording is None:
            recording = SignalContainer(
                name="recording",
                model_element_type=ModelElementType.MODEL_RECORDING,
            )
            self.attach(recording, parent=measurements, reserve_existing=False, remap_ids=False)

    def _ensure_variable_database_tree(self) -> None:
        """Ensure ``variables_db`` under ``@main`` exists for name->signal mappings."""
        if self.root.name != "main":
            return
        for c in self.root.children:
            if isinstance(c, VariableDatabase) and c.name == "variables_db":
                return
        db = VariableDatabase(name="variables_db")
        self.attach(db, parent=self.root, reserve_existing=False, remap_ids=False)

    def get_variable_database(self) -> VariableDatabase | None:
        if self.root.name != "main":
            return None
        for c in self.root.children:
            if isinstance(c, VariableDatabase) and c.name == "variables_db":
                return c
        return None

    def sync_variable_mapping_entries(self) -> None:
        """Keep ``variables_db`` entries aligned with variable-name registry."""
        db = self.get_variable_database()
        if db is None:
            return
        names = {name for name, _count, _mapped in self.variable_registry.rows_ordered_by_name()}
        existing: dict[str, VariableMappingEntry] = {}
        for child in db.children:
            if isinstance(child, VariableMappingEntry):
                existing[child.name] = child
        # Remove stale entries.
        for name, entry in list(existing.items()):
            if name in names:
                continue
            if entry.id is not None:
                self.delete(db, entry.id)
            existing.pop(name, None)
        # Create missing entries.
        for name in sorted(names):
            if name in existing:
                continue
            self.attach(
                VariableMappingEntry(
                    variable_name=name,
                    mapped_signal=self.variable_registry.mapped_signal_for_name(name),
                ),
                parent=db,
                reserve_existing=False,
                remap_ids=False,
            )
        # Refresh mirrored entry values from SQL registry.
        for child in db.children:
            if not isinstance(child, VariableMappingEntry):
                continue
            try:
                child.set("mapped_signal", self.variable_registry.mapped_signal_for_name(child.name))
            except Exception:
                continue

    def variable_mapped_signal(self, variable_name: str) -> str:
        return self.variable_registry.mapped_signal_for_name(variable_name)

    def set_variable_mapped_signal(self, variable_name: str, signal_name: str | None) -> None:
        self.variable_registry.set_mapped_signal_for_name(variable_name, signal_name)
        db = self.get_variable_database()
        if db is None:
            return
        entry = db.entry_for_name(variable_name)
        if entry is None:
            return
        try:
            entry.set("mapped_signal", self.variable_registry.mapped_signal_for_name(variable_name))
        except Exception:
            pass

    # ---- root lookups --------------------------------------------------------

    def get_root_by_type(self, element_type: ModelElementType) -> BaseObject | None:
        """Return a well-known root object by logical type, if present."""
        if element_type == ModelElementType.MODEL_COMPLEX:
            return self.root
        if element_type == ModelElementType.MODEL_MEASUREMENTS:
            for c in self.root.children:
                if isinstance(c, ComplexInstance) and c.name == "measurements":
                    return c
            return None
        if element_type in (ModelElementType.MODEL_STIMULI, ModelElementType.MODEL_RECORDING):
            measurements = self.get_root_by_type(ModelElementType.MODEL_MEASUREMENTS)
            if not isinstance(measurements, ComplexInstance):
                return None
            target_name = "stimuli" if element_type == ModelElementType.MODEL_STIMULI else "recording"
            for c in measurements.children:
                if isinstance(c, SignalContainer) and c.name == target_name:
                    return c
            return None
        if element_type == ModelElementType.MODEL_VARIABLE_DATABASE:
            return self.get_variable_database()
        return None

    def allocate_dataviewer_id(self) -> int:
        """Next free viewer id (max existing ``dataviewer_id`` + 1)."""
        m = 0
        for node in _iter_subtree(self.root):
            if isinstance(node, DataViewer):
                try:
                    m = max(m, int(node.get("dataviewer_id")))
                except (KeyError, TypeError, ValueError):
                    continue
        return m + 1

    def iter_dataviewers(self) -> list[DataViewer]:
        found = [n for n in _iter_subtree(self.root) if isinstance(n, DataViewer) and not self.is_in_trash_subtree(n)]
        found.sort(key=lambda d: int(d.get("dataviewer_id")))
        return found

    def _ensure_trash_folder(self) -> ComplexInstance:
        """Ensure a single ``trash`` :class:`ComplexInstance` exists directly under the model root."""
        for c in self.root.children:
            if isinstance(c, ComplexInstance) and c.name == "trash":
                return c
        t = ComplexInstance(name="trash")
        self.attach(t, parent=self.root, reserve_existing=False, remap_ids=False)
        return t

    def get_trash_folder(self) -> ComplexInstance:
        """Return the trash container (child ``trash`` of the model root)."""
        return self._ensure_trash_folder()

    def is_in_trash_subtree(self, node: BaseObject) -> bool:
        """True if ``node`` is stored under the trash folder (not the trash folder itself)."""
        trash = self.get_trash_folder()
        p = node.parent
        while p is not None:
            if p is trash:
                return True
            p = p.parent
        return False

    def _will_be_in_trash_subtree_after_reparent(self, new_parent: ComplexInstance) -> bool:
        trash = self.get_trash_folder()
        p: BaseObject | None = new_parent
        while p is not None:
            if p is trash:
                return True
            p = p.parent
        return False

    def reparent(self, node: BaseObject, new_parent: ComplexInstance) -> None:
        """Move ``node`` to ``new_parent`` without cloning; updates variable registry across trash boundary."""
        if node is self.root:
            raise ValueError("Cannot reparent the model root.")
        if new_parent.context is not self.context:
            raise DetachedObjectError("new_parent must belong to this model.")
        trash = self.get_trash_folder()
        if node is trash:
            raise ValueError("Cannot reparent the trash folder.")
        old_parent = node.parent
        if old_parent is None or not isinstance(old_parent, ComplexInstance):
            raise ValueError("Node has no container parent to reparent from.")
        oid = node.id
        if oid is None:
            raise ValueError("Node has no id.")

        p: BaseObject | None = new_parent
        while p is not None:
            if p is node:
                raise ValueError("Cannot move a container into its own subtree.")
            p = p.parent

        was_trash = self.is_in_trash_subtree(node)
        will_trash = self._will_be_in_trash_subtree_after_reparent(new_parent)
        if was_trash != will_trash:
            for n in _iter_subtree(node):
                if isinstance(n, Variable):
                    if was_trash and not will_trash:
                        self.variable_registry.increment(n.name)
                    elif not was_trash and will_trash:
                        self.variable_registry.decrement(n.name)

        old_parent.del_(oid)
        new_parent.paste(node)
        self.sync_variable_mapping_entries()

    def get_root(self) -> ComplexInstance:
        return self.root

    def get_root_model(self) -> Model:
        return self

    def iter_objects(self) -> Iterator[BaseObject]:
        """Depth-first iteration of all objects in the model (root first)."""
        yield from _iter_subtree(self.root)

    def find_by_id(self, obj_id: UUID) -> BaseObject | None:
        for node in _iter_subtree(self.root):
            if node.id == obj_id:
                return node
        return None

    def rebuild_variable_registry(self) -> None:
        """Recount variables outside the trash subtree (repair if registry drifted)."""
        self.variable_registry.clear()
        for node in _iter_subtree(self.root):
            if isinstance(node, Variable) and not self.is_in_trash_subtree(node):
                self.variable_registry.increment(node.name)
        self.sync_variable_mapping_entries()

    def short_id(self, obj_id: UUID, *, min_len: int = 1) -> str:
        """Return the shortest unique hex prefix for obj_id within this model."""
        hex_id = obj_id.hex
        all_hex = [node.id.hex for node in _iter_subtree(self.root) if node.id is not None]
        for length in range(max(1, min_len), len(hex_id) + 1):
            prefix = hex_id[:length]
            if sum(1 for h in all_hex if h.startswith(prefix)) == 1:
                return prefix
        return hex_id

    def clone(self) -> Model:
        """Create a detached clone of this model keeping existing IDs."""
        root_clone = _clone_for_paste(self.root, keep_ids=True)
        if not isinstance(root_clone, ComplexInstance):
            raise TypeError("Model root clone must be a ComplexInstance.")
        return Model(root_clone, load_existing_ids=True)

    def attach(
        self,
        obj: BaseObject,
        *,
        parent: ComplexInstance | None,
        reserve_existing: bool,
        remap_ids: bool,
    ) -> BaseObject:
        if parent is not None and parent.context is not self.context:
            raise DetachedObjectError("Parent must be attached to this model.")

        if remap_ids:
            for node in _iter_subtree(obj):
                node._id = None
                node._refresh_hash_name()

        self._assign_subtree(obj, parent=parent, reserve_existing=reserve_existing)
        return obj

    def _assign_subtree(self, obj: BaseObject, *, parent: ComplexInstance | None, reserve_existing: bool) -> None:
        obj._assign_context(self.context)
        obj.parent = parent

        if obj.id is None:
            obj._id = self.context.id_factory.new_id()
            obj._refresh_hash_name()
        elif reserve_existing:
            self.context.id_factory.reserve(obj.id)
        else:
            # If caller says "do not reserve existing", force a fresh model-local ID.
            obj._id = self.context.id_factory.new_id()
            obj._refresh_hash_name()

        if parent is not None and obj not in parent.children:
            parent.paste(obj)

        if isinstance(obj, Variable):
            self.variable_registry.increment(obj.name)
        elif isinstance(obj, ComplexInstance):
            for child in list(obj.children):
                self._assign_subtree(child, parent=obj, reserve_existing=reserve_existing)
        if isinstance(obj, (Variable, ComplexInstance)):
            self.sync_variable_mapping_entries()

    def delete(self, container: ComplexInstance, obj_id: UUID) -> None:
        victim = container.get_child(str(obj_id))
        if victim is None:
            return
        for node in _iter_subtree(victim):
            if isinstance(node, Variable):
                self.variable_registry.decrement(node.name)
        for node in _iter_subtree(victim):
            if node.id is not None:
                self.context.id_factory.unregister(node.id)
            node._detach_context()
            node.parent = None
        container.del_(obj_id)
        self.sync_variable_mapping_entries()

    def paste(self, container: ComplexInstance, obj: BaseObject, *, remap_ids: bool = True) -> BaseObject:
        clone = _clone_for_paste(obj, keep_ids=not remap_ids)
        return self.attach(clone, parent=container, reserve_existing=not remap_ids, remap_ids=remap_ids)

    def import_object(self, container: ComplexInstance, obj: BaseObject, *, keep_ids_if_free: bool = False) -> BaseObject:
        if keep_ids_if_free:
            return self.attach(
                _clone_for_paste(obj, keep_ids=True),
                parent=container,
                reserve_existing=True,
                remap_ids=False,
            )
        return self.paste(container, obj, remap_ids=True)


class Connector(BaseObject):
    def __init__(
        self,
        *,
        name: str,
        source_instance_id: UUID,
        source_pin: str,
        target_instance_id: UUID,
        target_pin: str,
        directed: bool = True,
        orthogonal_bends: Iterable[float] | None = None,
        obj_id: UUID | None = None,
        parent: ComplexInstance | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model_element_type=ModelElementType.MODEL_CONNECTOR,
            obj_id=obj_id,
            parent=parent,
        )
        self.source_instance_id = source_instance_id
        self.source_pin = source_pin
        self.target_instance_id = target_instance_id
        self.target_pin = target_pin
        self.directed = directed
        self._orthogonal_bends: list[float] = [float(x) for x in (orthogonal_bends or ())]
        self.attribute_dict.set_virtual(
            "orthogonal_bends",
            getter=self._get_orthogonal_bends_virtual,
            setter=self._set_orthogonal_bends,
            writable=True,
        )

    def _get_orthogonal_bends_virtual(self) -> list[float]:
        """Expose absolute diagram coordinates (CLI / lsattr); internal storage is source-relative."""
        model = self.get_root_model()
        if model is None or not self._orthogonal_bends:
            return list(self._orthogonal_bends)
        from synarius_core.model.diagram_geometry import connector_source_pin_diagram_xy

        xy = connector_source_pin_diagram_xy(model, self)
        if xy is None:
            return list(self._orthogonal_bends)
        sx, sy = xy
        return bends_relative_to_absolute(sx, sy, self._orthogonal_bends)

    def _set_orthogonal_bends(self, value: Any) -> None:
        if value is None:
            self._orthogonal_bends = []
            self._touch()
            return
        if isinstance(value, str):
            parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
            abs_list = [float(p) for p in parts]
        elif isinstance(value, (list, tuple)):
            abs_list = [float(x) for x in value]
        else:
            raise TypeError("orthogonal_bends expects list/tuple of numbers or comma-separated string.")
        model = self.get_root_model()
        from synarius_core.model.diagram_geometry import connector_source_pin_diagram_xy

        xy = connector_source_pin_diagram_xy(model, self) if model is not None else None
        if xy is not None:
            sx, sy = xy
            self._orthogonal_bends = bends_absolute_to_relative(sx, sy, abs_list)
        else:
            self._orthogonal_bends = abs_list
        self._touch()

    def polyline_xy(
        self,
        source_xy: tuple[float, float],
        target_xy: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Scene/model-space vertices for current ``orthogonal_bends`` (or auto layout)."""
        sx, sy = source_xy
        tx, ty = target_xy
        if not self._orthogonal_bends:
            return polyline_for_endpoints(sx, sy, tx, ty, [])
        abs_b = bends_relative_to_absolute(sx, sy, self._orthogonal_bends)
        return polyline_for_endpoints(sx, sy, tx, ty, abs_b)

    def materialize_default_bends(self, source_xy: tuple[float, float], target_xy: tuple[float, float]) -> None:
        """If bends are empty, set default H–V–H bends when geometry needs a knee."""
        if self._orthogonal_bends:
            return
        sx, sy = source_xy
        tx, ty = target_xy
        b = auto_orthogonal_bends(sx, sy, tx, ty)
        if b:
            self._orthogonal_bends = bends_absolute_to_relative(sx, sy, b)
            self._touch()

    def apply_polyline(self, poly: list[tuple[float, float]], source_xy: tuple[float, float], target_xy: tuple[float, float]) -> None:
        """Replace bends from a full orthogonal polyline S→T."""
        sx, sy = source_xy
        tx, ty = target_xy
        enc = encode_bends_from_polyline(sx, sy, tx, ty, poly)
        self._orthogonal_bends = bends_absolute_to_relative(sx, sy, enc) if enc else []
        self._touch()

    def validate_endpoints(self) -> bool:
        return bool(self.source_pin) and bool(self.target_pin)

