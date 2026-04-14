from __future__ import annotations

from typing import Iterable
from uuid import UUID

from .base import BaseObject, LocatableInstance
from .element_type import ModelElementType
from .geometry import Point2D, Size2D


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
