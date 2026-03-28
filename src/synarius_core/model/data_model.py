from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import UUID, uuid4

from .attribute_dict import AttributeDict
from .element_type import ModelElementType
from .connector_routing import auto_orthogonal_bends, encode_bends_from_polyline, polyline_for_endpoints


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
        return self.attribute_dict[key]

    def set(self, key: str, value: Any) -> None:
        self.attribute_dict.set_value(key, value)
        self._touch()

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
        self.in_pins = list(in_pins or [])
        self.out_pins = list(out_pins or [])


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
        super().__init__(
            name=name,
            type_key=type_key,
            model_element_type=ModelElementType.MODEL_VARIABLE,
            obj_id=obj_id,
            **kwargs,
        )
        self.value: Any = value
        self.unit: str = unit


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
        return Variable(
            name=obj.name,
            type_key=obj.type_key,
            value=obj.value,
            unit=obj.unit,
            in_pins=list(obj.in_pins),
            out_pins=list(obj.out_pins),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
    if isinstance(obj, BasicOperator):
        return BasicOperator(
            name=obj.name,
            type_key=obj.type_key,
            operation=obj.operation,
            in_pins=list(obj.in_pins),
            out_pins=list(obj.out_pins),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
    if isinstance(obj, ElementaryInstance):
        return ElementaryInstance(
            name=obj.name,
            type_key=obj.type_key,
            in_pins=list(obj.in_pins),
            out_pins=list(obj.out_pins),
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
    if isinstance(obj, ComplexInstance):
        cloned = ComplexInstance(
            name=obj.name,
            position=obj.position,
            size=obj.size,
            obj_id=obj_id,
        )
        for child in obj.children:
            cloned.paste(_clone_for_paste(child, keep_ids=keep_ids))
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


class Model:
    """Model aggregate owning root object and shared context."""

    def __init__(self, root: ComplexInstance, *, context: ModelContext | None = None, load_existing_ids: bool = True) -> None:
        self.context = context or ModelContext()
        self.context.model = self
        self.root = root
        self.attach(root, parent=None, reserve_existing=load_existing_ids, remap_ids=not load_existing_ids)
        self._ensure_main_output_color()

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

    def get_root(self) -> ComplexInstance:
        return self.root

    def get_root_model(self) -> Model:
        return self

    def find_by_id(self, obj_id: UUID) -> BaseObject | None:
        for node in _iter_subtree(self.root):
            if node.id == obj_id:
                return node
        return None

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

        if isinstance(obj, ComplexInstance):
            for child in list(obj.children):
                self._assign_subtree(child, parent=obj, reserve_existing=reserve_existing)

    def delete(self, container: ComplexInstance, obj_id: UUID) -> None:
        victim = container.get_child(str(obj_id))
        if victim is None:
            return
        for node in _iter_subtree(victim):
            if node.id is not None:
                self.context.id_factory.unregister(node.id)
            node._detach_context()
            node.parent = None
        container.del_(obj_id)

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
            getter=lambda: list(self._orthogonal_bends),
            setter=self._set_orthogonal_bends,
            writable=True,
        )

    def _set_orthogonal_bends(self, value: Any) -> None:
        if value is None:
            self._orthogonal_bends = []
            self._touch()
            return
        if isinstance(value, str):
            parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
            self._orthogonal_bends = [float(p) for p in parts]
            self._touch()
            return
        if isinstance(value, (list, tuple)):
            self._orthogonal_bends = [float(x) for x in value]
            self._touch()
            return
        raise TypeError("orthogonal_bends expects list/tuple of numbers or comma-separated string.")

    def polyline_xy(
        self,
        source_xy: tuple[float, float],
        target_xy: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Scene/model-space vertices for current ``orthogonal_bends`` (or auto layout)."""
        sx, sy = source_xy
        tx, ty = target_xy
        return polyline_for_endpoints(sx, sy, tx, ty, self._orthogonal_bends)

    def materialize_default_bends(self, source_xy: tuple[float, float], target_xy: tuple[float, float]) -> None:
        """If bends are empty, set default H–V–H bends when geometry needs a knee."""
        if self._orthogonal_bends:
            return
        sx, sy = source_xy
        tx, ty = target_xy
        b = auto_orthogonal_bends(sx, sy, tx, ty)
        if b:
            self._orthogonal_bends = b
            self._touch()

    def apply_polyline(self, poly: list[tuple[float, float]], source_xy: tuple[float, float], target_xy: tuple[float, float]) -> None:
        """Replace bends from a full orthogonal polyline S→T."""
        sx, sy = source_xy
        tx, ty = target_xy
        self._orthogonal_bends = encode_bends_from_polyline(sx, sy, tx, ty, poly)
        self._touch()

    def validate_endpoints(self) -> bool:
        return bool(self.source_pin) and bool(self.target_pin)

