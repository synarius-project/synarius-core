from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from .complex_instance import ComplexInstance
    from .root_model import Model

from synarius_core.variable_naming import validate_pin_name

from .attribute_dict import AttributeDict, AttributeEntry
from .attribute_path import deep_copy_mapping_tree, split_attribute_path
from .element_type import ModelElementType
from .geometry import Point2D, Size2D


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
            getter=lambda: dict.__getitem__(self.attribute_dict, "created_at").value,
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "updated_at",
            getter=lambda: dict.__getitem__(self.attribute_dict, "updated_at").value,
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
            AttributeEntry.stored(_utcnow()),
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
