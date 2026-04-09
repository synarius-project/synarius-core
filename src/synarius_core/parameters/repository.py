from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from uuid import UUID, uuid4

import numpy as np


_TEXT_CATEGORIES = {"ASCII"}


def _rounded_float_ndarray_bytes(a: np.ndarray) -> bytes:
    """Gleiche Rundungslogik wie ParaWiz/MainWindow für stabilen Wertevergleich (nicht Roh-Blob-Bytes)."""
    x = np.asarray(a, dtype=np.float64).reshape(-1)
    if x.size == 0:
        return b""
    y = np.round(x, 10)
    y = np.where(np.abs(y) < 1e-15, 0.0, y)
    return y.tobytes()


def _parameter_va_fingerprint_semantic(
    *,
    category: str,
    text_value: str,
    values_arr: np.ndarray,
    axes_by_idx: dict[int, np.ndarray],
) -> tuple:
    """Wert-/Achsen-Fingerprint wie :meth:`ParameterRecord`-basierte ParaWiz-Logik (ohne vollen Record)."""
    cat_u = str(category).upper()
    if cat_u in _TEXT_CATEGORIES:
        return ("t", cat_u, str(text_value))
    v = np.asarray(values_arr, dtype=np.float64)
    ax_parts: list[tuple[int, bytes]] = []
    for idx in sorted(axes_by_idx.keys()):
        ax_parts.append((int(idx), _rounded_float_ndarray_bytes(axes_by_idx[idx])))
    return ("n", v.shape, _rounded_float_ndarray_bytes(v), tuple(ax_parts))


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
    axis_names: dict[int, str] = field(default_factory=dict)
    axis_units: dict[int, str] = field(default_factory=dict)

    @property
    def is_text(self) -> bool:
        return str(self.category).upper() in _TEXT_CATEGORIES


@dataclass(frozen=True, slots=True)
class ParameterTableSummary:
    """Lightweight row for parameter lists (no full value/axis blob reads except 0-D scalars)."""

    name: str
    category: str
    value_label: str


@dataclass(frozen=True, slots=True)
class ParameterCompareFingerprints:
    """Cross-dataset styling: semantischer VA-Fingerprint (gerundete Werte/Achsen), Meta ohne Provenance-Noise."""

    va_fingerprint: tuple
    category: str
    is_text: bool
    numeric_format: str
    value_semantics: str
    source_identifier: str


@dataclass(slots=True)
class CalParamImportPrepared:
    """Validated numeric cal-param row ready for DuckDB (single or bulk insert)."""

    parameter_id: UUID
    data_set_id: UUID
    name: str
    category: str
    display_name: str
    unit: str
    source_identifier: str
    values: np.ndarray
    resolved_axes: dict[int, np.ndarray]
    axis_names: dict[int, str]
    axis_units: dict[int, str]


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
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS parameter_axis_meta (
                parameter_id TEXT NOT NULL,
                axis_index INTEGER NOT NULL,
                axis_name TEXT NOT NULL,
                axis_unit TEXT NOT NULL,
                PRIMARY KEY(parameter_id, axis_index)
            );
            """
        )
        self._con.execute(
            "CREATE INDEX IF NOT EXISTS idx_parameters_all_data_set_id ON parameters_all(data_set_id);"
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group DuckDB writes; rolls back on exception."""
        self._con.execute("BEGIN TRANSACTION")
        try:
            yield
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        else:
            self._con.execute("COMMIT")

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

    def delete_parameters_for_data_set(
        self, data_set_id: UUID, *, remove_data_set_row: bool = False
    ) -> int:
        """Remove DuckDB parameter rows for ``data_set_id``. Optionally drop the ``data_sets`` row.

        Returns the number of parameters removed.
        """
        ds_s = str(data_set_id)
        cnt_row = self._con.execute(
            "SELECT COUNT(*) FROM parameters_all WHERE data_set_id = ?",
            [ds_s],
        ).fetchone()
        n = int(cnt_row[0]) if cnt_row is not None else 0
        sub = "(SELECT parameter_id FROM parameters_all WHERE data_set_id = ?)"
        with self.transaction():
            if n > 0:
                self._con.execute(f"DELETE FROM parameter_axis_meta WHERE parameter_id IN {sub}", [ds_s])
                self._con.execute(f"DELETE FROM parameter_axes WHERE parameter_id IN {sub}", [ds_s])
                self._con.execute(f"DELETE FROM parameter_values WHERE parameter_id IN {sub}", [ds_s])
                self._con.execute("DELETE FROM parameters_all WHERE data_set_id = ?", [ds_s])
            if remove_data_set_row:
                self._con.execute("DELETE FROM data_sets WHERE id = ?", [ds_s])
        return n

    def count_parameters_for_data_set(self, data_set_id: UUID) -> int:
        """Number of rows in ``parameters_all`` for ``data_set_id``."""
        row = self._con.execute(
            "SELECT COUNT(*) FROM parameters_all WHERE data_set_id = ?",
            [str(data_set_id)],
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def list_parameter_ids_for_data_set(self, data_set_id: UUID) -> list[UUID]:
        """All ``parameter_id`` values in ``data_set_id``, ordered by ``name`` (case-insensitive)."""
        rows = self._con.execute(
            "SELECT parameter_id FROM parameters_all WHERE data_set_id = ? ORDER BY LOWER(name)",
            [str(data_set_id)],
        ).fetchall()
        return [UUID(str(r[0])) for r in rows]

    def delete_data_set_and_parameters(self, data_set_id: UUID) -> int:
        """Remove all parameters belonging to ``data_set_id`` and the ``data_sets`` row. Returns parameter count."""
        return self.delete_parameters_for_data_set(data_set_id, remove_data_set_row=True)

    def swap_parameter_data_set_ids(self, a_id: UUID, b_id: UUID) -> None:
        """Exchange ``data_set_id`` for all rows in ``parameters_all`` between the two sets.

        Uses a temporary UUID not present in ``data_sets``; DuckDB schema has no FK constraint.
        """
        sa, sb = str(a_id), str(b_id)
        if sa == sb:
            return
        temp = str(uuid4())
        with self.transaction():
            self._con.execute(
                "UPDATE parameters_all SET data_set_id = ? WHERE data_set_id = ?",
                [temp, sa],
            )
            self._con.execute(
                "UPDATE parameters_all SET data_set_id = ? WHERE data_set_id = ?",
                [sa, sb],
            )
            self._con.execute(
                "UPDATE parameters_all SET data_set_id = ? WHERE data_set_id = ?",
                [sb, temp],
            )

    def reconcile_swapped_data_set_rows(
        self,
        id_a: UUID,
        row_a: tuple[str, str, str, str],
        id_b: UUID,
        row_b: tuple[str, str, str, str],
    ) -> None:
        """Schreibt zwei ``data_sets``-Zeilen auf getauschte Modell-Metadaten ohne UNIQUE-Konflikt auf ``name``.

        ``row_*`` = ``(name, source_format, source_path, source_hash)`` pro Satz-ID.
        Zwei UPDATEs mit finalem ``name`` würden kurz zwei gleiche Namen erzeugen; daher zuerst
        eindeutige Platzhalter-Namen, dann Zielwerte (in einer Transaktion).
        """
        sa, sb = str(id_a), str(id_b)
        if sa == sb:
            return
        na, sfa, spa, sha = (str(x) for x in row_a)
        nb, sfb, spb, shb = (str(x) for x in row_b)
        it_a = _now_iso() if (spa or sha) else ""
        it_b = _now_iso() if (spb or shb) else ""
        t1 = f"__synarius_swap_{uuid4().hex}__"
        t2 = f"__synarius_swap_{uuid4().hex}__"
        with self.transaction():
            self._con.execute("UPDATE data_sets SET name = ? WHERE id = ?", [t1, sa])
            self._con.execute("UPDATE data_sets SET name = ? WHERE id = ?", [t2, sb])
            self._con.execute(
                """
                UPDATE data_sets
                SET name = ?, source_format = ?, source_path = ?, source_hash = ?, import_time = ?
                WHERE id = ?
                """,
                [na, sfa, spa, sha, it_a, sa],
            )
            self._con.execute(
                """
                UPDATE data_sets
                SET name = ?, source_format = ?, source_path = ?, source_hash = ?, import_time = ?
                WHERE id = ?
                """,
                [nb, sfb, spb, shb, it_b, sb],
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
        self._con.execute("DELETE FROM parameter_axis_meta WHERE parameter_id = ?", [str(parameter_id)])

    def get_parameter_table_summary(self, parameter_id: UUID) -> ParameterTableSummary:
        """Name, category, and table label without loading large ``values_npy`` (only shape_json + scalar blob)."""
        row = self._con.execute(
            """
            SELECT p.name, p.category, p.text_value, pv.shape_json
            FROM parameters_all p
            JOIN parameter_values pv ON p.parameter_id = pv.parameter_id
            WHERE p.parameter_id = ?
            """,
            [str(parameter_id)],
        ).fetchone()
        if row is None:
            raise ValueError("unknown parameter_id")
        name = str(row[0])
        category = str(row[1])
        text_value = str(row[2])
        shape_json = str(row[3])
        cat_u = category.upper()
        if cat_u in _TEXT_CATEGORIES:
            return ParameterTableSummary(name=name, category=category, value_label=text_value)
        shape_tuple = tuple(int(x) for x in json.loads(shape_json))
        if len(shape_tuple) == 0:
            blob_row = self._con.execute(
                "SELECT values_npy FROM parameter_values WHERE parameter_id = ?",
                [str(parameter_id)],
            ).fetchone()
            if blob_row is None:
                return ParameterTableSummary(name=name, category=category, value_label="nan")
            v = self._from_npy_blob(blob_row[0])
            return ParameterTableSummary(name=name, category=category, value_label=repr(float(v.item())))
        if len(shape_tuple) == 1:
            n0 = int(shape_tuple[0])
            if n0 == 0:
                return ParameterTableSummary(name=name, category=category, value_label="0 Values")
            return ParameterTableSummary(
                name=name, category=category, value_label=f"{n0} Values"
            )
        label = f"{'X'.join(str(dim) for dim in shape_tuple)} Values"
        return ParameterTableSummary(name=name, category=category, value_label=label)

    def get_parameter_table_summaries_for_ids(self, parameter_ids: Sequence[UUID]) -> dict[UUID, ParameterTableSummary]:
        """Batch variant of :meth:`get_parameter_table_summary` (few round-trips; scalars batched)."""
        out: dict[UUID, ParameterTableSummary] = {}
        ids = list(dict.fromkeys(parameter_ids))
        if not ids:
            return out
        chunk_size = 1200
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start : start + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            rows = self._con.execute(
                f"""
                SELECT p.parameter_id, p.name, p.category, p.text_value, pv.shape_json
                FROM parameters_all p
                JOIN parameter_values pv ON p.parameter_id = pv.parameter_id
                WHERE p.parameter_id IN ({placeholders})
                """,
                [str(x) for x in chunk],
            ).fetchall()
            scalar_ids: list[UUID] = []
            scalar_meta: dict[UUID, tuple[str, str]] = {}
            for row in rows:
                pid = UUID(str(row[0]))
                name = str(row[1])
                category = str(row[2])
                text_value = str(row[3])
                shape_json = str(row[4])
                cat_u = category.upper()
                if cat_u in _TEXT_CATEGORIES:
                    out[pid] = ParameterTableSummary(name=name, category=category, value_label=text_value)
                    continue
                shape_tuple = tuple(int(x) for x in json.loads(shape_json))
                if len(shape_tuple) == 0:
                    scalar_ids.append(pid)
                    scalar_meta[pid] = (name, category)
                    continue
                if len(shape_tuple) == 1:
                    n0 = int(shape_tuple[0])
                    if n0 == 0:
                        out[pid] = ParameterTableSummary(name=name, category=category, value_label="0 Values")
                    else:
                        out[pid] = ParameterTableSummary(
                            name=name, category=category, value_label=f"{n0} Values"
                        )
                    continue
                label = f"{'X'.join(str(dim) for dim in shape_tuple)} Values"
                out[pid] = ParameterTableSummary(name=name, category=category, value_label=label)
            if not scalar_ids:
                continue
            ph2 = ",".join(["?"] * len(scalar_ids))
            blob_rows = self._con.execute(
                f"SELECT parameter_id, values_npy FROM parameter_values WHERE parameter_id IN ({ph2})",
                [str(x) for x in scalar_ids],
            ).fetchall()
            for bid, blob in blob_rows:
                pid = UUID(str(bid))
                meta = scalar_meta.get(pid)
                if meta is None:
                    continue
                name, category = meta
                if blob is None:
                    out[pid] = ParameterTableSummary(name=name, category=category, value_label="nan")
                else:
                    v = self._from_npy_blob(blob)
                    out[pid] = ParameterTableSummary(name=name, category=category, value_label=repr(float(v.item())))
        return out

    def prepare_cal_param_import_row(
        self,
        *,
        parameter_id: UUID,
        data_set_id: UUID,
        name: str,
        category: str,
        display_name: str = "",
        unit: str = "",
        source_identifier: str = "",
        values: np.ndarray,
        axes: dict[int, np.ndarray],
        axis_names: dict[int, str],
        axis_units: dict[int, str],
    ) -> CalParamImportPrepared:
        """Validate numeric import payload and resolve axes (shared by single-row and bulk import)."""
        cat = str(category).upper()
        if cat in _TEXT_CATEGORIES:
            raise ValueError("write_cal_param_import is for numeric parameters only")
        vals = np.asarray(values, dtype=np.float64)
        nd = int(vals.ndim)
        for k in axes:
            ki = int(k)
            if ki < 0 or ki >= nd:
                raise ValueError("axis index out of bounds for values shape")
        resolved_axes: dict[int, np.ndarray] = {}
        for idx in range(nd):
            if idx in axes:
                resolved_axes[idx] = np.asarray(axes[idx], dtype=np.float64).reshape(-1)
            else:
                resolved_axes[idx] = np.arange(int(vals.shape[idx]), dtype=np.float64)
        for axis_idx in range(nd):
            a = resolved_axes[axis_idx]
            need = int(vals.shape[axis_idx])
            if int(a.shape[0]) != need:
                raise ValueError("axis length must match parameter shape on this axis")
            if a.shape[0] >= 2 and not bool(np.all(np.diff(a) > 0.0)):
                raise ValueError("axis values must be strictly monotonic increasing")
        vals_copy = np.array(vals, copy=True)
        return CalParamImportPrepared(
            parameter_id=parameter_id,
            data_set_id=data_set_id,
            name=str(name),
            category=cat,
            display_name=str(display_name),
            unit=str(unit),
            source_identifier=str(source_identifier),
            values=vals_copy,
            resolved_axes={int(k): np.array(v, copy=True) for k, v in resolved_axes.items()},
            axis_names={int(k): str(v) for k, v in axis_names.items()},
            axis_units={int(k): str(v) for k, v in axis_units.items()},
        )

    def write_cal_param_import(
        self,
        *,
        parameter_id: UUID,
        data_set_id: UUID,
        name: str,
        category: str,
        display_name: str = "",
        unit: str = "",
        source_identifier: str = "",
        values: np.ndarray,
        axes: dict[int, np.ndarray],
        axis_names: dict[int, str],
        axis_units: dict[int, str],
    ) -> None:
        """Insert or replace one numeric cal parameter in few DB round-trips (no ``get_record`` per field)."""
        if not self._exists_data_set(data_set_id):
            raise ValueError("parameter registration requires existing data_set_id")
        prep = self.prepare_cal_param_import_row(
            parameter_id=parameter_id,
            data_set_id=data_set_id,
            name=name,
            category=category,
            display_name=display_name,
            unit=unit,
            source_identifier=source_identifier,
            values=values,
            axes=axes,
            axis_names=axis_names,
            axis_units=axis_units,
        )
        self._write_cal_param_import_prepared(prep)

    def _write_cal_param_import_prepared(self, prep: CalParamImportPrepared) -> None:
        pid = prep.parameter_id
        nd = int(prep.values.ndim)
        self._con.execute(
            """
            INSERT OR REPLACE INTO parameters_all(
                parameter_id, data_set_id, name, category, display_name, comment, unit,
                conversion_ref, source_identifier, numeric_format, value_semantics, text_value
            ) VALUES (?, ?, ?, ?, ?, '', ?, '', ?, 'decimal', 'physical', '')
            """,
            [
                str(pid),
                str(prep.data_set_id),
                prep.name,
                prep.category,
                prep.display_name,
                prep.unit,
                prep.source_identifier,
            ],
        )
        self._write_numeric_array(pid, prep.values)
        self._con.execute("DELETE FROM parameter_axes WHERE parameter_id = ?", [str(pid)])
        self._con.execute("DELETE FROM parameter_axis_meta WHERE parameter_id = ?", [str(pid)])
        for axis_idx in range(nd):
            self._write_axis_values(pid, axis_idx, prep.resolved_axes[axis_idx])
        for axis_idx in range(nd):
            an = str(prep.axis_names.get(axis_idx, "") or "")
            au = str(prep.axis_units.get(axis_idx, "") or "")
            self._write_axis_meta(pid, axis_idx, an, au)

    def copy_cal_param_payload(self, source_parameter_id: UUID, dest_parameter_id: UUID) -> None:
        """Copy values, axes and relevant metadata from one cal-param row to another (other data_set).

        Es werden **keine** gemeinsamen NumPy-Buffer zwischen Quelle und Ziel in der DB abgelegt:
        ``get_record`` lädt getrennte Arrays; hier werden explizit Kopien gebaut; ``write_cal_param_import``
        serialisiert mit eigenen Blobs pro ``parameter_id`` (INSERT OR REPLACE nur für die Ziel-UUID).
        """
        src = self.get_record(source_parameter_id)
        dst = self.get_record(dest_parameter_id)
        self._ensure_dataset_ownership(src)
        self._ensure_dataset_ownership(dst)
        if src.is_text:
            if not dst.is_text:
                raise ValueError("cannot copy text parameter onto numeric parameter")
            self._con.execute(
                """
                UPDATE parameters_all SET category = ?, display_name = ?, comment = ?, unit = ?,
                    conversion_ref = ?, source_identifier = ?, numeric_format = ?, value_semantics = ?,
                    text_value = ?
                WHERE parameter_id = ?
                """,
                [
                    src.category,
                    src.display_name,
                    src.comment,
                    src.unit,
                    dst.conversion_ref,
                    dst.source_identifier,
                    src.numeric_format,
                    src.value_semantics,
                    src.text_value,
                    str(dest_parameter_id),
                ],
            )
            return
        if dst.is_text:
            raise ValueError("cannot copy numeric parameter onto text parameter")
        axes = {int(k): np.array(v, dtype=np.float64, copy=True) for k, v in src.axes.items()}
        self.write_cal_param_import(
            parameter_id=dest_parameter_id,
            data_set_id=dst.data_set_id,
            name=dst.name,
            category=src.category,
            display_name=src.display_name,
            unit=src.unit,
            source_identifier=dst.source_identifier,
            values=np.array(src.values, dtype=np.float64, copy=True),
            axes=axes,
            axis_names={int(k): str(v) for k, v in src.axis_names.items()},
            axis_units={int(k): str(v) for k, v in src.axis_units.items()},
        )

    def _write_cal_param_import_prepared_replace_bulk_chunk(self, chunk: Sequence[CalParamImportPrepared]) -> None:
        """Replace numeric cal-params (existing ``parameter_id``): OR REPLACE meta/values, clear axes, reinsert axes."""
        if not chunk:
            return
        with self.transaction():
            pa_rows = [
                (
                    str(r.parameter_id),
                    str(r.data_set_id),
                    r.name,
                    r.category,
                    r.display_name,
                    r.unit,
                    r.source_identifier,
                )
                for r in chunk
            ]
            self._con.executemany(
                """
                INSERT OR REPLACE INTO parameters_all(
                    parameter_id, data_set_id, name, category, display_name, comment, unit,
                    conversion_ref, source_identifier, numeric_format, value_semantics, text_value
                ) VALUES (?, ?, ?, ?, ?, '', ?, '', ?, 'decimal', 'physical', '')
                """,
                pa_rows,
            )
            pv_rows = [
                (str(r.parameter_id), json.dumps(list(r.values.shape)), self._to_npy_blob(r.values))
                for r in chunk
            ]
            self._con.executemany(
                """
                INSERT OR REPLACE INTO parameter_values(parameter_id, shape_json, values_npy)
                VALUES (?, ?, ?)
                """,
                pv_rows,
            )
            pids = [str(r.parameter_id) for r in chunk]
            ph = ",".join(["?"] * len(pids))
            self._con.execute(f"DELETE FROM parameter_axes WHERE parameter_id IN ({ph})", pids)
            self._con.execute(f"DELETE FROM parameter_axis_meta WHERE parameter_id IN ({ph})", pids)
            axes_batch: list[tuple[str, int, bytes]] = []
            meta_batch: list[tuple[str, int, str, str]] = []
            for r in chunk:
                nd = int(r.values.ndim)
                for axis_idx in range(nd):
                    a = r.resolved_axes[axis_idx]
                    axes_batch.append((str(r.parameter_id), int(axis_idx), self._to_npy_blob(a)))
                    meta_batch.append(
                        (
                            str(r.parameter_id),
                            int(axis_idx),
                            str(r.axis_names.get(axis_idx, "") or ""),
                            str(r.axis_units.get(axis_idx, "") or ""),
                        )
                    )
            if axes_batch:
                self._con.executemany(
                    """
                    INSERT INTO parameter_axes(parameter_id, axis_index, values_npy)
                    VALUES (?, ?, ?)
                    """,
                    axes_batch,
                )
            if meta_batch:
                self._con.executemany(
                    """
                    INSERT INTO parameter_axis_meta(parameter_id, axis_index, axis_name, axis_unit)
                    VALUES (?, ?, ?, ?)
                    """,
                    meta_batch,
                )

    def copy_cal_param_payload_bulk(
        self,
        pairs: Sequence[tuple[UUID, UUID]],
        *,
        chunk_size: int = 300,
        cooperative_hook: Callable[[], None] | None = None,
        progress_hook: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        """Copy many cal-param payloads (same semantics as :meth:`copy_cal_param_payload`).

        Returns one string per input pair: ``""`` if that copy succeeded, otherwise an error message.
        Independent pairs behave like sequential single copies (no single all-or-nothing transaction).
        """
        n = len(pairs)
        if n == 0:
            return []
        src_ids = list(dict.fromkeys(sid for sid, _ in pairs))
        dst_ids = list(dict.fromkeys(did for _, did in pairs))
        src_map = self.get_records_for_ids(src_ids)
        dst_map = self.get_records_for_ids(dst_ids)

        errs: list[str] = [""] * n
        text_updates: list[
            tuple[
                str,
                str,
                str,
                str,
                str,
                str,
                str,
                str,
                str,
                str,
            ]
        ] = []
        text_indices: list[int] = []
        numeric_items: list[tuple[int, CalParamImportPrepared]] = []

        for i, (sid, did) in enumerate(pairs):
            src = src_map.get(sid)
            dst = dst_map.get(did)
            if src is None or dst is None:
                errs[i] = "unknown parameter_id"
                continue
            try:
                self._ensure_dataset_ownership(src)
                self._ensure_dataset_ownership(dst)
            except Exception as exc:
                errs[i] = str(exc)
                continue

            if src.is_text:
                if not dst.is_text:
                    errs[i] = "cannot copy text parameter onto numeric parameter"
                    continue
                text_updates.append(
                    (
                        src.category,
                        src.display_name,
                        src.comment,
                        src.unit,
                        dst.conversion_ref,
                        dst.source_identifier,
                        src.numeric_format,
                        src.value_semantics,
                        src.text_value,
                        str(did),
                    )
                )
                text_indices.append(i)
                continue
            if dst.is_text:
                errs[i] = "cannot copy numeric parameter onto text parameter"
                continue

            axes = {int(k): np.array(v, dtype=np.float64, copy=True) for k, v in src.axes.items()}
            try:
                prep = self.prepare_cal_param_import_row(
                    parameter_id=did,
                    data_set_id=dst.data_set_id,
                    name=dst.name,
                    category=src.category,
                    display_name=src.display_name,
                    unit=src.unit,
                    source_identifier=dst.source_identifier,
                    values=np.array(src.values, dtype=np.float64, copy=True),
                    axes=axes,
                    axis_names={int(k): str(v) for k, v in src.axis_names.items()},
                    axis_units={int(k): str(v) for k, v in src.axis_units.items()},
                )
            except Exception as exc:
                errs[i] = str(exc)
                continue
            numeric_items.append((i, prep))

        done = 0
        if text_updates:
            try:
                self._con.executemany(
                    """
                    UPDATE parameters_all SET category = ?, display_name = ?, comment = ?, unit = ?,
                        conversion_ref = ?, source_identifier = ?, numeric_format = ?, value_semantics = ?,
                        text_value = ?
                    WHERE parameter_id = ?
                    """,
                    text_updates,
                )
            except Exception:
                for ti in text_indices:
                    sid, did = pairs[ti]
                    try:
                        self.copy_cal_param_payload(sid, did)
                    except Exception as exc2:
                        errs[ti] = str(exc2)
            else:
                done += len(text_updates)
            if cooperative_hook is not None:
                cooperative_hook()
            if progress_hook is not None:
                progress_hook(done, n)

        if numeric_items:
            cs = max(1, int(chunk_size))
            for start in range(0, len(numeric_items), cs):
                chunk_items = numeric_items[start : start + cs]
                preps = [p for _, p in chunk_items]
                try:
                    self._write_cal_param_import_prepared_replace_bulk_chunk(preps)
                except Exception:
                    for pair_idx, prep in chunk_items:
                        try:
                            self._write_cal_param_import_prepared(prep)
                        except Exception as exc:
                            errs[pair_idx] = str(exc)
                    done += sum(1 for pair_idx, _ in chunk_items if not errs[pair_idx])
                else:
                    done += len(chunk_items)
                if cooperative_hook is not None:
                    cooperative_hook()
                if progress_hook is not None:
                    progress_hook(done, n)

        return errs

    def write_cal_params_import_bulk(
        self,
        rows: Sequence[CalParamImportPrepared],
        *,
        chunk_size: int = 1000,
        cooperative_hook: Callable[[], None] | None = None,
        write_progress_hook: Callable[[int, int], None] | None = None,
    ) -> None:
        """Bulk insert many new numeric cal parameters (few DuckDB round-trips per chunk).

        Preconditions: every ``parameter_id`` is new to the repository (no prior axis rows);
        all rows share the same ``data_set_id`` and the data set already exists.
        Skips per-row ``DELETE`` on axis tables (not needed for fresh UUIDs).
        Uses plain ``INSERT`` (not ``INSERT OR REPLACE``) for speed; duplicates raise DB errors.

        ``write_progress_hook(done, total)`` is called after each chunk (``done`` = rows written so far).
        ``cooperative_hook`` is invoked after each major ``executemany`` so UIs can ``processEvents``.
        """
        if not rows:
            return
        ds0 = rows[0].data_set_id
        if not self._exists_data_set(ds0):
            raise ValueError("parameter registration requires existing data_set_id")
        for r in rows:
            if r.data_set_id != ds0:
                raise ValueError("bulk cal-param import requires a single data_set_id")
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            pa_rows = [
                (
                    str(r.parameter_id),
                    str(r.data_set_id),
                    r.name,
                    r.category,
                    r.display_name,
                    r.unit,
                    r.source_identifier,
                )
                for r in chunk
            ]
            self._con.executemany(
                """
                INSERT INTO parameters_all(
                    parameter_id, data_set_id, name, category, display_name, comment, unit,
                    conversion_ref, source_identifier, numeric_format, value_semantics, text_value
                ) VALUES (?, ?, ?, ?, ?, '', ?, '', ?, 'decimal', 'physical', '')
                """,
                pa_rows,
            )
            if cooperative_hook is not None:
                cooperative_hook()
            pv_rows = [
                (str(r.parameter_id), json.dumps(list(r.values.shape)), self._to_npy_blob(r.values))
                for r in chunk
            ]
            self._con.executemany(
                """
                INSERT INTO parameter_values(parameter_id, shape_json, values_npy)
                VALUES (?, ?, ?)
                """,
                pv_rows,
            )
            if cooperative_hook is not None:
                cooperative_hook()
            axes_batch: list[tuple[str, int, bytes]] = []
            meta_batch: list[tuple[str, int, str, str]] = []
            for r in chunk:
                nd = int(r.values.ndim)
                for axis_idx in range(nd):
                    a = r.resolved_axes[axis_idx]
                    axes_batch.append((str(r.parameter_id), int(axis_idx), self._to_npy_blob(a)))
                    meta_batch.append(
                        (
                            str(r.parameter_id),
                            int(axis_idx),
                            str(r.axis_names.get(axis_idx, "") or ""),
                            str(r.axis_units.get(axis_idx, "") or ""),
                        )
                    )
            if axes_batch:
                self._con.executemany(
                    """
                    INSERT INTO parameter_axes(parameter_id, axis_index, values_npy)
                    VALUES (?, ?, ?)
                    """,
                    axes_batch,
                )
                if cooperative_hook is not None:
                    cooperative_hook()
            if meta_batch:
                self._con.executemany(
                    """
                    INSERT INTO parameter_axis_meta(parameter_id, axis_index, axis_name, axis_unit)
                    VALUES (?, ?, ?, ?)
                    """,
                    meta_batch,
                )
                if cooperative_hook is not None:
                    cooperative_hook()
            end_exclusive = start + len(chunk)
            if write_progress_hook is not None:
                write_progress_hook(end_exclusive, len(rows))
            if cooperative_hook is not None:
                cooperative_hook()

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
        axis_names, axis_units = self._read_axis_meta(parameter_id)
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
            axis_names=axis_names,
            axis_units=axis_units,
        )

    def get_compare_fingerprints_for_ids(
        self, parameter_ids: Sequence[UUID]
    ) -> dict[UUID, ParameterCompareFingerprints]:
        """Cross-dataset UI styling: semantische VA-Fingerprints (wie ParaWiz-Vergleichsdialog)."""
        uniq: list[UUID] = []
        seen: set[str] = set()
        for p in parameter_ids:
            s = str(p)
            if s not in seen:
                seen.add(s)
                uniq.append(p)
        if not uniq:
            return {}

        out: dict[UUID, ParameterCompareFingerprints] = {}
        chunk_size = 1200
        for start in range(0, len(uniq), chunk_size):
            chunk = uniq[start : start + chunk_size]
            ph = ",".join(["?"] * len(chunk))
            args = [str(p) for p in chunk]

            rows = self._con.execute(
                f"""
                SELECT p.parameter_id, p.category, p.text_value, p.source_identifier,
                       p.numeric_format, p.value_semantics, pv.values_npy
                FROM parameters_all p
                JOIN parameter_values pv ON p.parameter_id = pv.parameter_id
                WHERE p.parameter_id IN ({ph})
                """,
                args,
            ).fetchall()

            ax_rows = self._con.execute(
                f"""
                SELECT parameter_id, axis_index, values_npy
                FROM parameter_axes
                WHERE parameter_id IN ({ph})
                """,
                args,
            ).fetchall()
            ax_by_arr: dict[str, dict[int, np.ndarray]] = {}
            for pid_s, axis_idx, blob in ax_rows:
                arr = self._from_npy_blob(blob).reshape(-1)
                ax_by_arr.setdefault(str(pid_s), {})[int(axis_idx)] = arr

            for row in rows:
                pid = UUID(str(row[0]))
                category = str(row[1])
                text_value = str(row[2])
                source_identifier = str(row[3])
                numeric_format = str(row[4])
                value_semantics = str(row[5])
                blob_v = row[6]
                cat_u = category.upper()
                is_text = cat_u in _TEXT_CATEGORIES
                if is_text:
                    va_fp = ("t", cat_u, str(text_value))
                    out[pid] = ParameterCompareFingerprints(
                        va_fingerprint=va_fp,
                        category=category,
                        is_text=True,
                        numeric_format=numeric_format,
                        value_semantics=value_semantics,
                        source_identifier=source_identifier,
                    )
                else:
                    if blob_v is None or len(blob_v) == 0:
                        v = np.zeros((), dtype=np.float64)
                    else:
                        v = self._from_npy_blob(blob_v)
                    axes_dict = dict(ax_by_arr.get(str(pid), {}))
                    va_fp = _parameter_va_fingerprint_semantic(
                        category=category,
                        text_value=text_value,
                        values_arr=v,
                        axes_by_idx=axes_dict,
                    )
                    out[pid] = ParameterCompareFingerprints(
                        va_fingerprint=va_fp,
                        category=category,
                        is_text=False,
                        numeric_format=numeric_format,
                        value_semantics=value_semantics,
                        source_identifier=source_identifier,
                    )
        return out

    def get_records_for_ids(self, parameter_ids: Sequence[UUID]) -> dict[UUID, ParameterRecord]:
        """Load many parameters with batched queries (avoids N× round-trips for cross-dataset UI styling)."""
        uniq: list[UUID] = []
        seen: set[str] = set()
        for p in parameter_ids:
            s = str(p)
            if s not in seen:
                seen.add(s)
                uniq.append(p)
        if not uniq:
            return {}

        out: dict[UUID, ParameterRecord] = {}
        chunk_size = 1200
        for start in range(0, len(uniq), chunk_size):
            chunk = uniq[start : start + chunk_size]
            ph = ",".join(["?"] * len(chunk))
            args = [str(p) for p in chunk]

            pa_rows = self._con.execute(
                f"""
                SELECT parameter_id, data_set_id, name, category, display_name, comment, unit,
                       conversion_ref, source_identifier, numeric_format, value_semantics, text_value
                FROM parameters_all
                WHERE parameter_id IN ({ph})
                """,
                args,
            ).fetchall()

            pv_rows = self._con.execute(
                f"SELECT parameter_id, values_npy FROM parameter_values WHERE parameter_id IN ({ph})",
                args,
            ).fetchall()
            pv_map: dict[str, bytes] = {str(r[0]): r[1] for r in pv_rows}

            ax_rows = self._con.execute(
                f"SELECT parameter_id, axis_index, values_npy FROM parameter_axes WHERE parameter_id IN ({ph})",
                args,
            ).fetchall()
            axes_by_pid: dict[str, dict[int, np.ndarray]] = {}
            for pid_s, axis_idx, blob in ax_rows:
                pid_s = str(pid_s)
                axes_by_pid.setdefault(pid_s, {})[int(axis_idx)] = self._from_npy_blob(blob).reshape(-1)

            meta_rows = self._con.execute(
                f"""
                SELECT parameter_id, axis_index, axis_name, axis_unit
                FROM parameter_axis_meta
                WHERE parameter_id IN ({ph})
                """,
                args,
            ).fetchall()
            names_by_pid: dict[str, dict[int, str]] = {}
            units_by_pid: dict[str, dict[int, str]] = {}
            for pid_s, axis_idx, axis_name, axis_unit in meta_rows:
                pid_s = str(pid_s)
                names_by_pid.setdefault(pid_s, {})[int(axis_idx)] = str(axis_name)
                units_by_pid.setdefault(pid_s, {})[int(axis_idx)] = str(axis_unit)

            for row in pa_rows:
                pid = UUID(str(row[0]))
                pid_s = str(pid)
                blob_v = pv_map.get(pid_s)
                values = self._from_npy_blob(blob_v) if blob_v is not None else np.zeros((), dtype=np.float64)
                category = str(row[3]).upper()
                text_value = str(row[11])
                axes = dict(axes_by_pid.get(pid_s, {}))
                axis_names = dict(names_by_pid.get(pid_s, {}))
                axis_units = dict(units_by_pid.get(pid_s, {}))
                out[pid] = ParameterRecord(
                    parameter_id=pid,
                    data_set_id=UUID(str(row[1])),
                    name=str(row[2]),
                    category=category,
                    display_name=str(row[4]),
                    comment=str(row[5]),
                    unit=str(row[6]),
                    conversion_ref=str(row[7]),
                    source_identifier=str(row[8]),
                    numeric_format=str(row[9]),
                    value_semantics=str(row[10]),
                    values=values,
                    text_value=text_value,
                    axes=axes,
                    axis_names=axis_names,
                    axis_units=axis_units,
                )
        return out

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

    def set_axis_meta_field(self, parameter_id: UUID, axis_idx: int, field_name: str, value: Any) -> None:
        rec = self.get_record(parameter_id)
        self._ensure_dataset_ownership(rec)
        if rec.is_text:
            raise ValueError("axis metadata is not writable for text parameters")
        if axis_idx < 0 or axis_idx >= rec.values.ndim:
            raise ValueError("axis index out of bounds for current shape")
        if field_name not in {"axis_name", "axis_unit"}:
            raise ValueError(f"unsupported axis metadata field: {field_name}")
        cur_name = rec.axis_names.get(axis_idx, "")
        cur_unit = rec.axis_units.get(axis_idx, "")
        if field_name == "axis_name":
            cur_name = str(value)
        else:
            cur_unit = str(value)
        self._write_axis_meta(parameter_id, axis_idx, cur_name, cur_unit)

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
            self._con.execute("DELETE FROM parameter_axis_meta WHERE parameter_id = ?", [str(rec.parameter_id)])
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
                self._con.execute(
                    "DELETE FROM parameter_axis_meta WHERE parameter_id = ? AND axis_index = ?",
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
        # Materielle Kopie vor Serialisierung: kein Teilen von Views mit Aufrufer- oder DuckDB-Puffern.
        a = np.array(np.asarray(arr, dtype=np.float64), copy=True)
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
        a = np.array(np.asarray(arr, dtype=np.float64).reshape(-1), copy=True)
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

    def _write_axis_meta(self, parameter_id: UUID, axis_idx: int, axis_name: str, axis_unit: str) -> None:
        self._con.execute(
            """
            INSERT OR REPLACE INTO parameter_axis_meta(parameter_id, axis_index, axis_name, axis_unit)
            VALUES (?, ?, ?, ?)
            """,
            [str(parameter_id), int(axis_idx), str(axis_name), str(axis_unit)],
        )

    def _read_axis_meta(self, parameter_id: UUID) -> tuple[dict[int, str], dict[int, str]]:
        rows = self._con.execute(
            "SELECT axis_index, axis_name, axis_unit FROM parameter_axis_meta WHERE parameter_id = ?",
            [str(parameter_id)],
        ).fetchall()
        names: dict[int, str] = {}
        units: dict[int, str] = {}
        for idx, axis_name, axis_unit in rows:
            names[int(idx)] = str(axis_name)
            units[int(idx)] = str(axis_unit)
        return names, units

    def get_dataset_name(self, data_set_id: UUID) -> str | None:
        row = self._con.execute("SELECT name FROM data_sets WHERE id = ?", [str(data_set_id)]).fetchone()
        if row is None:
            return None
        return str(row[0])

    def get_dataset_init_file_stem(self, data_set_id: UUID) -> str:
        """Filename stem from ``source_path`` when the set was registered; else DuckDB ``name``."""
        row = self._con.execute(
            "SELECT name, source_path FROM data_sets WHERE id = ?",
            [str(data_set_id)],
        ).fetchone()
        if row is None:
            return str(data_set_id)
        name, sp = str(row[0]), str(row[1] or "").strip()
        if sp:
            stem = Path(sp.replace("\\", "/")).stem.strip()
            if stem:
                return stem
        return name

