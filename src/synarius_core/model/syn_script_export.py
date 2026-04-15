"""Best-effort export of the root-level dataflow diagram to a ``.syn`` command script."""

from __future__ import annotations

import shlex
from typing import Any
from uuid import UUID

from synarius_core.dataflow_sim.compiler import elementary_has_fmu_path

from .complex_instance import ComplexInstance
from .connector import Connector
from .diagram_blocks import BasicOperator, DataViewer, Variable
from .elementary import ElementaryInstance
from .root_model import Model


def _size_scalar(inst: Any) -> float:
    s = getattr(inst, "size", None)
    if s is None:
        return 1.0
    w = float(getattr(s, "width", 1.0))
    h = float(getattr(s, "height", 1.0))
    return w if abs(w - h) < 1e-9 else w


def _fmt_set_scalar(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    return shlex.quote(str(val))


def _emit_variable_lines(v: Variable) -> list[str]:
    x, y = float(v.position.x), float(v.position.y)
    s = _size_scalar(v)
    lines = [f"new Variable {shlex.quote(v.name)} {x:g} {y:g} {s:g}"]
    try:
        val = v.value
        if val is not None and str(val).strip() != "":
            lines.append(f"set {shlex.quote(v.name)}.value {_fmt_set_scalar(val)}")
    except Exception:
        pass
    try:
        u = v.unit
        if u is not None and str(u).strip() != "":
            lines.append(f"set {shlex.quote(v.name)}.unit {shlex.quote(str(u))}")
    except Exception:
        pass
    return lines


def _emit_basic_operator_lines(o: BasicOperator) -> list[str]:
    sym = str(o.operation.value)
    x, y = float(o.position.x), float(o.position.y)
    s = _size_scalar(o)
    parts = ["new", "BasicOperator", sym, f"{x:g}", f"{y:g}"]
    if abs(s - 1.0) > 1e-9:
        parts.append(f"{s:g}")
    parts.append(f"name={shlex.quote(o.name)}")
    return [" ".join(parts)]


def _emit_elementary_lines(el: ElementaryInstance) -> list[str]:
    x, y = float(el.position.x), float(el.position.y)
    s = _size_scalar(el)
    tk = str(el.type_key)
    if elementary_has_fmu_path(el):
        fm = el.get("fmu")
        if not isinstance(fm, dict):
            raise ValueError(f"FMU block {el.name!r} has no fmu metadata.")
        path = str(fm.get("path") or "").strip()
        if not path:
            raise ValueError(f"FMU block {el.name!r} has empty fmu.path.")
        parts = [
            "new",
            "FmuInstance",
            shlex.quote(el.name),
            f"{x:g}",
            f"{y:g}",
            f"{s:g}",
            f"fmu_path={shlex.quote(path)}",
        ]
        if tk and tk.strip():
            parts.append(f"type_key={shlex.quote(tk)}")
        return [" ".join(parts)]
    return [f"new Elementary {shlex.quote(el.name)} {x:g} {y:g} {s:g} type_key={shlex.quote(tk)}"]


def _emit_dataviewer_lines(dv: DataViewer) -> list[str]:
    x, y = float(dv.position.x), float(dv.position.y)
    vid = int(dv.get("dataviewer_id"))
    return [f"new DataViewer {x:g} {y:g} dataviewer_id={vid}"]


def _emit_connector_line(model: Model, c: Connector, id_to_script_ref: dict[Any, str]) -> str | None:
    src = model.find_by_id(c.source_instance_id)
    dst = model.find_by_id(c.target_instance_id)
    if src is None or dst is None:
        return None
    sr = id_to_script_ref.get(src.id)
    tr = id_to_script_ref.get(dst.id)
    if sr is None or tr is None:
        return None
    parts = [
        "new",
        "Connector",
        shlex.quote(sr),
        shlex.quote(tr),
        f"source_pin={shlex.quote(str(c.source_pin))}",
        f"target_pin={shlex.quote(str(c.target_pin))}",
    ]
    if not c.directed:
        parts.append("directed=false")
    try:
        bends = c.get("orthogonal_bends")
    except Exception:
        bends = []
    if bends:
        inner = ",".join(f"{float(v):g}" for v in bends)
        parts.append(f"orthogonal_bends={shlex.quote(inner)}")
    return " ".join(parts)


def export_root_diagram_syn_text(model: Model) -> str:
    """
    Build UTF-8 text for a ``load``-able script: diagram objects directly under ``model.root``.

    Skips structural ``ComplexInstance`` children (``measurements``, ``trash``, …) and anything
    under the trash subtree. Unsupported direct children raise :class:`ValueError`.
    """
    lines: list[str] = [
        "# Exported by Synarius Studio (best-effort). Review before reuse.",
        "",
    ]
    root = model.root
    children = [c for c in root.children if getattr(c, "parent", None) is root]
    diagram_nodes: list[Any] = []
    connectors: list[Connector] = []
    for ch in children:
        if model.is_in_trash_subtree(ch):
            continue
        if isinstance(ch, Connector):
            connectors.append(ch)
        elif isinstance(ch, (Variable, BasicOperator, DataViewer)):
            diagram_nodes.append(ch)
        elif isinstance(ch, ElementaryInstance):
            diagram_nodes.append(ch)
        elif isinstance(ch, ComplexInstance):
            continue
        else:
            raise ValueError(f"Unsupported root-level object for export: {type(ch).__name__} ({ch!r})")

    id_to_script_ref: dict[UUID, str] = {}
    for obj in diagram_nodes:
        id_to_script_ref[obj.id] = obj.name

    def _sort_key(o: Any) -> tuple[float, float, str]:
        return (float(o.position.y), float(o.position.x), o.name)

    for obj in sorted(diagram_nodes, key=_sort_key):
        if isinstance(obj, Variable):
            lines.extend(_emit_variable_lines(obj))
        elif isinstance(obj, BasicOperator):
            lines.extend(_emit_basic_operator_lines(obj))
        elif isinstance(obj, DataViewer):
            lines.extend(_emit_dataviewer_lines(obj))
        elif isinstance(obj, ElementaryInstance):
            lines.extend(_emit_elementary_lines(obj))
        lines.append("")

    for c in sorted(connectors, key=lambda x: (x.name, str(x.source_instance_id))):
        ln = _emit_connector_line(model, c, id_to_script_ref)
        if ln:
            lines.append(ln)
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
