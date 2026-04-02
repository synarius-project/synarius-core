"""Compile a dataflow graph from the diagram model (variables, operators, connectors)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any, TYPE_CHECKING
from uuid import UUID

from synarius_core.model import BasicOperator, Connector, ElementaryInstance, Model, Variable

from .context import SimulationContext

if TYPE_CHECKING:
    pass


# Compiled edge: target pin wired from (source instance id, source output pin name).
WireRef = tuple[UUID, str]


def unpack_wire_ref(raw: object) -> tuple[UUID, str]:
    """Normalize a compiled incoming edge (``WireRef`` or legacy bare :class:`UUID`)."""
    if isinstance(raw, tuple) and len(raw) >= 2:
        u, pin = raw[0], raw[1]
        if isinstance(u, UUID):
            return u, str(pin or "out")
    if isinstance(raw, UUID):
        return raw, "out"
    raise TypeError(f"invalid wire reference: {raw!r}")


def scalar_ws_read(
    ws: dict[object, float],
    raw: object,
    *,
    node_by_id: dict[UUID, ElementaryInstance],
) -> float:
    """Read a scalar from the workspace following an incoming edge (FMU outputs use ``(id, pin)`` keys)."""
    if raw is None:
        return 0.0
    src_id, src_pin = unpack_wire_ref(raw)
    src_node = node_by_id.get(src_id)
    if isinstance(src_node, ElementaryInstance) and elementary_has_fmu_path(src_node):
        return float(ws.get((src_id, src_pin), 0.0))
    return float(ws.get(src_id, 0.0))


# region agent log
try:
    _payload = {
        "sessionId": "ccbe80",
        "runId": "startup-import",
        "hypothesisId": "H_COMPILER_SYMBOL_PRESENT",
        "location": "compiler.py:module_import",
        "message": "compiler_loaded",
        "data": {
            "compiler_file": str(__file__),
            "has_scalar_ws_read": bool("scalar_ws_read" in globals()),
            "has_unpack_wire_ref": bool("unpack_wire_ref" in globals()),
        },
        "timestamp": int(time.time() * 1000),
    }
    with Path(r"h:\Programmierung\Synarius\debug-ccbe80.log").open("a", encoding="utf-8") as _df:
        _df.write(json.dumps(_payload, ensure_ascii=False) + "\n")
except Exception:
    pass
# endregion


@dataclass(frozen=True)
class CompiledDataflow:
    """Topological evaluation order and pin wiring for one root-level diagram."""

    topo_order: list[UUID]
    node_by_id: dict[UUID, ElementaryInstance]
    """target_block_id -> target_pin -> (source_block_id, source_pin)"""
    incoming: dict[UUID, dict[str, WireRef]]


@dataclass(frozen=True)
class CompiledFmuDiagram:
    """Nodes that carry an FMU file path (``fmu.path``); subset of :attr:`CompiledDataflow.node_by_id`."""

    fmu_node_ids: frozenset[UUID]


def iter_live_diagram_nodes(model: Model) -> list[ElementaryInstance]:
    """Diagram elementary blocks under ``model.root`` (variables, operators, FMU/library blocks, …), excluding trash."""
    out: list[ElementaryInstance] = []
    for child in model.root.children:
        if isinstance(child, ElementaryInstance):
            if not model.is_in_trash_subtree(child):
                out.append(child)
    return out


def iter_live_connectors(model: Model) -> list[Connector]:
    out: list[Connector] = []
    for child in model.root.children:
        if isinstance(child, Connector) and not model.is_in_trash_subtree(child):
            out.append(child)
    return out


def elementary_has_fmu_path(n: ElementaryInstance) -> bool:
    """True for non-variable/non-operator elementaries with a non-empty ``fmu.path`` (diagram FMU block)."""
    return _is_fmu_diagram_node(n)


def _is_fmu_diagram_node(n: ElementaryInstance) -> bool:
    """True for generic elementaries with a non-empty ``fmu.path`` (not variables/operators)."""
    if isinstance(n, (Variable, BasicOperator)):
        return False
    try:
        fm = n.get("fmu")
    except (KeyError, TypeError, ValueError):
        return False
    if not isinstance(fm, dict):
        return False
    return bool(str(fm.get("path") or "").strip())


def _fmu_variable_index(node: ElementaryInstance) -> dict[str, dict[str, Any]]:
    try:
        vars_ = node.get("fmu.variables")
    except (KeyError, TypeError, ValueError):
        return {}
    if not isinstance(vars_, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in vars_:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            out[name] = item
    return out


def _pin_meta(node: ElementaryInstance, pin_name: str) -> dict[str, Any] | None:
    try:
        pmap = node.get("pin")
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(pmap, dict):
        return None
    meta = pmap.get(pin_name)
    return meta if isinstance(meta, dict) else None


def _pin_is_input(meta: dict[str, Any] | None) -> bool:
    if not meta:
        return True
    d = str(meta.get("direction") or "").upper()
    return d != "OUT"


def _canonical_dtype(raw: object) -> str:
    if raw is None or raw == "":
        return "float"
    s = str(raw).strip().lower()
    if s in ("real", "double", "float", "single"):
        return "float"
    if s in ("int", "integer", "int32", "int64"):
        return "int"
    if s in ("bool", "boolean"):
        return "bool"
    if s in ("string", "str"):
        return "string"
    return "float"


def _dtypes_compatible_for_edge(src_t: str, dst_t: str) -> bool:
    if src_t == dst_t:
        return True
    if dst_t == "float" and src_t in ("int", "bool"):
        return True
    return False


def _skip_unconnected_fmu_input(var_meta: dict[str, Any] | None) -> bool:
    """Parameters / constants often have no dataflow edge."""
    if not var_meta:
        return False
    c = str(var_meta.get("causality") or "").strip().lower()
    if c in ("parameter", "independent", "constant"):
        return True
    return False


def _build_outgoing_pins(
    model: Model, node_by_id: dict[UUID, ElementaryInstance]
) -> dict[UUID, set[str]]:
    out: dict[UUID, set[str]] = defaultdict(set)
    for c in iter_live_connectors(model):
        src = model.find_by_id(c.source_instance_id)
        if src is None or src.id is None:
            continue
        if src.id not in node_by_id:
            continue
        dst = model.find_by_id(c.target_instance_id)
        if dst is None or dst.id is None:
            continue
        if dst.id not in node_by_id:
            continue
        out[src.id].add(str(c.source_pin))
    return dict(out)


def _append_fmu_compile_diagnostics(
    model: Model,
    *,
    node_by_id: dict[UUID, ElementaryInstance],
    incoming: dict[UUID, dict[str, WireRef]],
    fmu_ids: frozenset[UUID],
    diagnostics: list[str],
) -> None:
    if not fmu_ids:
        return

    outgoing = _build_outgoing_pins(model, node_by_id)
    for fid in sorted(fmu_ids, key=lambda u: str(u)):
        node = node_by_id.get(fid)
        if node is None:
            continue
        label = node.name
        var_idx = _fmu_variable_index(node)
        try:
            pmap_raw = node.get("pin")
        except (KeyError, TypeError, ValueError):
            pmap_raw = None
        pmap = pmap_raw if isinstance(pmap_raw, dict) else {}

        inc = incoming.get(fid, {})
        out_pins = outgoing.get(fid, set())

        for pin_name, meta in sorted(pmap.items()):
            if not isinstance(meta, dict):
                continue
            pin_s = str(pin_name)
            var_meta = var_idx.get(pin_s)
            is_in = _pin_is_input(meta)

            if is_in:
                if pin_s not in inc and not _skip_unconnected_fmu_input(var_meta):
                    diagnostics.append(
                        f"FMU '{label}': input pin {pin_s!r} has no incoming connector "
                        "(set via parameter causality in fmu.variables to suppress if intentional)."
                    )
            else:
                if pin_s not in out_pins:
                    diagnostics.append(f"FMU '{label}': output pin {pin_s!r} has no outgoing connector.")

        for c in iter_live_connectors(model):
            if c.target_instance_id != fid:
                continue
            tpin = str(c.target_pin)
            vm = var_idx.get(tpin)
            if vm is not None:
                caus = str(vm.get("causality") or "").strip().lower()
                if caus == "output":
                    diagnostics.append(
                        f"FMU '{label}': variable {tpin!r} is declared output in fmu.variables "
                        "but is a connector *target* pin (outputs must be sources)."
                    )
                meta_t = pmap.get(tpin)
                if caus in ("input", "parameter") and meta_t and not _pin_is_input(meta_t):
                    diagnostics.append(
                        f"FMU '{label}': pin {tpin!r} is an input/parameter in fmu.variables "
                        "but pin.direction is OUT in the diagram pin map."
                    )

        for c in iter_live_connectors(model):
            if c.source_instance_id != fid:
                continue
            spin = str(c.source_pin)
            vm = var_idx.get(spin)
            if vm is not None:
                caus = str(vm.get("causality") or "").strip().lower()
                if caus in ("input", "parameter"):
                    diagnostics.append(
                        f"FMU '{label}': variable {spin!r} is declared {caus} in fmu.variables "
                        "but is a connector *source* pin (inputs must be targets)."
                    )
                meta_s = pmap.get(spin)
                if caus == "output" and meta_s and _pin_is_input(meta_s):
                    diagnostics.append(
                        f"FMU '{label}': pin {spin!r} is an output in fmu.variables "
                        "but pin.direction is IN in the diagram pin map."
                    )

        for c in iter_live_connectors(model):
            if c.target_instance_id != fid:
                continue
            src = model.find_by_id(c.source_instance_id)
            if src is None or src.id is None or src.id not in node_by_id:
                continue
            if not isinstance(src, ElementaryInstance):
                continue
            tpin = str(c.target_pin)
            spin = str(c.source_pin)
            sm = _pin_meta(src, spin)
            tm = _pin_meta(node, tpin)
            if sm is None or tm is None:
                continue
            src_t = _canonical_dtype(sm.get("data_type"))
            dst_t = _canonical_dtype(tm.get("data_type"))
            if not _dtypes_compatible_for_edge(src_t, dst_t):
                diagnostics.append(
                    f"FMU '{label}': type mismatch on edge to pin {tpin!r}: "
                    f"source {src.name!r}.{spin} ({src_t}) -> target ({dst_t})."
                )


class DataflowCompilePass:
    """Compiler pass: build :class:`CompiledDataflow` and store under ``ctx.artifacts['dataflow']``."""

    name: str = "dataflow"
    stage: str = "compile"

    def run(self, ctx: SimulationContext) -> SimulationContext:
        model = ctx.model
        nodes = iter_live_diagram_nodes(model)
        node_by_id: dict[UUID, ElementaryInstance] = {}
        for n in nodes:
            if n.id is None:
                ctx.diagnostics.append("Skipping diagram node without id.")
                continue
            node_by_id[n.id] = n

        incoming: dict[UUID, dict[str, WireRef]] = defaultdict(dict)
        edges: list[tuple[UUID, UUID]] = []

        for c in iter_live_connectors(model):
            src = model.find_by_id(c.source_instance_id)
            dst = model.find_by_id(c.target_instance_id)
            if src is None or dst is None or src.id is None or dst.id is None:
                continue
            if src.id not in node_by_id or dst.id not in node_by_id:
                continue
            incoming[dst.id][c.target_pin] = (src.id, str(c.source_pin or "out"))
            edges.append((src.id, dst.id))

        ids = list(node_by_id.keys())
        in_deg = {i: 0 for i in ids}
        adj: dict[UUID, list[UUID]] = defaultdict(list)
        for a, b in edges:
            if a in in_deg and b in in_deg:
                adj[a].append(b)
                in_deg[b] += 1

        q = deque([i for i in ids if in_deg[i] == 0])
        topo: list[UUID] = []
        while q:
            u = q.popleft()
            topo.append(u)
            for v in adj[u]:
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    q.append(v)

        if len(topo) != len(ids):
            ctx.diagnostics.append("Dataflow graph has a cycle; simulation is undefined.")
            ctx.artifacts["dataflow"] = None
            ctx.artifacts["fmu_diagram"] = None
            return ctx

        for n in node_by_id.values():
            if isinstance(n, ElementaryInstance) and not isinstance(n, (Variable, BasicOperator)):
                ctx.diagnostics.append(
                    "Dataflow graph includes generic elementary block(s); simple_scalar runtime does not execute them (outputs stay at initial scalar slot)."
                )
                break

        fmu_ids = frozenset(uid for uid, n in node_by_id.items() if _is_fmu_diagram_node(n))
        ctx.artifacts["fmu_diagram"] = CompiledFmuDiagram(fmu_node_ids=fmu_ids)
        incoming_ro = dict(incoming)
        _append_fmu_compile_diagnostics(
            model,
            node_by_id=node_by_id,
            incoming=incoming_ro,
            fmu_ids=fmu_ids,
            diagnostics=ctx.diagnostics,
        )

        ctx.artifacts["dataflow"] = CompiledDataflow(
            topo_order=topo,
            node_by_id=node_by_id,
            incoming=incoming_ro,
        )
        return ctx
