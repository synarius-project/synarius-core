"""Synarius ``runtime:fmu`` plugin: FMI 2.0 co-simulation via FMPy."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import UUID


class _Bundle:
    """Holds one FMU slave instance (avoid ``@dataclass``: dynamic plugin modules may lack ``sys.modules``)."""

    __slots__ = ("slave", "unzip_dir", "input_map", "output_vr", "node_label")

    def __init__(
        self,
        slave: Any,
        unzip_dir: Path,
        input_map: list[tuple[str, int]],
        output_vr: int | None,
        node_label: str,
    ) -> None:
        self.slave = slave
        self.unzip_dir = unzip_dir
        self.input_map = input_map
        self.output_vr = output_vr
        self.node_label = node_label


class FmuRuntimePlugin:
    """Instantiate FMUs from the compiled diagram and advance them on each ``step_fmu`` call."""

    name: str = "fmu_runtime"

    def __init__(self) -> None:
        self._bundles: dict[UUID, _Bundle] = {}

    def init_fmu(self, ctx: Any) -> None:
        self.shutdown_fmu(ctx)
        try:
            from fmpy import read_model_description
            from fmpy.fmi2 import FMU2Slave

            try:
                from fmpy.util import extract
            except ImportError:
                from fmpy import extract
        except ImportError:
            ctx.diagnostics.append(
                "FMU runtime: FMPy is not installed (optional extra: pip install 'synarius-core[fmu]' or fmpy)."
            )
            return

        compiled = ctx.artifacts.get("dataflow")
        if compiled is None:
            return
        fdiag = ctx.artifacts.get("fmu_diagram")
        if fdiag is None or not getattr(fdiag, "fmu_node_ids", None):
            return

        for uid in sorted(fdiag.fmu_node_ids, key=lambda u: str(u)):
            node = compiled.node_by_id.get(uid)
            if node is None:
                continue
            if not _node_has_fmu_path(node):
                continue
            path = Path(str(node.get("fmu.path"))).expanduser()
            if not path.is_file():
                ctx.diagnostics.append(f"FMU runtime: file missing for node {node.name!r}: {path}")
                continue
            try:
                model_description = read_model_description(str(path))
            except Exception as exc:  # noqa: BLE001
                ctx.diagnostics.append(f"FMU runtime: cannot read modelDescription for {node.name!r}: {exc}")
                continue
            if model_description.coSimulation is None:
                ctx.diagnostics.append(
                    f"FMU runtime: {node.name!r} has no coSimulation interface "
                    "(this plugin supports FMI 2.0 co-simulation only)."
                )
                continue
            fmi_ver = str(node.get("fmu.fmi_version") or "2.0").strip()
            if not fmi_ver.startswith("2"):
                ctx.diagnostics.append(
                    f"FMU runtime: {node.name!r} uses fmi_version={fmi_ver!r}; "
                    "only FMI 2.x co-simulation is implemented."
                )
                continue
            try:
                unzip_dir = Path(extract(str(path)))
            except Exception as exc:  # noqa: BLE001
                ctx.diagnostics.append(f"FMU runtime: extract failed for {node.name!r}: {exc}")
                continue
            mid = str(node.get("fmu.model_identifier") or "").strip()
            if not mid:
                mid = model_description.coSimulation.modelIdentifier
            try:
                slave = FMU2Slave(
                    guid=model_description.guid,
                    unzipDirectory=str(unzip_dir),
                    modelIdentifier=mid,
                    instanceName=f"syn_{node.name}_{uid.hex[:8]}",
                )
                slave.instantiate()
                start = _float_attr(node, "fmu.start_time", 0.0)
                stop = _float_attr(node, "fmu.stop_time", 1.0e9)
                slave.setupExperiment(startTime=start, stopTime=stop)
                slave.enterInitializationMode()
                slave.exitInitializationMode()
            except Exception as exc:  # noqa: BLE001
                ctx.diagnostics.append(f"FMU runtime: instantiate/setup failed for {node.name!r}: {exc}")
                shutil.rmtree(unzip_dir, ignore_errors=True)
                continue

            input_map, output_vr = _resolve_ios(node, model_description, ctx)
            self._bundles[uid] = _Bundle(
                slave=slave,
                unzip_dir=unzip_dir,
                input_map=input_map,
                output_vr=output_vr,
                node_label=node.name,
            )

    def step_fmu(self, ctx: Any, node_id: UUID) -> None:
        b = self._bundles.get(node_id)
        if b is None or ctx.scalar_workspace is None:
            return
        compiled = ctx.artifacts.get("dataflow")
        if compiled is None:
            return
        inc = compiled.incoming.get(node_id, {})
        try:
            vrs: list[int] = []
            vals: list[float] = []
            for pin_name, vr in b.input_map:
                src_id = inc.get(pin_name)
                v = 0.0 if src_id is None else float(ctx.scalar_workspace.get(src_id, 0.0))
                vrs.append(vr)
                vals.append(v)
            if vrs:
                b.slave.setReal(vrs, vals)
            h = float(ctx.options.get("communication_step_size") or 0.02)
            b.slave.doStep(currentCommunicationPoint=ctx.time_s, communicationStepSize=h)
            if b.output_vr is not None:
                y = b.slave.getReal([b.output_vr])[0]
                ctx.scalar_workspace[node_id] = float(y)
        except Exception as exc:  # noqa: BLE001
            ctx.diagnostics.append(f"FMU runtime: step failed for {b.node_label!r}: {exc}")

    def shutdown_fmu(self, ctx: Any) -> None:
        _ = ctx
        for _uid, b in list(self._bundles.items()):
            try:
                b.slave.terminate()
            except Exception:
                pass
            try:
                b.slave.freeInstance()
            except Exception:
                pass
            shutil.rmtree(b.unzip_dir, ignore_errors=True)
        self._bundles.clear()

    def reset_fmu(self, ctx: Any) -> None:
        self.shutdown_fmu(ctx)
        self.init_fmu(ctx)


def _node_has_fmu_path(node: Any) -> bool:
    from synarius_core.dataflow_sim import elementary_has_fmu_path
    from synarius_core.model import ElementaryInstance

    return isinstance(node, ElementaryInstance) and elementary_has_fmu_path(node)


def _float_attr(node: Any, path: str, default: float) -> float:
    try:
        v = node.get(path)
    except Exception:
        return default
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _resolve_ios(node: Any, model_description: Any, ctx: Any) -> tuple[list[tuple[str, int]], int | None]:
    try:
        pmap = node.get("pin")
    except Exception:
        pmap = {}
    if not isinstance(pmap, dict):
        pmap = {}
    md_vars = {v.name: v for v in model_description.modelVariables}

    inputs: list[tuple[str, int]] = []
    outputs: list[tuple[str, int]] = []

    for pin_name in sorted(pmap.keys()):
        meta = pmap.get(pin_name)
        if not isinstance(meta, dict):
            continue
        direction = str(meta.get("direction") or "").upper()
        is_out = direction == "OUT"
        vr_raw = meta.get("value_reference")
        if vr_raw is None:
            vm = _fmu_var_row(node, str(pin_name))
            if vm is not None and vm.get("value_reference") is not None:
                try:
                    vr_raw = int(vm["value_reference"])
                except (TypeError, ValueError):
                    vr_raw = None
        if vr_raw is None:
            mv = md_vars.get(str(pin_name))
            if mv is not None:
                vr_raw = mv.valueReference
        if vr_raw is None:
            ctx.diagnostics.append(
                f"FMU runtime: pin {pin_name!r} on {node.name!r} has no value reference; skipped."
            )
            continue
        vr = int(vr_raw)
        if is_out:
            outputs.append((str(pin_name), vr))
        else:
            inputs.append((str(pin_name), vr))

    outputs.sort(key=lambda x: x[0])
    primary_vr = outputs[0][1] if outputs else None
    return inputs, primary_vr


def _fmu_var_row(node: Any, pin_name: str) -> dict[str, Any] | None:
    try:
        arr = node.get("fmu.variables")
    except Exception:
        return None
    if not isinstance(arr, list):
        return None
    for item in arr:
        if isinstance(item, dict) and str(item.get("name") or "") == pin_name:
            return item
    return None
