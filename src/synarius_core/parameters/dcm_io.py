"""Minimal DCM (KONSERVIERUNG_FORMAT 2.0) import for ParaWiz and tooling.

Parses the numeric subset used by the test fixtures:
``FESTWERT``, ``FESTWERTEBLOCK``, ``KENNLINIE``, ``KENNFELD``, ``STUETZSTELLENVERTEILUNG``.
Additionally maps common metadata fields:
``LANGNAME``, ``EINHEIT``, ``VAR``, ``FUNKTION``, ``LANGNAME_X``, ``LANGNAME_Y``,
``EINHEIT_X``, ``EINHEIT_Y``.

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

from .repository import CalParamImportPrepared


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
                raise ValueError("FESTWERTEBLOCK requires <name> <count>")
            name = parts[1]
            n = int(parts[2])
            i += 1
            block_vals: list[float] | None = None
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
                    block_vals = bv.tolist()
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
            if block_vals is None or len(block_vals) != n:
                raise ValueError(f"FESTWERTEBLOCK {name!r} expected {n} values, got {block_vals!r}")
            arr = np.asarray(block_vals, dtype=np.float64).reshape(n)
            specs.append(
                DcmImportSpec(
                    name,
                    "VALUE",
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
                    "VALUE",
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

    parent = controller.current
    if not isinstance(parent, ComplexInstance):
        raise ValueError("controller cwd must be a ComplexInstance (e.g. parameters/data_sets)")

    rt = controller.model.parameter_runtime()
    total = len(specs)
    umax = max(1, 3 * total)
    if import_phase_hook is not None:
        import_phase_hook("write", total)
    pairs: list[tuple[ComplexInstance, CalParamImportPrepared]] = []
    for spec in specs:
        node = ComplexInstance(name=spec.name)
        controller.model.attach(node, parent=parent, reserve_existing=False, remap_ids=False)
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
        write_hook = lambda d, _t, tt=total, uh=umax, ph=progress_hook: ph(tt + d, uh)

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
