"""Compile a dataflow graph from the diagram model (variables, operators, connectors)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from synarius_core.model import BasicOperator, Connector, Model, Variable

from .context import SimulationContext

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class CompiledDataflow:
    """Topological evaluation order and pin wiring for one root-level diagram."""

    topo_order: list[UUID]
    node_by_id: dict[UUID, Variable | BasicOperator]
    """target_block_id -> target_pin -> source_block_id"""
    incoming: dict[UUID, dict[str, UUID]]


def iter_live_diagram_nodes(model: Model) -> list[Variable | BasicOperator]:
    """Variables and operators directly under ``model.root``, excluding trash subtree."""
    out: list[Variable | BasicOperator] = []
    for child in model.root.children:
        if isinstance(child, (Variable, BasicOperator)):
            if not model.is_in_trash_subtree(child):
                out.append(child)
    return out


def iter_live_connectors(model: Model) -> list[Connector]:
    out: list[Connector] = []
    for child in model.root.children:
        if isinstance(child, Connector) and not model.is_in_trash_subtree(child):
            out.append(child)
    return out


class DataflowCompilePass:
    """Compiler pass: build :class:`CompiledDataflow` and store under ``ctx.artifacts['dataflow']``."""

    name: str = "dataflow"
    stage: str = "compile"

    def run(self, ctx: SimulationContext) -> SimulationContext:
        model = ctx.model
        nodes = iter_live_diagram_nodes(model)
        node_by_id: dict[UUID, Variable | BasicOperator] = {}
        for n in nodes:
            if n.id is None:
                ctx.diagnostics.append("Skipping diagram node without id.")
                continue
            node_by_id[n.id] = n

        incoming: dict[UUID, dict[str, UUID]] = defaultdict(dict)
        edges: list[tuple[UUID, UUID]] = []

        for c in iter_live_connectors(model):
            src = model.find_by_id(c.source_instance_id)
            dst = model.find_by_id(c.target_instance_id)
            if src is None or dst is None or src.id is None or dst.id is None:
                continue
            if src.id not in node_by_id or dst.id not in node_by_id:
                continue
            incoming[dst.id][c.target_pin] = src.id
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
            return ctx

        ctx.artifacts["dataflow"] = CompiledDataflow(
            topo_order=topo,
            node_by_id=node_by_id,
            incoming=dict(incoming),
        )
        return ctx
