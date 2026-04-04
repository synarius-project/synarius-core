from __future__ import annotations

from typing import Any
from uuid import UUID

from synarius_core.model.data_model import ComplexInstance, Model

from .repository import ParametersRepository


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

    def parameters_root(self) -> ComplexInstance:
        for c in self.model.root.children:
            if isinstance(c, ComplexInstance) and c.name == "parameters":
                return c
        p = ComplexInstance(name="parameters")
        self.model.attach(p, parent=self.model.root, reserve_existing=False, remap_ids=False)
        p.attribute_dict["type"] = "MODEL.PARAMETERS"
        return p

    def _ensure_child_container(self, parent: ComplexInstance, name: str, type_name: str) -> ComplexInstance:
        for c in parent.children:
            if isinstance(c, ComplexInstance) and c.name == name:
                return c
        node = ComplexInstance(name=name)
        self.model.attach(node, parent=parent, reserve_existing=False, remap_ids=False)
        node.attribute_dict["type"] = type_name
        return node

    def data_sets_root(self) -> ComplexInstance:
        return self._ensure_child_container(self.parameters_root(), "data_sets", "MODEL.PARAMETER_DATA_SETS")

    # ---- refs -------------------------------------------------------------

    def _find_dataset_by_name(self, name: str) -> ComplexInstance | None:
        root = self.data_sets_root()
        for c in root.children:
            if isinstance(c, ComplexInstance) and c.name == name:
                return c
        return None

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

    def register_data_container_node(self, node: ComplexInstance) -> None:
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
        if data_set_id is None:
            active = self.active_dataset()
            if active is None or active.id is None:
                raise ValueError("cal_param requires a data_set (active_dataset_name is None)")
            data_set_id = active.id
        node.attribute_dict["type"] = "MODEL.CAL_PARAM"
        if "data_set_id" not in node.attribute_dict:
            dict.__setitem__(node.attribute_dict, "data_set_id", (str(data_set_id), None, None, True, False))
        self.repo.register_parameter(
            parameter_id=node.id,
            data_set_id=data_set_id,
            name=node.name,
            category=category,
        )
        self._install_cal_param_virtuals(node)

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

