from __future__ import annotations

from collections.abc import Callable
from typing import Any, Sequence, cast
from uuid import UUID

import numpy as np

from synarius_core.model.data_model import ComplexInstance, Model

from .repository import CalParamImportPrepared, ParametersRepository


class ParameterRuntime:
    """Bridges model ``parameters`` subtree and :class:`ParametersRepository`.

    The DuckDB repository is created lazily on first :attr:`repo` access so
    ``Model.new("main")`` does not block GUI startup on ``duckdb.connect``.
    """

    __slots__ = ("model", "_repo", "_active_dataset_name")

    def __init__(self, model: Model) -> None:
        self.model = model
        self._repo: ParametersRepository | None = None
        self._active_dataset_name = None

    @property
    def repo(self) -> ParametersRepository:
        r = self._repo
        if r is None:
            r = ParametersRepository()
            self._repo = r
        return r

    # ---- tree -------------------------------------------------------------

    def ensure_tree(self) -> None:
        if self.model.root.name != "main":
            return
        p = self.parameters_root()
        _ = self._ensure_child_container(p, "data_sets", "MODEL.PARAMETER_DATA_SETS")
        if "active_dataset_name" not in p.attribute_dict:
            p.attribute_dict.set_virtual(
                "active_dataset_name",
                getter=lambda: self._active_dataset_name,
                setter=lambda v: self.set_active_dataset_name(None if v in (None, "", "None") else str(v)),
                writable=True,
            )
        self._ensure_num_params_virtual_on_all_datasets()

    def parameters_root(self) -> ComplexInstance:
        for c in self.model.root.children:
            if isinstance(c, ComplexInstance) and c.name == "parameters":
                c.attribute_dict["type"] = "MODEL.PARAMETERS"
                return c
        p = ComplexInstance(name="parameters")
        self.model.attach(p, parent=self.model.root, reserve_existing=False, remap_ids=False)
        p.attribute_dict["type"] = "MODEL.PARAMETERS"
        return p

    def _ensure_child_container(self, parent: ComplexInstance, name: str, type_name: str) -> ComplexInstance:
        for c in parent.children:
            if isinstance(c, ComplexInstance) and c.name == name:
                c.attribute_dict["type"] = type_name
                return c
        node = ComplexInstance(name=name)
        self.model.attach(node, parent=parent, reserve_existing=False, remap_ids=False)
        node.attribute_dict["type"] = type_name
        return node

    def data_sets_root(self) -> ComplexInstance:
        return self._ensure_child_container(self.parameters_root(), "data_sets", "MODEL.PARAMETER_DATA_SETS")

    @staticmethod
    def _node_type(node: ComplexInstance | None) -> str:
        if node is None:
            return ""
        try:
            return str(node.get("type"))
        except Exception:
            return ""

    def _is_data_set_node(self, node: ComplexInstance | None) -> bool:
        return self._node_type(node) == "MODEL.PARAMETER_DATA_SET"

    def _dataset_ancestor_for_node(self, node: ComplexInstance | None) -> ComplexInstance | None:
        cur = node
        while isinstance(cur, ComplexInstance):
            if self._is_data_set_node(cur):
                return cur
            cur = cur.parent
        return None

    # ---- refs -------------------------------------------------------------

    def _find_dataset_by_name(self, name: str) -> ComplexInstance | None:
        root = self.data_sets_root()
        matches: list[ComplexInstance] = []
        for c in root.children:
            if isinstance(c, ComplexInstance) and c.name == name:
                matches.append(c)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        # Duplicate data set names: the first child wins for iteration order only — that can
        # pick a stale node without a DuckDB row (e.g. two "parawiz_target" after reload).
        # Prefer any node registered in the parameters repository.
        repo = self.repo
        registered = [m for m in matches if m.id is not None and repo.get_dataset_name(m.id) is not None]
        if len(registered) == 1:
            return registered[0]
        if len(registered) > 1:
            return registered[0]
        return matches[0]

    def active_dataset(self) -> ComplexInstance | None:
        raw = self._active_dataset_name
        if raw in (None, "", "None"):
            return None
        return self._find_dataset_by_name(str(raw))

    def set_active_dataset_name(self, name: str | None) -> None:
        if name in (None, "", "None"):
            self._active_dataset_name = None
            return
        ds = self._find_dataset_by_name(str(name))
        if ds is None:
            raise ValueError("active_dataset_name must reference an existing data_set name")
        self._active_dataset_name = ds.name

    # ---- registrations ----------------------------------------------------

    def register_data_set_node(
        self,
        node: ComplexInstance,
        *,
        source_path: str = "",
        source_format: str = "unknown",
        source_hash: str = "",
    ) -> None:
        if node.id is None:
            raise ValueError("data_set node must be attached before registration")
        parent = node.parent
        if not isinstance(parent, ComplexInstance) or self._node_type(parent) != "MODEL.PARAMETER_DATA_SETS":
            raise ValueError("data_set must be created directly under parameters/data_sets")
        node.attribute_dict["type"] = "MODEL.PARAMETER_DATA_SET"
        for key, value in (
            ("source_path", str(source_path)),
            ("source_format", str(source_format)),
            ("source_hash", str(source_hash)),
        ):
            if key not in node.attribute_dict:
                dict.__setitem__(node.attribute_dict, key, (value, None, None, True, True))
            else:
                node.set(key, value)
        self.repo.register_data_set(
            data_set_id=node.id,
            name=node.name,
            source_path=str(source_path),
            source_format=str(source_format),
            source_hash=str(source_hash),
        )
        if self._active_dataset_name in (None, "", "None"):
            self._active_dataset_name = node.name
        self._install_num_params_virtual(node)

    def clear_all_parameters_in_data_set(self, ds_node: ComplexInstance) -> int:
        """Remove all ``MODEL.CAL_PARAM`` descendants and DuckDB parameter rows; keep the data set row and node.

        Returns the number of parameters removed from the repository.
        """
        if not self._is_data_set_node(ds_node) or ds_node.id is None:
            raise ValueError("clear_all_parameters_in_data_set requires a MODEL.PARAMETER_DATA_SET with id")
        ds_id = ds_node.id
        pairs: list[tuple[ComplexInstance, UUID]] = []
        stack: list[ComplexInstance] = [ds_node]
        while stack:
            cur = stack.pop()
            for child in list(cur.children):
                if isinstance(child, ComplexInstance):
                    stack.append(child)
                    if self._node_type(child) == "MODEL.CAL_PARAM" and child.id is not None:
                        pairs.append((cur, child.id))
        if pairs:
            self.model.delete_many(pairs)
        return self.repo.delete_parameters_for_data_set(ds_id, remove_data_set_row=False)

    def _ensure_num_params_virtual_on_all_datasets(self) -> None:
        root = self.data_sets_root()
        for c in list(root.children):
            if isinstance(c, ComplexInstance) and self._is_data_set_node(c) and c.id is not None:
                self._install_num_params_virtual(c)

    def _install_num_params_virtual(self, node: ComplexInstance) -> None:
        """Virtual ``num_params``: read-only count from DuckDB; write only ``0`` clears parameters (CCP ``set``)."""
        if not self._is_data_set_node(node) or node.id is None:
            return
        if "num_params" in node.attribute_dict:
            return
        ds_id = cast(UUID, node.id)
        rt = self

        def getter() -> int:
            return rt.repo.count_parameters_for_data_set(ds_id)

        def setter(v: Any) -> None:
            if isinstance(v, bool):
                raise ValueError("num_params does not accept boolean values")
            if isinstance(v, float):
                if not v.is_integer():
                    raise ValueError("num_params must be an integer")
                iv = int(v)
            elif isinstance(v, int):
                iv = v
            else:
                try:
                    iv = int(v)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"num_params expects integer 0 to clear all parameters, got {v!r}"
                    ) from exc
            if iv != 0:
                raise ValueError(
                    "num_params may only be written as 0 (removes all parameters in this data set; "
                    "the MODEL.PARAMETER_DATA_SET node and data_sets row are kept)"
                )
            rt.clear_all_parameters_in_data_set(node)

        node.attribute_dict.set_virtual(
            "num_params",
            getter=getter,
            setter=setter,
            exposed=True,
            writable=True,
        )

    def register_data_container_node(self, node: ComplexInstance) -> None:
        parent = node.parent
        if not isinstance(parent, ComplexInstance) or not self._is_data_set_node(parent):
            raise ValueError("data_container must be created as direct child of a data_set")
        node.attribute_dict["type"] = "MODEL.PARAMETER_DATA_CONTAINER"
        if "container_type" not in node.attribute_dict:
            dict.__setitem__(node.attribute_dict, "container_type", ("GROUP", None, None, True, True))

    def register_cal_param_node(
        self,
        node: ComplexInstance,
        *,
        data_set_id: UUID | None,
        category: str = "VALUE",
    ) -> None:
        if node.id is None:
            raise ValueError("cal_param node must be attached before registration")
        parent = node.parent if isinstance(node.parent, ComplexInstance) else None
        parent_is_dataset = self._is_data_set_node(parent)
        parent_is_container = self._node_type(parent) == "MODEL.PARAMETER_DATA_CONTAINER"
        if not (parent_is_dataset or parent_is_container):
            raise ValueError("cal_param must be created under a data_set or data_container")
        owner_data_set = self._dataset_ancestor_for_node(parent)
        if owner_data_set is None or owner_data_set.id is None:
            raise ValueError("cal_param parent must belong to an attached data_set")
        owner_data_set_id = owner_data_set.id
        if data_set_id is None:
            data_set_id = owner_data_set_id
        elif data_set_id != owner_data_set_id:
            raise ValueError("cal_param data_set=... must match the parent data_set")
        node.attribute_dict["type"] = "MODEL.CAL_PARAM"
        if "data_set_id" in node.attribute_dict:
            try:
                existing = UUID(str(node.get("data_set_id")))
            except Exception as exc:
                raise ValueError("cal_param has invalid existing data_set_id attribute") from exc
            if existing != data_set_id:
                raise ValueError("cal_param existing data_set_id conflicts with resolved parent data_set")
        else:
            dict.__setitem__(node.attribute_dict, "data_set_id", (str(data_set_id), None, None, True, False))
        self.repo.register_parameter(
            parameter_id=node.id,
            data_set_id=data_set_id,
            name=node.name,
            category=category,
        )
        self._install_cal_param_virtuals(node)

    def register_cal_param_node_from_import(
        self,
        node: ComplexInstance,
        *,
        data_set_id: UUID | None,
        category: str,
        display_name: str = "",
        unit: str = "",
        source_identifier: str = "",
        values: np.ndarray,
        axes: dict[int, np.ndarray],
        axis_names: dict[int, str],
        axis_units: dict[int, str],
    ) -> None:
        """Register a cal_param and write payload in one repository path (e.g. DCM bulk import)."""
        if node.id is None:
            raise ValueError("cal_param node must be attached before registration")
        parent = node.parent if isinstance(node.parent, ComplexInstance) else None
        owner_data_set = self._dataset_ancestor_for_node(parent)
        if owner_data_set is None or owner_data_set.id is None:
            raise ValueError("imported cal_param must be attached under a data_set subtree")
        owner_data_set_id = owner_data_set.id
        if data_set_id is None:
            data_set_id = owner_data_set_id
        elif data_set_id != owner_data_set_id:
            raise ValueError("imported cal_param data_set_id must match parent data_set")
        node.attribute_dict["type"] = "MODEL.CAL_PARAM"
        if "data_set_id" in node.attribute_dict:
            try:
                existing = UUID(str(node.get("data_set_id")))
            except Exception as exc:
                raise ValueError("imported cal_param has invalid existing data_set_id attribute") from exc
            if existing != data_set_id:
                raise ValueError("imported cal_param existing data_set_id conflicts with parent data_set")
        else:
            dict.__setitem__(node.attribute_dict, "data_set_id", (str(data_set_id), None, None, True, False))
        self.repo.write_cal_param_import(
            parameter_id=node.id,
            data_set_id=data_set_id,
            name=node.name,
            category=category,
            display_name=str(display_name),
            unit=str(unit),
            source_identifier=str(source_identifier),
            values=values,
            axes=axes,
            axis_names=axis_names,
            axis_units=axis_units,
        )
        self._install_cal_param_virtuals(node)

    def register_cal_param_nodes_bulk_from_import(
        self,
        pairs: Sequence[tuple[ComplexInstance, CalParamImportPrepared]],
        *,
        cooperative_hook: Callable[[], None] | None = None,
        write_progress_hook: Callable[[int, int], None] | None = None,
        virtual_progress_hook: Callable[[int, int], None] | None = None,
        virtual_progress_every: int = 80,
    ) -> None:
        """Attach path already done; set model attrs, one transactional DuckDB bulk write, then virtuals."""
        if not pairs:
            return
        for node, prep in pairs:
            if node.id is None:
                raise ValueError("cal_param node must be attached before registration")
            if node.id != prep.parameter_id:
                raise ValueError("prepared row parameter_id must match attached node id")
            parent = node.parent if isinstance(node.parent, ComplexInstance) else None
            owner_data_set = self._dataset_ancestor_for_node(parent)
            if owner_data_set is None or owner_data_set.id is None:
                raise ValueError("imported cal_param must be attached under a data_set subtree")
            if owner_data_set.id != prep.data_set_id:
                raise ValueError("prepared row data_set_id must match parent data_set")
            node.attribute_dict["type"] = "MODEL.CAL_PARAM"
            if "data_set_id" in node.attribute_dict:
                try:
                    existing = UUID(str(node.get("data_set_id")))
                except Exception as exc:
                    raise ValueError("imported cal_param has invalid existing data_set_id attribute") from exc
                if existing != prep.data_set_id:
                    raise ValueError("imported cal_param existing data_set_id conflicts with parent data_set")
            else:
                dict.__setitem__(
                    node.attribute_dict,
                    "data_set_id",
                    (str(prep.data_set_id), None, None, True, False),
                )
        prepared = [p for _, p in pairs]
        with self.repo.transaction():
            self.repo.write_cal_params_import_bulk(
                prepared,
                cooperative_hook=cooperative_hook,
                write_progress_hook=write_progress_hook,
            )
        total = len(pairs)
        if cooperative_hook is not None:
            cooperative_hook()
        if virtual_progress_hook is not None:
            virtual_progress_hook(0, total)
        for k, (node, _) in enumerate(pairs):
            self._install_cal_param_virtuals(node)
            done = k + 1
            if virtual_progress_hook is not None and virtual_progress_every > 0 and done % virtual_progress_every == 0:
                virtual_progress_hook(done, total)
            if cooperative_hook is not None and virtual_progress_every > 0 and done % virtual_progress_every == 0:
                cooperative_hook()
        if virtual_progress_hook is not None:
            virtual_progress_hook(total, total)
        if cooperative_hook is not None:
            cooperative_hook()

    # ---- cal_param virtual attrs -----------------------------------------

    def _install_cal_param_virtuals(self, node: ComplexInstance) -> None:
        if node.id is None:
            raise ValueError("cal_param must have id")
        pid = node.id

        def _rec():
            return self.repo.get_record(pid)

        # metadata
        for attr in (
            "category",
            "display_name",
            "comment",
            "unit",
            "conversion_ref",
            "source_identifier",
            "numeric_format",
            "value_semantics",
        ):
            node.attribute_dict.set_virtual(
                attr,
                getter=lambda a=attr: getattr(_rec(), a),
                setter=lambda v, a=attr: self.repo.set_meta_field(pid, a, v),
                writable=True,
            )

        # values and shape (guarded)
        node.attribute_dict.set_virtual(
            "value",
            getter=lambda: self.repo.get_value(pid),
            setter=lambda v: self.repo.set_value(pid, v),
            writable=True,
        )
        node.attribute_dict.set_virtual(
            "shape",
            getter=lambda: list(self.repo.get_record(pid).values.shape),
            setter=lambda v: self.repo.reshape(pid, self._parse_shape(v)),
            writable=True,
        )
        # xN_dim virtual attrs (equivalent to shape update only on axis N)
        for axis_idx in range(5):
            key = f"x{axis_idx + 1}_dim"
            node.attribute_dict.set_virtual(
                key,
                getter=lambda i=axis_idx: self._get_axis_dim(pid, i),
                setter=lambda v, i=axis_idx: self.repo.set_axis_dim(pid, i, self._parse_pos_int(v)),
                writable=True,
            )
            axis_key = f"x{axis_idx + 1}_axis"
            node.attribute_dict.set_virtual(
                axis_key,
                getter=lambda i=axis_idx: self.repo.get_axis_values(pid, i).tolist(),
                setter=lambda v, i=axis_idx: self.repo.set_axis_values(pid, i, v),
                writable=True,
            )
            axis_name_key = f"x{axis_idx + 1}_name"
            node.attribute_dict.set_virtual(
                axis_name_key,
                getter=lambda i=axis_idx: self.repo.get_record(pid).axis_names.get(i, ""),
                setter=lambda v, i=axis_idx: self.repo.set_axis_meta_field(pid, i, "axis_name", v),
                writable=True,
            )
            axis_unit_key = f"x{axis_idx + 1}_unit"
            node.attribute_dict.set_virtual(
                axis_unit_key,
                getter=lambda i=axis_idx: self.repo.get_record(pid).axis_units.get(i, ""),
                setter=lambda v, i=axis_idx: self.repo.set_axis_meta_field(pid, i, "axis_unit", v),
                writable=True,
            )
        node.attribute_dict.set_virtual(
            "data_set_name",
            getter=lambda: self._dataset_name_for_param(pid),
            setter=None,
            writable=False,
        )

    def _dataset_name_for_param(self, parameter_id: UUID) -> str:
        rec = self.repo.get_record(parameter_id)
        name = self.repo.get_dataset_name(rec.data_set_id)
        return name or ""

    @staticmethod
    def _parse_shape(value: Any) -> tuple[int, ...]:
        if isinstance(value, str):
            text = value.strip().strip("[]")
            if text == "":
                return ()
            parts = [p.strip() for p in text.split(",") if p.strip()]
            dims = tuple(int(p) for p in parts)
        elif isinstance(value, (list, tuple)):
            dims = tuple(int(x) for x in value)
        else:
            raise ValueError("shape must be list/tuple or comma-separated string")
        if any(int(x) <= 0 for x in dims):
            raise ValueError("shape dimensions must be positive integers")
        return dims

    @staticmethod
    def _parse_pos_int(value: Any) -> int:
        out = int(value)
        if out <= 0:
            raise ValueError("dimension must be positive integer")
        return out

    def _get_axis_dim(self, parameter_id: UUID, axis_idx: int) -> int:
        rec = self.repo.get_record(parameter_id)
        if axis_idx >= rec.values.ndim:
            return 1
        return int(rec.values.shape[axis_idx])

