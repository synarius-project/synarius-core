from __future__ import annotations

from typing import Iterator, Sequence
from uuid import UUID

from synarius_core.variable_registry import VariableNameRegistry

from .base import BaseObject, DetachedObjectError, ModelContext
from .clone import _clone_for_paste, _iter_subtree
from .complex_instance import ComplexInstance
from .diagram_blocks import DataViewer, Variable
from .element_type import ModelElementType
from .signals import SignalContainer, VariableDatabase, VariableMappingEntry


class Model:
    """Model aggregate owning root object and shared context."""

    def __init__(self, root: ComplexInstance, *, context: ModelContext | None = None, load_existing_ids: bool = True) -> None:
        self.context = context or ModelContext()
        self.context.model = self
        self.root = root
        self.variable_registry = VariableNameRegistry()
        self._parameter_runtime = None
        self.attach(root, parent=None, reserve_existing=load_existing_ids, remap_ids=not load_existing_ids)
        self._ensure_main_output_color()
        self._ensure_trash_folder()
        self._ensure_simulation_mode_attribute()
        self._ensure_simulation_steps_attribute()
        self._ensure_last_selected_dataviewer_attribute()
        self._ensure_dataviewer_open_widget_attributes()
        self._ensure_measurements_tree()
        self._ensure_variable_database_tree()
        self._ensure_parameters_tree()
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

    def _ensure_simulation_steps_attribute(self) -> None:
        """Studio/console: ``set @main.simulation_steps N`` sets the step count for the Step toolbar action."""
        if "simulation_steps" in self.root.attribute_dict:
            return
        dict.__setitem__(self.root.attribute_dict, "simulation_steps", (10, None, None, True, True))

    def _ensure_last_selected_dataviewer_attribute(self) -> None:
        """Default data viewer for the measure dialog; ``-1`` means none."""
        if self.root.name != "main":
            return
        if "last_selected_dataviewer_id" in self.root.attribute_dict:
            return
        dict.__setitem__(self.root.attribute_dict, "last_selected_dataviewer_id", (-1, None, None, True, True))

    def _ensure_dataviewer_open_widget_attributes(self) -> None:
        """Ensure each DataViewer has ``open_widget`` (for CCP ``set`` / Studio sync)."""
        for dv in self.iter_dataviewers():
            if "open_widget" in dv.attribute_dict:
                continue
            dict.__setitem__(dv.attribute_dict, "open_widget", (False, None, None, True, True))

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

    def parameter_runtime(self):
        if self._parameter_runtime is None:
            from synarius_core.parameters import ParameterRuntime

            self._parameter_runtime = ParameterRuntime(self)
        return self._parameter_runtime

    def _ensure_parameters_tree(self) -> None:
        if self.root.name != "main":
            return
        self.parameter_runtime().ensure_tree()

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
                child._mirror_mapped_signal_from_registry(
                    self.variable_registry.mapped_signal_for_name(child.name)
                )
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
            entry._mirror_mapped_signal_from_registry(
                self.variable_registry.mapped_signal_for_name(variable_name)
            )
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

    def next_dataviewer_default_position(self) -> tuple[float, float]:
        """Bottom-left default placement for a new DataViewer; subsequent viewers step right in one row.

        Model-space coordinates (scene uses UI_SCALE in Studio layout). Matches the layout used by
        ``new DataViewer`` when ``<x> <y>`` are omitted.
        """
        idx = len(self.iter_dataviewers())
        start_x = 20.0
        start_y = 440.0
        step_x = 80.0
        return (start_x + idx * step_x, start_y)

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
            self.sync_variable_mapping_entries()
        elif isinstance(obj, ComplexInstance):
            for child in list(obj.children):
                self._assign_subtree(child, parent=obj, reserve_existing=reserve_existing)

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

    def delete_many(self, items: Sequence[tuple[ComplexInstance, UUID]]) -> None:
        """Like :meth:`delete` for each pair, but ``sync_variable_mapping_entries`` runs once at the end."""
        if not items:
            return
        grouped: dict[ComplexInstance, set[UUID]] = {}
        for container, obj_id in items:
            grouped.setdefault(container, set()).add(obj_id)

        for container, target_ids in grouped.items():
            if not target_ids:
                continue
            kept_children: list[BaseObject] = []
            removed_any = False
            for child in list(container.children):
                cid = child.id
                if cid is None or cid not in target_ids:
                    kept_children.append(child)
                    continue
                removed_any = True
                for node in _iter_subtree(child):
                    if isinstance(node, Variable):
                        self.variable_registry.decrement(node.name)
                for node in _iter_subtree(child):
                    if node.id is not None:
                        self.context.id_factory.unregister(node.id)
                    node._detach_context()
                    node.parent = None
            if not removed_any:
                continue
            container.children = kept_children
            container.children_by_hash_name = {c.hash_name: c for c in kept_children}
            container._touch()
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
