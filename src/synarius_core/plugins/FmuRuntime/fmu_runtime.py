"""Synarius ``runtime:fmu`` plugin: FMI 2.0 co-simulation via FMPy."""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from synarius_core.dataflow_sim.compiler import scalar_ws_read, unpack_wire_ref
from synarius_core.model import Variable


def _var_stim_value_t0(var: Variable) -> float | None:
    try:
        kind = str(var.get("stim_kind") or "").strip().lower()
    except Exception:
        return None
    if kind in ("", "none", "off"):
        return None

    def _f(key: str, default: float = 0.0) -> float:
        try:
            return float(var.get(key))
        except Exception:
            return default

    if kind == "constant":
        return _f("stim_p0", 0.0)
    if kind == "ramp":
        return _f("stim_p0", 0.0)
    if kind == "sine":
        off = _f("stim_p0", 0.0)
        amp = _f("stim_p1", 1.0)
        ph = math.radians(_f("stim_p3", 0.0))
        return off + amp * math.sin(ph)
    if kind == "step":
        low = _f("stim_p0", 0.0)
        high = _f("stim_p2", 1.0)
        t_sw = _f("stim_p1", 0.0)
        return high if 0.0 >= t_sw else low
    return None


def _fmu_parameter_scalar_from_variable(var: Variable) -> float:
    """Numeric value for an FMU *parameter* pin driven by a diagram :class:`Variable`.

    When ``stim_kind`` is off, dataflow conventionally uses :attr:`Variable.value`, but the Studio
    stimulation UI and console often still set ``stim_p0`` (always logged on OK). If ``value`` is
    still ``0.0`` while ``stim_p0`` is non-zero, treat ``stim_p0`` as the authored constant so log,
    diagram overlay, and FMU stay aligned. Explicit ``value == 0`` with stale non-zero ``stim_p0``
    is ambiguous: clear ``stim_p0`` or set ``value`` to zero after syncing from the dialog.
    """
    try:
        v = float(var.value)
    except (TypeError, ValueError):
        try:
            return float(var.get("stim_p0") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    try:
        p0 = float(var.get("stim_p0") or 0.0)
    except (TypeError, ValueError):
        p0 = 0.0
    if v == 0.0 and p0 != 0.0:
        return p0
    return v


def _resolve_fmu_archive_path(raw_str: str, ctx: Any) -> Path | None:
    """Resolve ``fmu.path`` for :func:`init_fmu`.

    Order: absolute path as given; then ``model_directory`` (from last ``load``); then each directory
    from :func:`os.getcwd` up to the filesystem root. The upward crawl fixes Studio sessions where no
    ``load`` ran but the working directory is a repo / project subtree containing the ``.fmu``.
    """
    raw = Path(str(raw_str or "").strip()).expanduser()
    if not raw.parts or raw == Path("."):
        return None
    if raw.is_absolute():
        try:
            return raw.resolve() if raw.is_file() else None
        except OSError:
            return None
    bases: list[Path] = []
    md = ctx.options.get("model_directory")
    if md is not None and str(md).strip():
        bases.append(Path(str(md)))
    cur = Path.cwd()
    for _ in range(64):
        try:
            br = cur.resolve()
        except OSError:
            br = cur
        bases.append(br)
        if br.parent == br:
            break
        cur = br.parent
    rel_variants = [raw]
    if raw != Path(raw.name):
        rel_variants.append(Path(raw.name))
    seen: set[Path] = set()
    for base in bases:
        try:
            br = base.expanduser().resolve()
        except OSError:
            br = base.expanduser()
        if br in seen:
            continue
        seen.add(br)
        for rel in rel_variants:
            try:
                cand = (br / rel).resolve()
            except OSError:
                cand = br / rel
            try:
                if cand.is_file():
                    return cand
            except OSError:
                continue
    return None


class _Bundle:
    """Holds one FMU slave instance (avoid ``@dataclass``: dynamic plugin modules may lack ``sys.modules``)."""

    __slots__ = (
        "slave",
        "unzip_dir",
        "input_map",
        "parameter_input_map",
        "output_map",
        "node_label",
        "start_time",
        "step_failed",
    )

    def __init__(
        self,
        slave: Any,
        unzip_dir: Path,
        input_map: list[tuple[str, int]],
        parameter_input_map: list[tuple[str, int]],
        output_map: list[tuple[str, int]],
        node_label: str,
        start_time: float,
    ) -> None:
        self.slave = slave
        self.unzip_dir = unzip_dir
        self.input_map = input_map
        self.parameter_input_map = parameter_input_map
        self.output_map = output_map
        self.node_label = node_label
        self.start_time = float(start_time)
        self.step_failed = False


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
            raw_path = str(node.get("fmu.path") or "")
            path = _resolve_fmu_archive_path(raw_path, ctx)
            if path is None:
                ctx.diagnostics.append(
                    f"FMU runtime: file missing for node {node.name!r}: {raw_path!r} "
                    f"(tried model_directory={ctx.options.get('model_directory')!r}, cwd ancestors, basename; cwd={Path.cwd()!s})"
                )
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
            input_map, output_map, parameter_input_map = _resolve_ios(node, model_description, ctx)
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
                # Default True: diagram wires to FMU parameter pins (e.g. BouncingBall ``g``) must override
                # modelDescription start values whenever the host does not opt out explicitly.
                apply_params_on_init = bool(ctx.options.get("fmu_apply_parameters_on_init", True))
                if parameter_input_map and apply_params_on_init:
                    ws = ctx.scalar_workspace or {}
                    inc = compiled.incoming.get(uid, {})
                    nb = compiled.node_by_id
                    pvrs: list[int] = []
                    pvals: list[float] = []
                    ppins: list[str] = []
                    psrc: list[dict[str, object]] = []
                    for pin_name, vr in parameter_input_map:
                        raw = inc.get(pin_name)
                        if raw is None:
                            psrc.append({"pin": str(pin_name), "source": None})
                            continue
                        try:
                            src_id, _src_pin = unpack_wire_ref(raw)
                            src_node = nb.get(src_id)
                        except Exception:
                            src_node = None
                        if isinstance(src_node, Variable):
                            stim_kind = ""
                            try:
                                stim_kind = str(src_node.get("stim_kind") or "").strip().lower()
                            except Exception:
                                stim_kind = ""
                            if stim_kind not in ("", "none", "off"):
                                stim_v = _var_stim_value_t0(src_node)
                                if stim_v is not None:
                                    pvals.append(float(stim_v))
                                    psrc.append(
                                        {
                                            "pin": str(pin_name),
                                            "source_name": str(src_node.name),
                                            "source_type": "stim_preferred",
                                            "source_value": float(stim_v),
                                            "stim_kind": stim_kind,
                                            "stim_p0": float(src_node.get("stim_p0") or 0.0),
                                        }
                                    )
                                    pvrs.append(vr)
                                    ppins.append(str(pin_name))
                                    continue
                            eff = _fmu_parameter_scalar_from_variable(src_node)
                            pvals.append(float(eff))
                            psrc.append(
                                {
                                    "pin": str(pin_name),
                                    "source_name": str(src_node.name),
                                    "source_type": "Variable.value_or_stim_p0",
                                    "source_value": float(eff),
                                    "stim_kind": str(src_node.get("stim_kind") or ""),
                                    "stim_p0": float(src_node.get("stim_p0") or 0.0),
                                }
                            )
                        else:
                            ws_val = scalar_ws_read(ws, raw, node_by_id=nb)
                            pvals.append(ws_val)
                            psrc.append(
                                {
                                    "pin": str(pin_name),
                                    "source_name": str(getattr(src_node, "name", "")),
                                    "source_type": "workspace_read",
                                    "source_value": float(ws_val),
                                }
                            )
                        pvrs.append(vr)
                        ppins.append(str(pin_name))
                    if pvrs:
                        slave.setReal(pvrs, pvals)
                elif parameter_input_map and not apply_params_on_init:
                    pass
                slave.exitInitializationMode()
            except Exception as exc:  # noqa: BLE001
                ctx.diagnostics.append(f"FMU runtime: instantiate/setup failed for {node.name!r}: {exc}")
                shutil.rmtree(unzip_dir, ignore_errors=True)
                continue

            self._bundles[uid] = _Bundle(
                slave=slave,
                unzip_dir=unzip_dir,
                input_map=input_map,
                parameter_input_map=parameter_input_map,
                output_map=output_map,
                node_label=node.name,
                start_time=float(start),
            )

    def step_fmu(self, ctx: Any, node_id: UUID) -> None:
        b = self._bundles.get(node_id)
        if b is None or ctx.scalar_workspace is None:
            return
        if b.step_failed:
            return
        compiled = ctx.artifacts.get("dataflow")
        if compiled is None:
            return
        inc = compiled.incoming.get(node_id, {})
        ws = ctx.scalar_workspace
        nb = compiled.node_by_id
        try:
            vrs: list[int] = []
            vals: list[float] = []
            for pin_name, vr in b.input_map:
                raw = inc.get(pin_name)
                # Keep FMU defaults/start values for unconnected inputs (especially parameters like g/e).
                if raw is None:
                    continue
                v = scalar_ws_read(ws, raw, node_by_id=nb)
                vrs.append(vr)
                vals.append(v)
            if vrs:
                b.slave.setReal(vrs, vals)
            h = float(ctx.options.get("communication_step_size") or 0.02)
            # Engine advances ``ctx.time_s`` before stepping nodes; FMU doStep needs the *current* point
            # of the interval, i.e. ``t_prev``, not ``t_next``.
            ccp = max(float(b.start_time), float(ctx.time_s) - h)
            b.slave.doStep(currentCommunicationPoint=ccp, communicationStepSize=h)
            if b.output_map:
                vrs_out = [vr for _pn, vr in b.output_map]
                ys = b.slave.getReal(vrs_out)
                for (_pname, _vr), y in zip(b.output_map, ys, strict=True):
                    ws[(node_id, _pname)] = float(y)
                ws[node_id] = float(ys[0])
        except Exception as exc:  # noqa: BLE001
            ctx.diagnostics.append(f"FMU runtime: step failed for {b.node_label!r}: {exc}")
            b.step_failed = True
            ctx.diagnostics.append(
                f"FMU runtime: disabled further steps for {b.node_label!r} after first step failure."
            )

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


def _resolve_ios(
    node: Any, model_description: Any, ctx: Any
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], list[tuple[str, int]]]:
    try:
        pmap = node.get("pin")
    except Exception:
        pmap = {}
    if not isinstance(pmap, dict):
        pmap = {}
    md_vars = {v.name: v for v in model_description.modelVariables}

    out_names: set[str] = set()
    in_names: set[str] = set()
    try:
        from synarius_core.model import ElementaryInstance

        if isinstance(node, ElementaryInstance):
            out_names = {p.name for p in node.out_pins}
            in_names = {p.name for p in node.in_pins}
    except Exception:
        pass

    inputs: list[tuple[str, int]] = []
    params: list[tuple[str, int]] = []
    outputs: list[tuple[str, int]] = []

    for pin_name in sorted(pmap.keys()):
        meta = pmap.get(pin_name)
        if not isinstance(meta, dict):
            continue
        pin_s = str(pin_name)
        vm = _fmu_var_row(node, pin_s)
        mv = md_vars.get(pin_s)

        if pin_s in out_names:
            is_out = True
        elif pin_s in in_names:
            is_out = False
        else:
            direction = str(meta.get("direction") or "").upper()
            if direction == "OUT":
                is_out = True
            elif direction == "IN":
                is_out = False
            else:
                caus_v = str((vm or {}).get("causality") or "").lower()
                caus_md = str(getattr(mv, "causality", None) or "").strip().lower() if mv is not None else ""
                if caus_v == "output" or caus_md == "output":
                    is_out = True
                elif caus_v in ("input", "parameter") or caus_md in ("input", "parameter", "independent"):
                    is_out = False
                elif caus_v == "local" or caus_md == "local":
                    # Modelica state / internal reals exposed as diagram pins (e.g. BouncingBall h, v).
                    is_out = True
                else:
                    is_out = False

        vr_raw = meta.get("value_reference")
        if vr_raw is None and vm is not None and vm.get("value_reference") is not None:
            try:
                vr_raw = int(vm["value_reference"])
            except (TypeError, ValueError):
                vr_raw = None
        if vr_raw is None and mv is not None:
            vr_raw = mv.valueReference
        if vr_raw is None:
            ctx.diagnostics.append(
                f"FMU runtime: pin {pin_name!r} on {node.name!r} has no value reference; skipped."
            )
            continue
        vr = int(vr_raw)
        caus_v = str((vm or {}).get("causality") or "").lower()
        caus_md = str(getattr(mv, "causality", None) or "").strip().lower() if mv is not None else ""
        is_param = caus_v == "parameter" or caus_md == "parameter"
        if is_param:
            params.append((pin_s, vr))
            continue
        if is_out:
            outputs.append((pin_s, vr))
        else:
            inputs.append((pin_s, vr))

    outputs.sort(key=lambda x: x[0])
    params.sort(key=lambda x: x[0])
    if not outputs and pmap:
        ctx.diagnostics.append(
            f"FMU runtime: {node.name!r} resolved zero output pins; downstream wires will stay at zero."
        )
    return inputs, outputs, params


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
