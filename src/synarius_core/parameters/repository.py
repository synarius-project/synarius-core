from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
import json
from typing import Any
from uuid import UUID

import numpy as np


_TEXT_CATEGORIES = {"ASCII"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _readonly_array_copy(a: np.ndarray) -> np.ndarray:
    out = np.array(a, copy=True)
    out.setflags(write=False)
    return out


@dataclass(slots=True)
class ParameterRecord:
    parameter_id: UUID
    data_set_id: UUID
    name: str
    category: str = "VALUE"
    display_name: str = ""
    comment: str = ""
    unit: str = ""
    conversion_ref: str = ""
    source_identifier: str = ""
    numeric_format: str = "decimal"
    value_semantics: str = "physical"
    values: np.ndarray = field(default_factory=lambda: np.zeros((), dtype=np.float64))
    text_value: str = ""
    axes: dict[int, np.ndarray] = field(default_factory=dict)

    @property
    def is_text(self) -> bool:
        return str(self.category).upper() in _TEXT_CATEGORIES


class ParametersRepository:
    """DuckDB-backed repository (process-local in-memory by default)."""

    def __init__(self, *, database: str = ":memory:") -> None:
        # Local import: loading ``duckdb`` pulls in a native extension; keep it out of the
        # import graph for ``synarius_core.parameters`` so Studio can build ``Model`` first.
        import duckdb  # pyright: ignore[reportMissingImports]

        # Process-local in-memory DB by default to minimize accidental external mutation.
        self._con = duckdb.connect(database=database)
        self._init_schema()

    def _init_schema(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS data_sets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                source_format TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                import_time TEXT NOT NULL
            );
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS parameters_all (
                parameter_id TEXT PRIMARY KEY,
                data_set_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                display_name TEXT NOT NULL,
                comment TEXT NOT NULL,
                unit TEXT NOT NULL,
                conversion_ref TEXT NOT NULL,
                source_identifier TEXT NOT NULL,
                numeric_format TEXT NOT NULL,
                value_semantics TEXT NOT NULL,
                text_value TEXT NOT NULL
            );
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS parameter_values (
                parameter_id TEXT PRIMARY KEY,
                shape_json TEXT NOT NULL,
                values_npy BLOB NOT NULL
            );
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS parameter_axes (
                parameter_id TEXT NOT NULL,
                axis_index INTEGER NOT NULL,
                values_npy BLOB NOT NULL,
                PRIMARY KEY(parameter_id, axis_index)
            );
            """
        )

    # ---- dataset ----------------------------------------------------------

    def register_data_set(
        self,
        *,
        data_set_id: UUID,
        name: str,
        source_path: str = "",
        source_format: str = "unknown",
        source_hash: str = "",
    ) -> None:
        import_time = _now_iso() if (source_path or source_hash) else ""
        hit = self._con.execute("SELECT 1 FROM data_sets WHERE id = ?", [str(data_set_id)]).fetchone()
        if hit is None:
            self._con.execute(
                """
                INSERT INTO data_sets(id, name, source_format, source_path, source_hash, import_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    str(data_set_id),
                    str(name),
                    str(source_format),
                    str(source_path),
                    str(source_hash),
                    import_time,
                ],
            )
            return
        self._con.execute(
            """
            UPDATE data_sets
            SET name = ?, source_format = ?, source_path = ?, source_hash = ?, import_time = ?
            WHERE id = ?
            """,
            [
                str(name),
                str(source_format),
                str(source_path),
                str(source_hash),
                import_time,
                str(data_set_id),
            ],
        )

    # ---- parameter records ------------------------------------------------

    def register_parameter(
        self,
        *,
        parameter_id: UUID,
        data_set_id: UUID,
        name: str,
        category: str = "VALUE",
    ) -> None:
        if not self._exists_data_set(data_set_id):
            raise ValueError("parameter registration requires existing data_set_id")
        cat = str(category).upper()
        self._con.execute(
            """
            INSERT OR REPLACE INTO parameters_all(
                parameter_id, data_set_id, name, category, display_name, comment, unit,
                conversion_ref, source_identifier, numeric_format, value_semantics, text_value
            ) VALUES (?, ?, ?, ?, '', '', '', '', '', 'decimal', 'physical', '')
            """,
            [str(parameter_id), str(data_set_id), str(name), cat],
        )
        self._write_numeric_array(parameter_id, np.zeros((), dtype=np.float64))
        self._con.execute("DELETE FROM parameter_axes WHERE parameter_id = ?", [str(parameter_id)])

    def get_record(self, parameter_id: UUID) -> ParameterRecord:
        row = self._con.execute(
            """
            SELECT data_set_id, name, category, display_name, comment, unit,
                   conversion_ref, source_identifier, numeric_format, value_semantics, text_value
            FROM parameters_all
            WHERE parameter_id = ?
            """,
            [str(parameter_id)],
        ).fetchone()
        if row is None:
            raise ValueError("unknown parameter_id")
        data_set_id = UUID(str(row[0]))
        category = str(row[2]).upper()
        text_value = str(row[10])
        values = self._read_numeric_array(parameter_id)
        axes = self._read_axes(parameter_id)
        return ParameterRecord(
            parameter_id=parameter_id,
            data_set_id=data_set_id,
            name=str(row[1]),
            category=category,
            display_name=str(row[3]),
            comment=str(row[4]),
            unit=str(row[5]),
            conversion_ref=str(row[6]),
            source_identifier=str(row[7]),
            numeric_format=str(row[8]),
            value_semantics=str(row[9]),
            values=values,
            text_value=text_value,
            axes=axes,
        )

    def _ensure_dataset_ownership(self, rec: ParameterRecord) -> None:
        if not self._exists_data_set(rec.data_set_id):
            raise ValueError("mutable parameter state without valid data_set ownership")

    def _exists_data_set(self, data_set_id: UUID) -> bool:
        hit = self._con.execute("SELECT 1 FROM data_sets WHERE id = ?", [str(data_set_id)]).fetchone()
        return hit is not None

    # ---- generic fields ---------------------------------------------------

    def set_meta_field(self, parameter_id: UUID, field_name: str, value: Any) -> None:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if field_name == "category":
            self._set_category(rec, str(value).upper())
            return
        if field_name in {
            "display_name",
            "comment",
            "unit",
            "conversion_ref",
            "source_identifier",
            "numeric_format",
            "value_semantics",
            "name",
        }:
            self._con.execute(
                f"UPDATE parameters_all SET {field_name} = ? WHERE parameter_id = ?",
                [str(value), str(parameter_id)],
            )
            return
        raise ValueError(f"unsupported metadata field: {field_name}")

    def _set_category(self, rec: ParameterRecord, new_category: str) -> None:
        old_text = rec.is_text
        new_text = new_category in _TEXT_CATEGORIES
        if old_text != new_text:
            if old_text and rec.text_value not in ("",):
                raise ValueError("invalid category migration: text -> numeric with existing text payload")
            if (not old_text) and rec.values.size > 0 and np.any(np.asarray(rec.values) != 0):
                raise ValueError("invalid category migration: numeric -> text with non-zero numeric payload")
        if new_text:
            self._con.execute("DELETE FROM parameter_axes WHERE parameter_id = ?", [str(rec.parameter_id)])
            self._write_numeric_array(rec.parameter_id, np.zeros((), dtype=np.float64))
        else:
            cur = self._read_numeric_array(rec.parameter_id)
            if cur.size == 0:
                self._write_numeric_array(rec.parameter_id, np.zeros((), dtype=np.float64))
        self._con.execute(
            "UPDATE parameters_all SET category = ?, text_value = CASE WHEN ? THEN text_value ELSE '' END WHERE parameter_id = ?",
            [new_category, bool(new_text), str(rec.parameter_id)],
        )

    # ---- values -----------------------------------------------------------

    def set_value(self, parameter_id: UUID, value: Any) -> None:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if rec.is_text:
            self._con.execute(
                "UPDATE parameters_all SET text_value = ? WHERE parameter_id = ?",
                [str(value), str(parameter_id)],
            )
            return
        arr = np.asarray(value, dtype=np.float64)
        # deterministic full replace; shape follows provided payload
        self._write_numeric_array(parameter_id, np.array(arr, copy=True))
        self._sync_axes_after_shape(parameter_id)

    def get_value(self, parameter_id: UUID) -> Any:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if rec.is_text:
            return rec.text_value
        if rec.values.ndim == 0:
            return float(rec.values.item())
        # MUST NOT expose mutable ndarray references that bypass guarded writes.
        return _readonly_array_copy(rec.values)

    # ---- shape + axis -----------------------------------------------------

    def reshape(self, parameter_id: UUID, shape: tuple[int, ...]) -> None:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if rec.is_text:
            raise ValueError("shape is not writable for text parameters")
        if any(int(x) <= 0 for x in shape):
            raise ValueError("shape dimensions must be positive integers")
        new_shape = tuple(int(x) for x in shape)
        old = self._read_numeric_array(parameter_id)
        if old.ndim == 0:
            old = old.reshape(())
        if old.shape == new_shape:
            return
        out = np.zeros(new_shape, dtype=np.float64)
        common = tuple(slice(0, min(a, b)) for a, b in zip(old.shape, new_shape))
        if common:
            out[common] = old[common]
        self._write_numeric_array(parameter_id, out)
        self._sync_axes_after_shape(parameter_id)

    def set_axis_dim(self, parameter_id: UUID, axis_idx: int, dim: int) -> None:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if rec.is_text:
            raise ValueError("axis dimensions are not writable for text parameters")
        if axis_idx < 0:
            raise ValueError("axis index must be >= 0")
        if int(dim) <= 0:
            raise ValueError("axis dimension must be a positive integer")
        old = self._read_numeric_array(parameter_id)
        shape: list[int] = list(old.shape if old.ndim > 0 else ())
        if axis_idx >= len(shape):
            shape.extend([1] * (axis_idx + 1 - len(shape)))
        shape[axis_idx] = int(dim)
        self.reshape(parameter_id, tuple(shape))

    def set_axis_values(self, parameter_id: UUID, axis_idx: int, values: Any) -> None:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if rec.is_text:
            raise ValueError("axis values are not writable for text parameters")
        if axis_idx < 0:
            raise ValueError("axis index must be >= 0")
        if axis_idx >= rec.values.ndim:
            raise ValueError("axis index out of bounds for current shape")
        a = np.asarray(values, dtype=np.float64).reshape(-1)
        values_now = self._read_numeric_array(parameter_id)
        need = values_now.shape[axis_idx]
        if int(a.shape[0]) != int(need):
            raise ValueError("axis length must match parameter shape on this axis")
        if a.shape[0] >= 2 and not bool(np.all(np.diff(a) > 0.0)):
            raise ValueError("axis values must be strictly monotonic increasing")
        self._write_axis_values(parameter_id, axis_idx, np.array(a, copy=True))

    def get_axis_values(self, parameter_id: UUID, axis_idx: int) -> np.ndarray:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if rec.is_text:
            raise ValueError("text parameters do not have axes")
        if axis_idx < 0 or axis_idx >= rec.values.ndim:
            raise ValueError("axis index out of bounds")
        a = self._read_axis_values(parameter_id, axis_idx)
        if a is None:
            a = np.arange(rec.values.shape[axis_idx], dtype=np.float64)
            self._write_axis_values(parameter_id, axis_idx, a)
        return _readonly_array_copy(a)

    def _sync_axes_after_shape(self, parameter_id: UUID) -> None:
        values = self._read_numeric_array(parameter_id)
        axes = self._read_axes(parameter_id)
        ndim = values.ndim
        for idx in list(axes.keys()):
            if idx >= ndim:
                self._con.execute(
                    "DELETE FROM parameter_axes WHERE parameter_id = ? AND axis_index = ?",
                    [str(parameter_id), int(idx)],
                )
        for idx in range(ndim):
            target = int(values.shape[idx])
            old = axes.get(idx)
            if old is None:
                self._write_axis_values(parameter_id, idx, np.arange(target, dtype=np.float64))
                continue
            out = np.arange(target, dtype=np.float64)
            n = min(target, int(old.shape[0]))
            if n > 0:
                out[:n] = old[:n]
            # enforce strict monotonicity deterministically
            if out.shape[0] >= 2 and not bool(np.all(np.diff(out) > 0.0)):
                out = np.arange(target, dtype=np.float64)
            self._write_axis_values(parameter_id, idx, out)

    # ---- ndarray/blob helpers -------------------------------------------

    @staticmethod
    def _to_npy_blob(a: np.ndarray) -> bytes:
        bio = BytesIO()
        np.save(bio, np.asarray(a), allow_pickle=False)
        return bio.getvalue()

    @staticmethod
    def _from_npy_blob(blob: bytes) -> np.ndarray:
        bio = BytesIO(blob)
        arr = np.load(bio, allow_pickle=False)
        return np.asarray(arr)

    def _write_numeric_array(self, parameter_id: UUID, arr: np.ndarray) -> None:
        a = np.asarray(arr, dtype=np.float64)
        self._con.execute(
            """
            INSERT OR REPLACE INTO parameter_values(parameter_id, shape_json, values_npy)
            VALUES (?, ?, ?)
            """,
            [str(parameter_id), json.dumps(list(a.shape)), self._to_npy_blob(a)],
        )

    def _read_numeric_array(self, parameter_id: UUID) -> np.ndarray:
        row = self._con.execute(
            "SELECT values_npy FROM parameter_values WHERE parameter_id = ?",
            [str(parameter_id)],
        ).fetchone()
        if row is None:
            return np.zeros((), dtype=np.float64)
        return self._from_npy_blob(row[0])

    def _write_axis_values(self, parameter_id: UUID, axis_idx: int, arr: np.ndarray) -> None:
        a = np.asarray(arr, dtype=np.float64).reshape(-1)
        self._con.execute(
            """
            INSERT OR REPLACE INTO parameter_axes(parameter_id, axis_index, values_npy)
            VALUES (?, ?, ?)
            """,
            [str(parameter_id), int(axis_idx), self._to_npy_blob(a)],
        )

    def _read_axis_values(self, parameter_id: UUID, axis_idx: int) -> np.ndarray | None:
        row = self._con.execute(
            "SELECT values_npy FROM parameter_axes WHERE parameter_id = ? AND axis_index = ?",
            [str(parameter_id), int(axis_idx)],
        ).fetchone()
        if row is None:
            return None
        return self._from_npy_blob(row[0]).reshape(-1)

    def _read_axes(self, parameter_id: UUID) -> dict[int, np.ndarray]:
        rows = self._con.execute(
            "SELECT axis_index, values_npy FROM parameter_axes WHERE parameter_id = ?",
            [str(parameter_id)],
        ).fetchall()
        out: dict[int, np.ndarray] = {}
        for idx, blob in rows:
            out[int(idx)] = self._from_npy_blob(blob).reshape(-1)
        return out

    def get_dataset_name(self, data_set_id: UUID) -> str | None:
        row = self._con.execute("SELECT name FROM data_sets WHERE id = ?", [str(data_set_id)]).fetchone()
        if row is None:
            return None
        return str(row[0])

