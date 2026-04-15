"""Compile a dataflow graph from the diagram model (variables, operators, connectors)."""

from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from synarius_core.model import BasicOperator, Connector, ElementaryInstance, Model, Variable

from ._std_type_keys import STD_ARITHMETIC_OP, STD_PARAM_LOOKUP
from .context import SimulationContext

if TYPE_CHECKING:
    pass


# Compiled edge: target pin wired from (source instance id, source output pin name).
WireRef = tuple[UUID, str]

# Directed dataflow edge for cycle analysis / delayed feedback (src -> dst.target_pin).
FeedbackWire = tuple[UUID, UUID, str]


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


@dataclass(frozen=True)
class CompiledDataflow:
    """Topological evaluation order and pin wiring for one root-level diagram."""

    topo_order: list[UUID]
    node_by_id: dict[UUID, ElementaryInstance]
    """target_block_id -> target_pin -> (source_block_id, source_pin)"""
    incoming: dict[UUID, dict[str, WireRef]]
    """Edges whose source is read from the **previous** committed workspace (unit delay)."""
    feedback_edges: frozenset[FeedbackWire] = field(default_factory=frozenset)
    """Maps each diagram instance id to the UUID key used in ``scalar_workspace`` (identity = default)."""
    workspace_key_uid: dict[UUID, UUID] = field(default_factory=dict)
    """Node ids of ``std.Kennwert`` / ``std.Kennlinie`` / ``std.Kennfeld`` blocks (STD_PARAM_LOOKUP)."""
    param_bound_node_ids: frozenset[UUID] = field(default_factory=frozenset)


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


def _tarjan_scc(node_ids: list[UUID], adj: dict[UUID, set[UUID]]) -> list[list[UUID]]:
    """Return list of SCCs (each a list of node ids)."""
    index = 0
    stack: list[UUID] = []
    on_stack: set[UUID] = set()
    indices: dict[UUID, int] = {}
    lowlink: dict[UUID, int] = {}
    sccs: list[list[UUID]] = []

    def strongconnect(v: UUID) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(adj.get(v, ()), key=str):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            comp: list[UUID] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for v in sorted(node_ids, key=str):
        if v not in indices:
            strongconnect(v)
    return sccs


def _fmu_in_feedback_cycle(
    edge_list: list[FeedbackWire],
    node_ids: list[UUID],
    fmu_ids: frozenset[UUID],
) -> bool:
    """True if an FMU diagram node lies on a directed cycle (SCC size > 1 or self-loop)."""
    if not fmu_ids:
        return False
    adj: dict[UUID, set[UUID]] = defaultdict(set)
    for s, d, _ in edge_list:
        adj[s].add(d)
    for comp in _tarjan_scc(node_ids, adj):
        cset = set(comp)
        if len(cset) == 1:
            u = comp[0]
            if u not in fmu_ids:
                continue
            if any(s == u and d == u for s, d, _ in edge_list):
                return True
        else:
            if fmu_ids & cset:
                return True
    return False


def _find_one_edge_on_cycle(edge_list: list[FeedbackWire]) -> FeedbackWire | None:
    """Return one directed edge that lies on a cycle, or ``None`` if ``edge_list`` is acyclic."""
    if not edge_list:
        return None
    adj: dict[UUID, list[FeedbackWire]] = defaultdict(list)
    verts: set[UUID] = set()
    for e in edge_list:
        s, d, _ = e
        verts.add(s)
        verts.add(d)
        adj[s].append(e)
    UNSEEN, VIS, DONE = 0, 1, 2
    state: dict[UUID, int] = {v: UNSEEN for v in verts}
    result: FeedbackWire | None = None

    def dfs(u: UUID) -> bool:
        nonlocal result
        state[u] = VIS
        for e in adj[u]:
            _, v, _ = e
            sv = state.get(v, UNSEEN)
            if sv == UNSEEN:
                if dfs(v):
                    return True
            elif sv == VIS:
                result = e
                return True
        state[u] = DONE
        return False

    for v in sorted(verts, key=str):
        if state.get(v, UNSEEN) == UNSEEN:
            if dfs(v):
                break
    return result


def _kahn_toposort(edge_list: list[FeedbackWire], node_ids: list[UUID]) -> tuple[list[UUID], bool]:
    """Topological order of ``node_ids`` using only ``edge_list``; ``ok`` is True iff the graph is a DAG."""
    ids_set = set(node_ids)
    in_deg = {n: 0 for n in node_ids}
    out_edges: dict[UUID, list[FeedbackWire]] = defaultdict(list)
    for e in edge_list:
        s, d, _ = e
        if s in ids_set and d in ids_set:
            out_edges[s].append(e)
            in_deg[d] += 1
    heap = [(str(n), n) for n in node_ids if in_deg[n] == 0]
    heapq.heapify(heap)
    topo: list[UUID] = []
    while heap:
        _, u = heapq.heappop(heap)
        topo.append(u)
        for e in out_edges[u]:
            _, v, _ = e
            in_deg[v] -= 1
            if in_deg[v] == 0:
                heapq.heappush(heap, (str(v), v))
    return topo, len(topo) == len(node_ids)


def _minimal_feedback_arc_set(
    edge_list: list[FeedbackWire], node_ids: list[UUID]
) -> tuple[list[FeedbackWire], list[FeedbackWire]]:
    """Split edges into (feedback_arcs, dag_edges). Feedback arcs get unit-delay reads."""
    working = list(edge_list)
    feedback: list[FeedbackWire] = []
    while True:
        _, ok = _kahn_toposort(working, node_ids)
        if ok:
            return feedback, working
        e = _find_one_edge_on_cycle(working)
        if e is None:
            return feedback, working
        feedback.append(e)
        working.remove(e)


def _workspace_key_uid_map(
    node_by_id: dict[UUID, ElementaryInstance],
    diagnostics: list[str],
) -> dict[UUID, UUID]:
    """Optional ``dataflow.scalar_slot_id`` merges multiple diagram nodes into one workspace UUID key."""
    out: dict[UUID, UUID] = {}
    for uid, node in node_by_id.items():
        key = uid
        try:
            raw = node.get("dataflow.scalar_slot_id")
        except (KeyError, TypeError, ValueError):
            raw = None
        if raw is not None and str(raw).strip() != "":
            try:
                peer = UUID(str(raw).strip())
            except ValueError:
                diagnostics.append(f"Invalid dataflow.scalar_slot_id on diagram node {node.name!r}; using own id.")
            else:
                if peer not in node_by_id:
                    diagnostics.append(
                        f"dataflow.scalar_slot_id {peer} on {node.name!r} is not a diagram node id; using own id."
                    )
                else:
                    key = peer
        out[uid] = key
    return out


def _validate_workspace_keys_vs_fmu(
    node_by_id: dict[UUID, ElementaryInstance],
    workspace_key_uid: dict[UUID, UUID],
    diagnostics: list[str],
) -> bool:
    """FMU diagram nodes must use their own workspace slot (no fusion)."""
    ok = True
    for uid, node in node_by_id.items():
        if not _is_fmu_diagram_node(node):
            continue
        if workspace_key_uid.get(uid, uid) != uid:
            diagnostics.append(
                f"FMU block {node.name!r}: dataflow.scalar_slot_id fusion is not supported; remove slot override."
            )
            ok = False
    return ok


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


def _fmu_diag_pin_connectivity(
    *,
    label: str,
    pmap: dict[Any, Any],
    var_idx: dict[str, dict[str, Any]],
    inc: dict[str, WireRef],
    out_pins: set[str],
    diagnostics: list[str],
) -> None:
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


def _fmu_diag_incoming_connector_causality(
    model: Model,
    *,
    fid: UUID,
    label: str,
    pmap: dict[Any, Any],
    var_idx: dict[str, dict[str, Any]],
    diagnostics: list[str],
) -> None:
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


def _fmu_diag_outgoing_connector_causality(
    model: Model,
    *,
    fid: UUID,
    label: str,
    pmap: dict[Any, Any],
    var_idx: dict[str, dict[str, Any]],
    diagnostics: list[str],
) -> None:
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


def _fmu_diag_edge_dtypes(
    model: Model,
    *,
    node_by_id: dict[UUID, ElementaryInstance],
    fid: UUID,
    node: ElementaryInstance,
    label: str,
    diagnostics: list[str],
) -> None:
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


def _append_fmu_compile_diagnostics_one(
    model: Model,
    *,
    node_by_id: dict[UUID, ElementaryInstance],
    incoming: dict[UUID, dict[str, WireRef]],
    outgoing: dict[UUID, set[str]],
    fid: UUID,
    diagnostics: list[str],
) -> None:
    node = node_by_id.get(fid)
    if node is None:
        return
    label = node.name
    var_idx = _fmu_variable_index(node)
    try:
        pmap_raw = node.get("pin")
    except (KeyError, TypeError, ValueError):
        pmap_raw = None
    pmap = pmap_raw if isinstance(pmap_raw, dict) else {}

    inc = incoming.get(fid, {})
    out_pins = outgoing.get(fid, set())

    _fmu_diag_pin_connectivity(
        label=label,
        pmap=pmap,
        var_idx=var_idx,
        inc=inc,
        out_pins=out_pins,
        diagnostics=diagnostics,
    )
    _fmu_diag_incoming_connector_causality(model, fid=fid, label=label, pmap=pmap, var_idx=var_idx, diagnostics=diagnostics)
    _fmu_diag_outgoing_connector_causality(model, fid=fid, label=label, pmap=pmap, var_idx=var_idx, diagnostics=diagnostics)
    _fmu_diag_edge_dtypes(
        model,
        node_by_id=node_by_id,
        fid=fid,
        node=node,
        label=label,
        diagnostics=diagnostics,
    )


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
        _append_fmu_compile_diagnostics_one(
            model,
            node_by_id=node_by_id,
            incoming=incoming,
            outgoing=outgoing,
            fid=fid,
            diagnostics=diagnostics,
        )


class DataflowCompilePass:
    """Compiler pass: build :class:`CompiledDataflow` and store under ``ctx.artifacts['dataflow']``."""

    name: str = "dataflow"
    stage: str = "compile"

    def _gather_node_by_id(self, model: Model, ctx: SimulationContext) -> dict[UUID, ElementaryInstance]:
        nodes = iter_live_diagram_nodes(model)
        node_by_id: dict[UUID, ElementaryInstance] = {}
        for n in nodes:
            if n.id is None:
                ctx.diagnostics.append("Skipping diagram node without id.")
                continue
            node_by_id[n.id] = n
        return node_by_id

    def _build_incoming_wiring(
        self, model: Model, node_by_id: dict[UUID, ElementaryInstance]
    ) -> tuple[dict[UUID, dict[str, WireRef]], list[FeedbackWire]]:
        incoming: dict[UUID, dict[str, WireRef]] = defaultdict(dict)
        edge_list: list[FeedbackWire] = []
        for c in iter_live_connectors(model):
            src = model.find_by_id(c.source_instance_id)
            dst = model.find_by_id(c.target_instance_id)
            if src is None or dst is None or src.id is None or dst.id is None:
                continue
            if src.id not in node_by_id or dst.id not in node_by_id:
                continue
            tp = str(c.target_pin)
            incoming[dst.id][tp] = (src.id, str(c.source_pin or "out"))
            edge_list.append((src.id, dst.id, tp))
        return incoming, edge_list

    def _maybe_warn_generic_elementaries(
        self, node_by_id: dict[UUID, ElementaryInstance], ctx: SimulationContext
    ) -> None:
        for n in node_by_id.values():
            if isinstance(n, ElementaryInstance) and not isinstance(n, (Variable, BasicOperator)):
                if n.type_key in STD_ARITHMETIC_OP:
                    continue
                if n.type_key in STD_PARAM_LOOKUP:
                    continue
                ctx.diagnostics.append(
                    "Dataflow graph includes generic elementary block(s); simple_scalar runtime does not execute them (outputs stay at initial scalar slot)."
                )
                break

    def _dataflow_compile_abort(self, ctx: SimulationContext) -> SimulationContext:
        ctx.artifacts["dataflow"] = None
        ctx.artifacts["fmu_diagram"] = None
        return ctx

    def _run_dataflow_validate_workspace(
        self,
        ctx: SimulationContext,
        node_by_id: dict[UUID, ElementaryInstance],
    ) -> dict[UUID, UUID] | None:
        workspace_key_uid = _workspace_key_uid_map(node_by_id, ctx.diagnostics)
        if not _validate_workspace_keys_vs_fmu(node_by_id, workspace_key_uid, ctx.diagnostics):
            return None
        return workspace_key_uid

    def _run_dataflow_validate_fmu_cycles(
        self,
        ctx: SimulationContext,
        edge_list: list[FeedbackWire],
        ids: list[UUID],
        node_by_id: dict[UUID, ElementaryInstance],
    ) -> bool:
        fmu_ids_preview = frozenset(uid for uid, n in node_by_id.items() if _is_fmu_diagram_node(n))
        if _fmu_in_feedback_cycle(edge_list, ids, fmu_ids_preview):
            ctx.diagnostics.append(
                "Dataflow graph has a cycle involving an FMU block; delayed feedback is not supported for FMU nodes."
            )
            return False
        return True

    def _run_dataflow_resolve_topo(
        self, ctx: SimulationContext, edge_list: list[FeedbackWire], ids: list[UUID]
    ) -> tuple[list[UUID], frozenset[FeedbackWire]] | None:
        feedback_edges_list, dag_edges = _minimal_feedback_arc_set(edge_list, ids)
        feedback_frozen = frozenset(feedback_edges_list)
        topo, dag_ok = _kahn_toposort(dag_edges, ids)
        if not dag_ok:
            ctx.diagnostics.append("Dataflow graph cycle resolution failed internally.")
            return None
        if feedback_frozen:
            ctx.diagnostics.append(
                "Dataflow graph had directed cycles; inferred unit-delay feedback on "
                f"{len(feedback_frozen)} edge(s) (see execution_semantics_v0_2, delayed feedback)."
            )
        return topo, feedback_frozen

    def _store_compiled_dataflow(
        self,
        ctx: SimulationContext,
        *,
        model: Model,
        node_by_id: dict[UUID, ElementaryInstance],
        incoming: dict[UUID, dict[str, WireRef]],
        topo: list[UUID],
        feedback_frozen: frozenset[FeedbackWire],
        workspace_key_uid: dict[UUID, UUID],
    ) -> None:
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
        param_bound_ids = frozenset(
            uid
            for uid, n in node_by_id.items()
            if isinstance(n, ElementaryInstance)
            and not isinstance(n, (Variable, BasicOperator))
            and n.type_key in STD_PARAM_LOOKUP
        )
        ctx.artifacts["dataflow"] = CompiledDataflow(
            topo_order=topo,
            node_by_id=node_by_id,
            incoming=incoming_ro,
            feedback_edges=feedback_frozen,
            workspace_key_uid=dict(workspace_key_uid),
            param_bound_node_ids=param_bound_ids,
        )

    def run(self, ctx: SimulationContext) -> SimulationContext:
        model = ctx.model
        node_by_id = self._gather_node_by_id(model, ctx)
        incoming, edge_list = self._build_incoming_wiring(model, node_by_id)

        ids = list(node_by_id.keys())
        workspace_key_uid = self._run_dataflow_validate_workspace(ctx, node_by_id)
        if workspace_key_uid is None:
            return self._dataflow_compile_abort(ctx)

        if not self._run_dataflow_validate_fmu_cycles(ctx, edge_list, ids, node_by_id):
            return self._dataflow_compile_abort(ctx)

        topo_feedback = self._run_dataflow_resolve_topo(ctx, edge_list, ids)
        if topo_feedback is None:
            return self._dataflow_compile_abort(ctx)
        topo, feedback_frozen = topo_feedback

        self._maybe_warn_generic_elementaries(node_by_id, ctx)
        self._store_compiled_dataflow(
            ctx,
            model=model,
            node_by_id=node_by_id,
            incoming=incoming,
            topo=topo,
            feedback_frozen=feedback_frozen,
            workspace_key_uid=workspace_key_uid,
        )
        return ctx
