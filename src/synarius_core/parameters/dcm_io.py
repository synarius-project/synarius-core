"""Minimal DCM (KONSERVIERUNG_FORMAT 2.0) import/export for ParaWiz and tooling.

Parses and serializes the numeric subset used by the test fixtures:
``FESTWERT``, ``FESTWERTEBLOCK``, ``KENNLINIE``, ``KENNFELD``, ``STUETZSTELLENVERTEILUNG``.
Additionally maps common metadata fields:
``LANGNAME``, ``EINHEIT``, ``VAR``, ``FUNKTION``, ``LANGNAME_X``, ``LANGNAME_Y``,
``EINHEIT_X``, ``EINHEIT_Y``.

Export omits text (ASCII) parameters as ``*`` comment lines so the file stays parseable.

Performance: lines without ``"`` use whitespace tokenization; quoted strings still use :mod:`shlex`.
Numeric rows use vectorized :class:`numpy.ndarray` parsing where possible; KENNFELD matrices use
``numpy.asarray(rows).T`` instead of nested Python loops.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import shlex
from typing import Any

import numpy as np

from .repository import CalParamImportPrepared, ParameterRecord


@dataclass(slots=True)
class DcmImportSpec:
    name: str
    category: str
    values: np.ndarray
    axes: dict[int, np.ndarray] = field(default_factory=dict)
    display_name: str = ""
    unit: str = ""
    source_identifier: str = ""
    axis_names: dict[int, str] = field(default_factory=dict)
    axis_units: dict[int, str] = field(default_factory=dict)


def _iter_body_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        out.append(line)
    return out


def _floats_after_keyword(tokens: list[str], kw: str) -> np.ndarray:
    if not tokens or tokens[0].upper() != kw.upper():
        raise ValueError(f"expected {kw}, got {tokens!r}")
    if len(tokens) < 2:
        return np.zeros((0,), dtype=np.float64)
    return np.asarray(tokens[1:], dtype=np.float64)


def _tokens(line: str) -> list[str]:
    """Split a DCM line; fast whitespace split when no ``\"`` (quoted strings need :mod:`shlex`)."""
    s = line.strip()
    if not s:
        return []
    if '"' not in s:
        return s.split()
    return shlex.split(s, posix=True)


def _str_after_keyword(tokens: list[str], kw: str, *, context: str) -> str:
    if not tokens or tokens[0].upper() != kw.upper():
        raise ValueError(f"expected {kw}, got {tokens!r}")
    if len(tokens) < 2:
        raise ValueError(f"{kw} needs a value in {context!r}")
    return " ".join(tokens[1:])


def _append_source_identifier(existing: str, key: str, value: str) -> str:
    part = f"{key}={value}"
    if not existing:
        return part
    return f"{existing};{part}"


def parse_dcm_specs(
    text: str,
    *,
    cooperative_hook: Callable[[], None] | None = None,
    cooperative_every: int = 400,
) -> list[DcmImportSpec]:
    lines = _iter_body_lines(text)
    i = 0
    specs: list[DcmImportSpec] = []
    _parse_tick = 0
    while i < len(lines):
        parts = _tokens(lines[i])
        if not parts:
            i += 1
            continue
        _parse_tick += 1
        if cooperative_hook is not None and cooperative_every > 0 and _parse_tick % cooperative_every == 0:
            cooperative_hook()
        kw = parts[0].upper()
        if kw == "KONSERVIERUNG_FORMAT":
            i += 1
            continue
        if kw == "END":
            i += 1
            continue

        if kw == "FESTWERT":
            if len(parts) < 2:
                raise ValueError("FESTWERT requires a name")
            name = parts[1]
            i += 1
            wval: float | None = None
            display_name = ""
            unit = ""
            source_identifier = ""
            while i < len(lines):
                tp = _tokens(lines[i])
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "WERT":
                    fv = _floats_after_keyword(tp, "WERT")
                    if fv.size != 1:
                        raise ValueError(f"WERT needs a value in {name!r}")
                    wval = float(fv[0])
                elif tp and tp[0].upper() == "LANGNAME":
                    display_name = _str_after_keyword(tp, "LANGNAME", context=name)
                elif tp and tp[0].upper() == "EINHEIT":
                    unit = _str_after_keyword(tp, "EINHEIT", context=name)
                elif tp and tp[0].upper() == "VAR":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "VAR",
                        _str_after_keyword(tp, "VAR", context=name),
                    )
                elif tp and tp[0].upper() == "FUNKTION":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "FUNKTION",
                        _str_after_keyword(tp, "FUNKTION", context=name),
                    )
                i += 1
            if wval is None:
                raise ValueError(f"FESTWERT {name!r} missing WERT")
            specs.append(
                DcmImportSpec(
                    name,
                    "VALUE",
                    np.array(wval, dtype=np.float64),
                    display_name=display_name,
                    unit=unit,
                    source_identifier=source_identifier,
                )
            )
            continue

        if kw == "FESTWERTEBLOCK":
            if len(parts) < 3:
                raise ValueError("FESTWERTEBLOCK requires <name> <count> or <count_x> @ <count_y>")
            name = parts[1]
            nx = int(parts[2])
            ny = 1
            if len(parts) >= 5 and parts[3] == "@":
                ny = int(parts[4])
            i += 1
            block_rows: list[list[float]] = []
            display_name = ""
            unit = ""
            source_identifier = ""
            while i < len(lines):
                tp = _tokens(lines[i])
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "WERT":
                    bv = _floats_after_keyword(tp, "WERT")
                    block_rows.append(bv.tolist())
                elif tp and tp[0].upper() == "LANGNAME":
                    display_name = _str_after_keyword(tp, "LANGNAME", context=name)
                elif tp and tp[0].upper() == "EINHEIT":
                    unit = _str_after_keyword(tp, "EINHEIT", context=name)
                elif tp and tp[0].upper() == "VAR":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "VAR",
                        _str_after_keyword(tp, "VAR", context=name),
                    )
                elif tp and tp[0].upper() == "FUNKTION":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "FUNKTION",
                        _str_after_keyword(tp, "FUNKTION", context=name),
                    )
                i += 1
            if ny <= 1:
                if len(block_rows) != 1:
                    raise ValueError(f"FESTWERTEBLOCK {name!r} expected exactly one WERT row, got {len(block_rows)}")
                block_vals = block_rows[0]
                if len(block_vals) != nx:
                    raise ValueError(f"FESTWERTEBLOCK {name!r} expected {nx} values, got {block_vals!r}")
                arr = np.asarray(block_vals, dtype=np.float64).reshape(nx)
                category = "ARRAY"
            else:
                if len(block_rows) != ny:
                    raise ValueError(
                        f"FESTWERTEBLOCK {name!r} expected {ny} WERT rows for matrix, got {len(block_rows)}"
                    )
                for row in block_rows:
                    if len(row) != nx:
                        raise ValueError(f"FESTWERTEBLOCK {name!r} matrix row length {len(row)} != {nx}")
                # ASAM DCM2 matrix form: "<nx> @ <ny>" and ny WERT-rows with nx values each.
                # Keep orientation aligned with KENNFELD: values[x, y] => shape (nx, ny).
                arr = np.asarray(block_rows, dtype=np.float64).reshape(ny, nx).T
                category = "MATRIX"
            specs.append(
                DcmImportSpec(
                    name,
                    category,
                    arr,
                    display_name=display_name,
                    unit=unit,
                    source_identifier=source_identifier,
                )
            )
            continue

        if kw == "KENNLINIE":
            if len(parts) < 3:
                raise ValueError("KENNLINIE requires <name> <count>")
            name = parts[1]
            nx = int(parts[2])
            i += 1
            stx: list[float] | None = None
            wrow: list[float] | None = None
            display_name = ""
            unit = ""
            source_identifier = ""
            axis_names: dict[int, str] = {}
            axis_units: dict[int, str] = {}
            while i < len(lines):
                tp = _tokens(lines[i])
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "ST/X":
                    stx = _floats_after_keyword(tp, "ST/X")
                elif tp and tp[0].upper() == "WERT":
                    wrow = _floats_after_keyword(tp, "WERT")
                elif tp and tp[0].upper() == "LANGNAME":
                    display_name = _str_after_keyword(tp, "LANGNAME", context=name)
                elif tp and tp[0].upper() == "EINHEIT":
                    unit = _str_after_keyword(tp, "EINHEIT", context=name)
                elif tp and tp[0].upper() == "LANGNAME_X":
                    axis_names[0] = _str_after_keyword(tp, "LANGNAME_X", context=name)
                elif tp and tp[0].upper() == "EINHEIT_X":
                    axis_units[0] = _str_after_keyword(tp, "EINHEIT_X", context=name)
                elif tp and tp[0].upper() == "VAR":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "VAR",
                        _str_after_keyword(tp, "VAR", context=name),
                    )
                elif tp and tp[0].upper() == "FUNKTION":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "FUNKTION",
                        _str_after_keyword(tp, "FUNKTION", context=name),
                    )
                i += 1
            if stx is None or wrow is None or int(stx.size) != nx or int(wrow.size) != nx:
                raise ValueError(f"KENNLINIE {name!r} invalid ST/X or WERT (expected {nx})")
            arr = np.asarray(wrow, dtype=np.float64).reshape(nx)
            ax = np.asarray(stx, dtype=np.float64).reshape(-1)
            specs.append(
                DcmImportSpec(
                    name,
                    "CURVE",
                    arr,
                    {0: ax},
                    display_name=display_name,
                    unit=unit,
                    source_identifier=source_identifier,
                    axis_names=axis_names,
                    axis_units=axis_units,
                )
            )
            continue

        if kw == "KENNFELD":
            if len(parts) < 4:
                raise ValueError("KENNFELD requires <name> <nx> <ny>")
            name = parts[1]
            nx = int(parts[2])
            ny = int(parts[3])
            i += 1
            stx: list[float] | None = None
            sty_order: list[float] = []
            rows: list[list[float]] = []
            display_name = ""
            unit = ""
            source_identifier = ""
            axis_names: dict[int, str] = {}
            axis_units: dict[int, str] = {}
            while i < len(lines):
                tp = _tokens(lines[i])
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "ST/X":
                    stx = _floats_after_keyword(tp, "ST/X")
                elif tp and tp[0].upper() == "ST/Y":
                    ys = _floats_after_keyword(tp, "ST/Y")
                    if ys.size != 1:
                        raise ValueError(f"KENNFELD {name!r} ST/Y must be one float per row")
                    sty_order.append(float(ys[0]))
                    i += 1
                    if i >= len(lines):
                        raise ValueError(f"KENNFELD {name!r} missing WERT after ST/Y")
                    wp = _tokens(lines[i])
                    wvals = _floats_after_keyword(wp, "WERT")
                    if int(wvals.size) != nx:
                        raise ValueError(f"KENNFELD {name!r} WERT row length {int(wvals.size)} != nx {nx}")
                    rows.append(wvals)
                elif tp and tp[0].upper() == "LANGNAME":
                    display_name = _str_after_keyword(tp, "LANGNAME", context=name)
                elif tp and tp[0].upper() == "EINHEIT":
                    unit = _str_after_keyword(tp, "EINHEIT", context=name)
                elif tp and tp[0].upper() == "LANGNAME_X":
                    axis_names[0] = _str_after_keyword(tp, "LANGNAME_X", context=name)
                elif tp and tp[0].upper() == "LANGNAME_Y":
                    axis_names[1] = _str_after_keyword(tp, "LANGNAME_Y", context=name)
                elif tp and tp[0].upper() == "EINHEIT_X":
                    axis_units[0] = _str_after_keyword(tp, "EINHEIT_X", context=name)
                elif tp and tp[0].upper() == "EINHEIT_Y":
                    axis_units[1] = _str_after_keyword(tp, "EINHEIT_Y", context=name)
                elif tp and tp[0].upper() == "VAR":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "VAR",
                        _str_after_keyword(tp, "VAR", context=name),
                    )
                elif tp and tp[0].upper() == "FUNKTION":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "FUNKTION",
                        _str_after_keyword(tp, "FUNKTION", context=name),
                    )
                i += 1
            if stx is None or int(stx.size) != nx or len(rows) != ny:
                raise ValueError(f"KENNFELD {name!r} incomplete (nx={nx} ny={ny})")
            # values[xi, yi]: first index axis0 (X / ST/X), second axis1 (Y / ST/Y)
            mat = np.asarray(rows, dtype=np.float64).T
            ax0 = np.asarray(stx, dtype=np.float64).reshape(-1)
            ax1 = np.asarray(sty_order, dtype=np.float64).reshape(-1)
            specs.append(
                DcmImportSpec(
                    name,
                    "MAP",
                    mat,
                    {0: ax0, 1: ax1},
                    display_name=display_name,
                    unit=unit,
                    source_identifier=source_identifier,
                    axis_names=axis_names,
                    axis_units=axis_units,
                )
            )
            continue

        if kw == "STUETZSTELLENVERTEILUNG":
            if len(parts) < 3:
                raise ValueError("STUETZSTELLENVERTEILUNG requires <name> <count>")
            name = parts[1]
            nx = int(parts[2])
            i += 1
            stx2: list[float] | None = None
            display_name = ""
            unit = ""
            source_identifier = ""
            axis_names: dict[int, str] = {}
            axis_units: dict[int, str] = {}
            while i < len(lines):
                tp = _tokens(lines[i])
                if tp and tp[0].upper() == "END":
                    i += 1
                    break
                if tp and tp[0].upper() == "ST/X":
                    stx2 = _floats_after_keyword(tp, "ST/X")
                elif tp and tp[0].upper() == "LANGNAME":
                    display_name = _str_after_keyword(tp, "LANGNAME", context=name)
                elif tp and tp[0].upper() == "EINHEIT":
                    unit = _str_after_keyword(tp, "EINHEIT", context=name)
                elif tp and tp[0].upper() == "LANGNAME_X":
                    axis_names[0] = _str_after_keyword(tp, "LANGNAME_X", context=name)
                elif tp and tp[0].upper() == "EINHEIT_X":
                    axis_units[0] = _str_after_keyword(tp, "EINHEIT_X", context=name)
                elif tp and tp[0].upper() == "VAR":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "VAR",
                        _str_after_keyword(tp, "VAR", context=name),
                    )
                elif tp and tp[0].upper() == "FUNKTION":
                    source_identifier = _append_source_identifier(
                        source_identifier,
                        "FUNKTION",
                        _str_after_keyword(tp, "FUNKTION", context=name),
                    )
                i += 1
            if stx2 is None or int(stx2.size) != nx:
                raise ValueError(f"STUETZSTELLENVERTEILUNG {name!r} invalid ST/X")
            arr = np.asarray(stx2, dtype=np.float64).reshape(nx)
            specs.append(
                DcmImportSpec(
                    name,
                    "NODE_ARRAY",
                    arr,
                    display_name=display_name,
                    unit=unit,
                    source_identifier=source_identifier,
                    axis_names=axis_names,
                    axis_units=axis_units,
                )
            )
            continue

        raise ValueError(f"Unsupported or unknown DCM keyword {kw!r} at line {lines[i]!r}")

    return specs


def import_dcm_for_dataset(
    controller: Any,
    data_set_ref: str,
    file_path: str,
    *,
    progress_hook: Callable[[int, int], None] | None = None,
    import_phase_hook: Callable[[str, int], None] | None = None,
    cooperative_hook: Callable[[], None] | None = None,
) -> int:
    """Create :class:`ComplexInstance` CAL_PARAM children for each parsed object; return count.

    ``import_phase_hook(phase, n)`` is called for coarse stages: ``"reading"``, ``"parsing"``,
    ``"write"`` (``n`` = number of specs to import), ``"virtuals"`` (``n`` = cal_param nodes
    finished installing model virtual attributes), ``"complete"`` (``n`` = imported count).

    ``progress_hook(done, umax)`` uses one combined scale ``umax = 3 * n`` (``n`` = number of specs):
    ``done`` runs ``1 … n`` while attaching, ``n+1 … 2n`` while bulk-writing DuckDB chunks, and
    ``2n … 3n`` while installing cal-param virtual attributes. GUIs may extend the bar maximum
    (e.g. for post-import table refresh) so the same widget runs once from 0 % to 100 %.
    GUI apps can call ``QApplication.processEvents()`` here so the window stays responsive.

    ``cooperative_hook`` is invoked periodically during parse, DuckDB bulk chunks, and model
    virtual-attribute installation so the UI thread can stay responsive (e.g. ``processEvents``).
    """
    path = Path(file_path)
    if import_phase_hook is not None:
        import_phase_hook("reading", 0)
    text = path.read_text(encoding="utf-8", errors="replace")
    if import_phase_hook is not None:
        import_phase_hook("parsing", 0)
    specs = parse_dcm_specs(text, cooperative_hook=cooperative_hook, cooperative_every=400)
    ds = controller._resolve_ref(data_set_ref.strip())
    from synarius_core.model.data_model import ComplexInstance

    if not isinstance(ds, ComplexInstance) or ds.id is None:
        raise ValueError("data_set_ref must resolve to an attached ComplexInstance with id")
    try:
        if str(ds.get("type")) != "MODEL.PARAMETER_DATA_SET":
            raise ValueError("data_set_ref must resolve to a MODEL.PARAMETER_DATA_SET node")
    except KeyError as exc:
        raise ValueError("data_set_ref must resolve to a MODEL.PARAMETER_DATA_SET node") from exc

    rt = controller.model.parameter_runtime()
    total = len(specs)
    umax = max(1, 3 * total)
    if import_phase_hook is not None:
        import_phase_hook("write", total)
    pairs: list[tuple[ComplexInstance, CalParamImportPrepared]] = []
    for spec in specs:
        node = ComplexInstance(name=spec.name)
        controller.model.attach(node, parent=ds, reserve_existing=False, remap_ids=False)
        ax_copy = {int(k): np.asarray(v, dtype=np.float64).copy() for k, v in spec.axes.items()}
        prep = rt.repo.prepare_cal_param_import_row(
            parameter_id=node.id,
            data_set_id=ds.id,
            name=spec.name,
            category=spec.category,
            display_name=spec.display_name,
            unit=spec.unit,
            source_identifier=spec.source_identifier,
            values=np.asarray(spec.values, dtype=np.float64),
            axes=ax_copy,
            axis_names={int(k): str(v) for k, v in spec.axis_names.items()},
            axis_units={int(k): str(v) for k, v in spec.axis_units.items()},
        )
        pairs.append((node, prep))
        n = len(pairs)
        if progress_hook is not None:
            progress_hook(n, umax)

    def _virtual_phase(done: int, _tot: int) -> None:
        if progress_hook is not None:
            progress_hook(2 * total + done, umax)
        if import_phase_hook is not None:
            import_phase_hook("virtuals", done)

    write_hook = None
    if progress_hook is not None:
        _base = total
        _um = umax
        _prog = progress_hook

        def write_hook(d: int, _t: int) -> None:
            _prog(_base + d, _um)

    rt.register_cal_param_nodes_bulk_from_import(
        pairs,
        cooperative_hook=cooperative_hook,
        write_progress_hook=write_hook,
        virtual_progress_hook=_virtual_phase if (progress_hook is not None or import_phase_hook is not None) else None,
        virtual_progress_every=80,
    )
    n = len(pairs)

    if import_phase_hook is not None:
        import_phase_hook("complete", n)
    return n


def _dcm_double_quoted(s: str) -> str:
    """DCM-style ``"…"`` string for LANGNAME fields (matches fixtures, avoids POSIX ``shlex`` single quotes)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dcm_short_atom(s: str) -> str:
    s = str(s).strip()
    if not s:
        return ""
    if any(c.isspace() for c in s) or '"' in s:
        return shlex.quote(s)
    return s


def _dcm_ident(name: str) -> str:
    if not name:
        raise ValueError("empty parameter name")
    if any(c.isspace() for c in name):
        return shlex.quote(name)
    return name


def _split_var_funk(source_identifier: str) -> tuple[str, str]:
    var = ""
    funk = ""
    for part in str(source_identifier).split(";"):
        part = part.strip()
        if part.startswith("VAR="):
            var = part[4:].strip()
        elif part.startswith("FUNKTION="):
            funk = part[9:].strip()
    return var, funk


def _fmt_dcm_float(x: float) -> str:
    v = float(np.float64(x))
    s = f"{v:.15g}"
    if "e" in s.lower() or "E" in s:
        return s
    if "." not in s and "inf" not in s.lower() and "nan" not in s.lower():
        return f"{s}.0"
    return s


def _lines_langname_einheit(rec: ParameterRecord, lines: list[str]) -> None:
    if rec.display_name.strip():
        lines.append(f" LANGNAME {_dcm_double_quoted(rec.display_name)}")
    u = rec.unit.strip()
    if u:
        lines.append(f" EINHEIT {_dcm_short_atom(u)}")


def _lines_var_funk(rec: ParameterRecord, lines: list[str]) -> None:
    v, f = _split_var_funk(rec.source_identifier)
    if v:
        lines.append(f" VAR {_dcm_short_atom(v)}")
    if f:
        lines.append(f" FUNKTION {_dcm_short_atom(f)}")


def format_parameter_record_dcm(rec: ParameterRecord) -> str:
    """Serialize one numeric :class:`ParameterRecord` to a DCM block (subset matching :func:`parse_dcm_specs`)."""
    if rec.is_text:
        return f"* Omitted non-DCM text parameter: {_dcm_ident(rec.name)}\n"

    cat = str(rec.category).upper()
    name = _dcm_ident(rec.name)
    vals = np.asarray(rec.values, dtype=np.float64)
    lines: list[str] = []

    if cat == "VALUE":
        if vals.ndim != 0:
            raise ValueError(f"VALUE parameter {rec.name!r} must be scalar")
        w = float(vals.item())
        lines.append(f"FESTWERT {name}")
        _lines_langname_einheit(rec, lines)
        _lines_var_funk(rec, lines)
        lines.append(f" WERT {_fmt_dcm_float(w)}")
        lines.append("END")
        return "\n".join(lines) + "\n"

    if cat == "ARRAY":
        if vals.ndim != 1:
            raise ValueError(f"ARRAY parameter {rec.name!r} must be one-dimensional")
        nx = int(vals.shape[0])
        lines.append(f"FESTWERTEBLOCK {name} {nx}")
        _lines_langname_einheit(rec, lines)
        _lines_var_funk(rec, lines)
        row = " ".join(_fmt_dcm_float(float(x)) for x in vals.reshape(-1))
        lines.append(f" WERT {row}")
        lines.append("END")
        return "\n".join(lines) + "\n"

    if cat == "MATRIX":
        if vals.ndim != 2:
            raise ValueError(f"MATRIX parameter {rec.name!r} must be two-dimensional")
        nx, ny = int(vals.shape[0]), int(vals.shape[1])
        lines.append(f"FESTWERTEBLOCK {name} {nx} @ {ny}")
        _lines_langname_einheit(rec, lines)
        _lines_var_funk(rec, lines)
        for yi in range(ny):
            row = vals[:, yi]
            lines.append(" WERT " + " ".join(_fmt_dcm_float(float(x)) for x in row))
        lines.append("END")
        return "\n".join(lines) + "\n"

    if cat == "CURVE":
        if vals.ndim != 1:
            raise ValueError(f"CURVE parameter {rec.name!r} must be one-dimensional")
        ax0 = rec.axes.get(0)
        if ax0 is None:
            raise ValueError(f"CURVE parameter {rec.name!r} missing axis 0")
        stx = np.asarray(ax0, dtype=np.float64).reshape(-1)
        nx = int(vals.shape[0])
        if int(stx.size) != nx:
            raise ValueError(f"CURVE parameter {rec.name!r} axis length mismatch")
        lines.append(f"KENNLINIE {name} {nx}")
        _lines_langname_einheit(rec, lines)
        nm0 = rec.axis_names.get(0, "").strip()
        un0 = rec.axis_units.get(0, "").strip()
        if nm0:
            lines.append(f" LANGNAME_X {_dcm_double_quoted(nm0)}")
        if un0:
            lines.append(f" EINHEIT_X {_dcm_short_atom(un0)}")
        _lines_var_funk(rec, lines)
        lines.append(" ST/X " + " ".join(_fmt_dcm_float(float(x)) for x in stx))
        lines.append(" WERT " + " ".join(_fmt_dcm_float(float(x)) for x in vals.reshape(-1)))
        lines.append("END")
        return "\n".join(lines) + "\n"

    if cat == "MAP":
        if vals.ndim != 2:
            raise ValueError(f"MAP parameter {rec.name!r} must be two-dimensional")
        ax0 = rec.axes.get(0)
        ax1 = rec.axes.get(1)
        if ax0 is None or ax1 is None:
            raise ValueError(f"MAP parameter {rec.name!r} missing axes 0/1")
        stx = np.asarray(ax0, dtype=np.float64).reshape(-1)
        sty = np.asarray(ax1, dtype=np.float64).reshape(-1)
        nx, ny = int(vals.shape[0]), int(vals.shape[1])
        if int(stx.size) != nx or int(sty.size) != ny:
            raise ValueError(f"MAP parameter {rec.name!r} axis length mismatch")
        lines.append(f"KENNFELD {name} {nx} {ny}")
        _lines_langname_einheit(rec, lines)
        nm0 = rec.axis_names.get(0, "").strip()
        un0 = rec.axis_units.get(0, "").strip()
        nm1 = rec.axis_names.get(1, "").strip()
        un1 = rec.axis_units.get(1, "").strip()
        if nm0:
            lines.append(f" LANGNAME_X {_dcm_double_quoted(nm0)}")
        if un0:
            lines.append(f" EINHEIT_X {_dcm_short_atom(un0)}")
        if nm1:
            lines.append(f" LANGNAME_Y {_dcm_double_quoted(nm1)}")
        if un1:
            lines.append(f" EINHEIT_Y {_dcm_short_atom(un1)}")
        _lines_var_funk(rec, lines)
        lines.append(" ST/X " + " ".join(_fmt_dcm_float(float(x)) for x in stx))
        for yi in range(ny):
            lines.append(f" ST/Y {_fmt_dcm_float(float(sty[yi]))}")
            row = vals[:, yi]
            lines.append(" WERT " + " ".join(_fmt_dcm_float(float(x)) for x in row))
        lines.append("END")
        return "\n".join(lines) + "\n"

    if cat == "NODE_ARRAY":
        if vals.ndim != 1:
            raise ValueError(f"NODE_ARRAY parameter {rec.name!r} must be one-dimensional")
        nx = int(vals.shape[0])
        lines.append(f"STUETZSTELLENVERTEILUNG {name} {nx}")
        _lines_langname_einheit(rec, lines)
        nm0 = rec.axis_names.get(0, "").strip()
        un0 = rec.axis_units.get(0, "").strip()
        if nm0:
            lines.append(f" LANGNAME_X {_dcm_double_quoted(nm0)}")
        if un0:
            lines.append(f" EINHEIT_X {_dcm_short_atom(un0)}")
        _lines_var_funk(rec, lines)
        lines.append(" ST/X " + " ".join(_fmt_dcm_float(float(x)) for x in vals.reshape(-1)))
        lines.append("END")
        return "\n".join(lines) + "\n"

    raise ValueError(f"Unsupported category for DCM export: {rec.category!r} ({rec.name!r})")


def write_dcm_records_to_path(path: Path | str, records: list[ParameterRecord]) -> tuple[int, int]:
    """Write UTF-8 DCM text. Returns ``(numeric_blocks, skipped_text_count)``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body: list[str] = []
    n_num = 0
    n_skip = 0
    for rec in records:
        block = format_parameter_record_dcm(rec)
        if block.lstrip().startswith("*"):
            body.append(block.rstrip("\n"))
            n_skip += 1
        else:
            body.append(block.rstrip("\n"))
            n_num += 1
    # Blank line between Kenngrößen blocks; header ends with a blank line before the first block.
    head_txt = "* Written by Synarius\nKONSERVIERUNG_FORMAT 2.0\n\n"
    if not body:
        text = head_txt
    else:
        text = head_txt + "\n\n".join(body).rstrip() + "\n"
    p.write_text(text, encoding="utf-8", newline="\n")
    return n_num, n_skip


def write_dcm_for_active_dataset(controller: Any, file_path: str | Path) -> tuple[int, int]:
    """Export all numeric parameters from the **active** ``MODEL.PARAMETER_DATA_SET`` to a DCM file.

    Text (ASCII) parameters are omitted (comment lines in the output). Returns ``(numeric_blocks, skipped_text)``.
    """
    from synarius_core.model.data_model import ComplexInstance

    rt = controller.model.parameter_runtime()
    ds = rt.active_dataset()
    if ds is None or not isinstance(ds, ComplexInstance) or ds.id is None:
        raise ValueError("No active parameter data set; set the active dataset (parameters runtime).")
    # ``ComplexInstance.get`` raises KeyError when ``type`` is missing (unlike ``dict.get``).
    # ``ParameterRuntime._is_data_set_node`` mirrors ``_node_type`` (try/except). Fall back to
    # DuckDB registration so legacy or partially materialized data set nodes still export.
    repo = rt.repo
    is_node = rt._is_data_set_node(ds)
    duck_name = repo.get_dataset_name(ds.id)
    if not is_node and duck_name is None:
        raise ValueError("Active context must be a MODEL.PARAMETER_DATA_SET node.")

    pids = repo.list_parameter_ids_for_data_set(ds.id)
    if not pids:
        return write_dcm_records_to_path(file_path, [])

    recs_map = repo.get_records_for_ids(pids)
    ordered = [recs_map[pid] for pid in pids]
    return write_dcm_records_to_path(file_path, ordered)
