"""Synarius ``runtime:fmu`` plugin: FMI 2.0 co-simulation via FMPy."""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from synarius_core.dataflow_sim.context import SimulationContext
from synarius_core.dataflow_sim.compiler import unpack_wire_ref
from synarius_core.model import Variable
from synarius_core.plugins.element_types import (
    ElementTypeHandler,
    SimContext,
    SimulationRuntimePlugin,
    SynariusPlugin,
)


class _FmuSimulationBridge(SimulationRuntimePlugin):
    """Draft ``SimulationRuntimePlugin`` facade over the legacy ``init_fmu`` / ``step_fmu`` API."""

    runtime_capability = "runtime:fmu"

    __slots__ = ("_host",)

    def __init__(self, host: "FmuRuntimePlugin") -> None:
        self._host = host

    def runtime_init(self, ctx: SimContext) -> None:
        self._host.init_fmu(ctx)

    def runtime_step(self, ctx: SimContext, node_id: UUID) -> None:
        self._host.step_fmu(ctx, node_id)

    def runtime_shutdown(self, ctx: SimContext) -> None:
        self._host.shutdown_fmu(ctx)


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
        "stop_time",
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
        *,
        stop_time: float,
    ) -> None:
        self.slave = slave
        self.unzip_dir = unzip_dir
        self.input_map = input_map
        self.parameter_input_map = parameter_input_map
        self.output_map = output_map
        self.node_label = node_label
        self.start_time = float(start_time)
        self.stop_time = float(stop_time)
        self.step_failed = False


class FmuRuntimePlugin(SynariusPlugin):
    """Instantiate FMUs from the compiled diagram and advance them on each ``step_fmu`` call."""

    name: str = "fmu_runtime"

    def __init__(self) -> None:
        self._bundles: dict[UUID, _Bundle] = {}

    # ---- FMPy / path / diagram helpers (private; flat module-level style on class) ----

    @staticmethod
    def _import_fmpy() -> tuple[Any, Any, Any] | None:
        try:
            from fmpy import read_model_description
            from fmpy.fmi2 import FMU2Slave

            try:
                from fmpy.util import extract
            except ImportError:
                from fmpy import extract
        except ImportError:
            return None
        return read_model_description, extract, FMU2Slave

    @staticmethod
    def _fmu_resolve_absolute_candidate(raw: Path) -> Path | None:
        try:
            return raw.resolve() if raw.is_file() else None
        except OSError:
            return None

    @staticmethod
    def _fmu_search_bases_from_ctx(ctx: Any) -> list[Path]:
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
        return bases

    @staticmethod
    def _fmu_try_relative_under_bases(raw: Path, bases: list[Path]) -> Path | None:
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

    @classmethod
    def _resolve_fmu_archive_path_expanded(cls, raw: Path, ctx: Any) -> Path | None:
        if raw.is_absolute():
            return cls._fmu_resolve_absolute_candidate(raw)
        return cls._fmu_try_relative_under_bases(raw, cls._fmu_search_bases_from_ctx(ctx))

    @classmethod
    def _resolve_fmu_archive_path(cls, raw_str: str, ctx: Any) -> Path | None:
        raw = Path(str(raw_str or "").strip()).expanduser()
        if not raw.parts or raw == Path("."):
            return None
        return cls._resolve_fmu_archive_path_expanded(raw, ctx)

    @staticmethod
    def _node_has_fmu_path(node: Any) -> bool:
        from synarius_core.dataflow_sim import elementary_has_fmu_path
        from synarius_core.model import ElementaryInstance

        return isinstance(node, ElementaryInstance) and elementary_has_fmu_path(node)

    @staticmethod
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

    @staticmethod
    def _variable_stim_float(var: Variable, key: str, default: float = 0.0) -> float:
        try:
            return float(var.get(key))
        except Exception:
            return default

    @staticmethod
    def _label_ws_read(
        ws: dict[Any, float],
        raw: Any,
        nb: dict[Any, Any],
    ) -> float:
        """Read from a label-keyed workspace via an incoming wire reference."""
        if raw is None:
            return 0.0
        try:
            src_id, src_pin = unpack_wire_ref(raw)
        except TypeError:
            return 0.0
        src_node = nb.get(src_id)
        if src_node is None:
            return 0.0
        from synarius_core.dataflow_sim import elementary_has_fmu_path
        from synarius_core.dataflow_sim.equation_walk import label as _lbl
        from synarius_core.model import ElementaryInstance
        src_label = _lbl(src_node)
        if isinstance(src_node, ElementaryInstance) and elementary_has_fmu_path(src_node):
            return float(ws.get(f"{src_label}.{src_pin}", 0.0))
        return float(ws.get(src_label, 0.0))

    @classmethod
    def _var_stim_value_t0(cls, var: Variable) -> float | None:
        from synarius_core.dataflow_sim.stimulation import (
            STIM_CONSTANT_VALUE,
            STIM_RAMP_OFFSET,
            STIM_SINE_AMPLITUDE,
            STIM_SINE_OFFSET,
            STIM_SINE_PHASE_DEG,
            STIM_STEP_HIGH,
            STIM_STEP_LOW,
            STIM_STEP_SWITCH_TIME_S,
            ensure_variable_stimulation_schema,
        )

        ensure_variable_stimulation_schema(var)
        try:
            kind = str(var.get("stim_kind") or "").strip().lower()
        except Exception:
            return None
        if kind in ("", "none", "off"):
            return None
        if kind == "constant":
            return cls._variable_stim_float(var, STIM_CONSTANT_VALUE, 0.0)
        if kind == "ramp":
            return cls._variable_stim_float(var, STIM_RAMP_OFFSET, 0.0)
        if kind == "sine":
            off = cls._variable_stim_float(var, STIM_SINE_OFFSET, 0.0)
            amp = cls._variable_stim_float(var, STIM_SINE_AMPLITUDE, 1.0)
            ph = math.radians(cls._variable_stim_float(var, STIM_SINE_PHASE_DEG, 0.0))
            return off + amp * math.sin(ph)
        if kind == "step":
            low = cls._variable_stim_float(var, STIM_STEP_LOW, 0.0)
            high = cls._variable_stim_float(var, STIM_STEP_HIGH, 1.0)
            t_sw = cls._variable_stim_float(var, STIM_STEP_SWITCH_TIME_S, 0.0)
            return high if 0.0 >= t_sw else low
        return None

    @staticmethod
    def _fmu_parameter_scalar_from_variable(var: Variable) -> float:
        from synarius_core.dataflow_sim.stimulation import STIM_CONSTANT_VALUE, ensure_variable_stimulation_schema

        ensure_variable_stimulation_schema(var)
        try:
            v = float(var.value)
        except (TypeError, ValueError):
            try:
                return float(var.get(STIM_CONSTANT_VALUE) or 0.0)
            except (TypeError, ValueError):
                return 0.0
        try:
            cst = float(var.get(STIM_CONSTANT_VALUE) or 0.0)
        except (TypeError, ValueError):
            cst = 0.0
        if v == 0.0 and cst != 0.0:
            return cst
        return v

    @staticmethod
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

    @staticmethod
    def _fmu_load_pin_map(node: Any) -> dict[Any, Any]:
        try:
            pmap = node.get("pin")
        except Exception:
            pmap = {}
        return pmap if isinstance(pmap, dict) else {}

    @staticmethod
    def _fmu_elementary_io_pin_sets(node: Any) -> tuple[set[str], set[str]]:
        try:
            from synarius_core.model import ElementaryInstance

            if isinstance(node, ElementaryInstance):
                return {p.name for p in node.out_pins}, {p.name for p in node.in_pins}
        except Exception:
            pass
        return set(), set()

    @staticmethod
    def _fmu_classify_pin_as_output(
        pin_s: str,
        meta: dict[str, Any],
        vm: dict[str, Any] | None,
        mv: Any,
        out_names: set[str],
        in_names: set[str],
    ) -> bool:
        if pin_s in out_names:
            return True
        if pin_s in in_names:
            return False
        direction = str(meta.get("direction") or "").upper()
        if direction == "OUT":
            return True
        if direction == "IN":
            return False
        caus_v = str((vm or {}).get("causality") or "").lower()
        caus_md = str(getattr(mv, "causality", None) or "").strip().lower() if mv is not None else ""
        if caus_v == "output" or caus_md == "output":
            return True
        if caus_v in ("input", "parameter") or caus_md in ("input", "parameter", "independent"):
            return False
        if caus_v == "local" or caus_md == "local":
            return True
        return False

    @staticmethod
    def _fmu_resolve_value_reference_raw(
        meta: dict[str, Any], vm: dict[str, Any] | None, mv: Any
    ) -> int | None:
        vr_raw = meta.get("value_reference")
        if vr_raw is None and vm is not None and vm.get("value_reference") is not None:
            try:
                vr_raw = int(vm["value_reference"])
            except (TypeError, ValueError):
                vr_raw = None
        if vr_raw is None and mv is not None:
            vr_raw = mv.valueReference
        if vr_raw is None:
            return None
        try:
            return int(vr_raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fmu_is_parameter_pin(vm: dict[str, Any] | None, mv: Any) -> bool:
        caus_v = str((vm or {}).get("causality") or "").lower()
        caus_md = str(getattr(mv, "causality", None) or "").strip().lower() if mv is not None else ""
        return caus_v == "parameter" or caus_md == "parameter"

    def _resolve_ios(
        self, node: Any, model_description: Any, ctx: Any
    ) -> tuple[list[tuple[str, int]], list[tuple[str, int]], list[tuple[str, int]]]:
        pmap = self._fmu_load_pin_map(node)
        md_vars = {v.name: v for v in model_description.modelVariables}
        out_names, in_names = self._fmu_elementary_io_pin_sets(node)

        inputs: list[tuple[str, int]] = []
        params: list[tuple[str, int]] = []
        outputs: list[tuple[str, int]] = []

        for pin_name in sorted(pmap.keys()):
            meta = pmap.get(pin_name)
            if not isinstance(meta, dict):
                continue
            pin_s = str(pin_name)
            vm = self._fmu_var_row(node, pin_s)
            mv = md_vars.get(pin_s)
            is_out = self._fmu_classify_pin_as_output(pin_s, meta, vm, mv, out_names, in_names)
            vr = self._fmu_resolve_value_reference_raw(meta, vm, mv)
            if vr is None:
                ctx.diagnostics.append(
                    f"FMU runtime: pin {pin_name!r} on {node.name!r} has no value reference; skipped."
                )
                continue
            if self._fmu_is_parameter_pin(vm, mv):
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

    def _parameter_value_for_init(
        self,
        raw: Any,
        ws: dict[Any, float],
        nb: dict[Any, Any],
    ) -> float | None:
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
                stim_v = self._var_stim_value_t0(src_node)
                if stim_v is not None:
                    return float(stim_v)
            return float(self._fmu_parameter_scalar_from_variable(src_node))
        return float(self._label_ws_read(ws, raw, nb))

    def _apply_parameter_reals_on_init(
        self,
        ctx: Any,
        slave: Any,
        compiled: Any,
        uid: UUID,
        parameter_input_map: list[tuple[str, int]],
    ) -> None:
        apply_params_on_init = bool(ctx.options.get("fmu_apply_parameters_on_init", True))
        if not parameter_input_map or not apply_params_on_init:
            return

        ws = ctx.scalar_workspace or {}
        inc = compiled.incoming.get(uid, {})
        nb = compiled.node_by_id
        pvrs: list[int] = []
        pvals: list[float] = []
        for pin_name, vr in parameter_input_map:
            raw = inc.get(pin_name)
            if raw is None:
                continue
            try:
                val = self._parameter_value_for_init(raw, ws, nb)
            except Exception:
                continue
            pvrs.append(vr)
            pvals.append(val)
        if pvrs:
            slave.setReal(pvrs, pvals)

    def _read_model_description_safe(
        self, path: Path, node: Any, read_model_description: Any, ctx: Any
    ) -> Any | None:
        try:
            return read_model_description(str(path))
        except Exception as exc:  # noqa: BLE001
            ctx.diagnostics.append(f"FMU runtime: cannot read modelDescription for {node.name!r}: {exc}")
            return None

    def _co_sim_fmi2_ok(self, node: Any, model_description: Any, ctx: Any) -> bool:
        if model_description.coSimulation is None:
            ctx.diagnostics.append(
                f"FMU runtime: {node.name!r} has no coSimulation interface "
                "(this plugin supports FMI 2.0 co-simulation only)."
            )
            return False
        fmi_ver = str(node.get("fmu.fmi_version") or "2.0").strip()
        if not fmi_ver.startswith("2"):
            ctx.diagnostics.append(
                f"FMU runtime: {node.name!r} uses fmi_version={fmi_ver!r}; "
                "only FMI 2.x co-simulation is implemented."
            )
            return False
        return True

    def _extract_unzip_dir(self, path: Path, node: Any, extract: Any, ctx: Any) -> Path | None:
        try:
            return Path(extract(str(path)))
        except Exception as exc:  # noqa: BLE001
            ctx.diagnostics.append(f"FMU runtime: extract failed for {node.name!r}: {exc}")
            return None

    def _try_instantiate_fmu_bundle(
        self,
        ctx: Any,
        compiled: Any,
        uid: UUID,
        node: Any,
        model_description: Any,
        unzip_dir: Path,
        FMU2Slave: Any,
        input_map: list[tuple[str, int]],
        output_map: list[tuple[str, int]],
        parameter_input_map: list[tuple[str, int]],
    ) -> bool:
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
            start = self._float_attr(node, "fmu.start_time", 0.0)
            stop = self._float_attr(node, "fmu.stop_time", 1.0e9)
            slave.setupExperiment(startTime=start, stopTime=stop)
            slave.enterInitializationMode()
            self._apply_parameter_reals_on_init(ctx, slave, compiled, uid, parameter_input_map)
            slave.exitInitializationMode()
        except Exception as exc:  # noqa: BLE001
            ctx.diagnostics.append(f"FMU runtime: instantiate/setup failed for {node.name!r}: {exc}")
            shutil.rmtree(unzip_dir, ignore_errors=True)
            return False

        self._bundles[uid] = _Bundle(
            slave=slave,
            unzip_dir=unzip_dir,
            input_map=input_map,
            parameter_input_map=parameter_input_map,
            output_map=output_map,
            node_label=node.name,
            start_time=float(start),
            stop_time=float(stop),
        )
        return True

    def _init_fmu_node(
        self,
        ctx: Any,
        compiled: Any,
        uid: UUID,
        read_model_description: Any,
        extract: Any,
        FMU2Slave: Any,
    ) -> None:
        node = compiled.node_by_id.get(uid)
        if node is None:
            return
        if not self._node_has_fmu_path(node):
            return

        raw_path = str(node.get("fmu.path") or "")
        path = self._resolve_fmu_archive_path(raw_path, ctx)
        if path is None:
            ctx.diagnostics.append(
                f"FMU runtime: file missing for node {node.name!r}: {raw_path!r} "
                f"(tried model_directory={ctx.options.get('model_directory')!r}, cwd ancestors, basename; cwd={Path.cwd()!s})"
            )
            return

        model_description = self._read_model_description_safe(path, node, read_model_description, ctx)
        if model_description is None:
            return
        if not self._co_sim_fmi2_ok(node, model_description, ctx):
            return

        unzip_dir = self._extract_unzip_dir(path, node, extract, ctx)
        if unzip_dir is None:
            return

        input_map, output_map, parameter_input_map = self._resolve_ios(node, model_description, ctx)
        self._try_instantiate_fmu_bundle(
            ctx,
            compiled,
            uid,
            node,
            model_description,
            unzip_dir,
            FMU2Slave,
            input_map,
            output_map,
            parameter_input_map,
        )

    def init_fmu(self, ctx: SimContext | SimulationContext) -> None:
        self.shutdown_fmu(ctx)
        fmpy = self._import_fmpy()
        if fmpy is None:
            ctx.diagnostics.append(
                "FMU runtime: FMPy is not installed (optional extra: pip install 'synarius-core[fmu]' or fmpy)."
            )
            return

        read_model_description, extract, FMU2Slave = fmpy

        compiled = ctx.artifacts.get("dataflow")
        if compiled is None:
            return
        fdiag = ctx.artifacts.get("fmu_diagram")
        if fdiag is None or not getattr(fdiag, "fmu_node_ids", None):
            return

        for uid in sorted(fdiag.fmu_node_ids, key=lambda u: str(u)):
            self._init_fmu_node(ctx, compiled, uid, read_model_description, extract, FMU2Slave)

    def _fmu_feed_inputs(
        self,
        b: _Bundle,
        inc: dict[str, Any],
        ws: dict[Any, float],
        nb: dict[Any, Any],
    ) -> None:
        vrs: list[int] = []
        vals: list[float] = []
        for pin_name, vr in b.input_map:
            raw = inc.get(pin_name)
            if raw is None:
                continue
            v = self._label_ws_read(ws, raw, nb)
            vrs.append(vr)
            vals.append(v)
        if vrs:
            b.slave.setReal(vrs, vals)

    def _fmu_write_outputs(self, b: _Bundle, ws: dict[Any, float], node_id: UUID, ys: Any) -> None:
        for (_pname, _vr), y in zip(b.output_map, ys, strict=True):
            ws[f"{b.node_label}.{_pname}"] = float(y)
        ws[b.node_label] = float(ys[0])

    def step_fmu(self, ctx: SimContext | SimulationContext, node_id: UUID) -> None:
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
            self._fmu_feed_inputs(b, inc, ws, nb)
            h = float(ctx.options.get("communication_step_size") or 0.02)
            ccp = max(float(b.start_time), float(ctx.time_s) - h)
            stop_t = float(b.stop_time)
            if ccp >= stop_t - 1e-12:
                return
            h_eff = min(h, max(0.0, stop_t - ccp))
            if h_eff <= 1e-15:
                return
            b.slave.doStep(currentCommunicationPoint=ccp, communicationStepSize=h_eff)
            if b.output_map:
                vrs_out = [vr for _pn, vr in b.output_map]
                ys = b.slave.getReal(vrs_out)
                self._fmu_write_outputs(b, ws, node_id, ys)
        except Exception as exc:  # noqa: BLE001
            ctx.diagnostics.append(f"FMU runtime: step failed for {b.node_label!r}: {exc}")
            b.step_failed = True
            ctx.diagnostics.append(
                f"FMU runtime: disabled further steps for {b.node_label!r} after first step failure."
            )

    def shutdown_fmu(self, ctx: SimContext | SimulationContext) -> None:
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

    def reset_fmu(self, ctx: SimContext | SimulationContext) -> None:
        self.shutdown_fmu(ctx)
        self.init_fmu(ctx)

    def element_type_handlers(self) -> list[ElementTypeHandler]:
        from synarius_core.plugins.FmuRuntime.fmu_instance_handler import FmuInstanceHandler

        return [FmuInstanceHandler()]

    def simulation_runtime(self) -> SimulationRuntimePlugin | None:
        return _FmuSimulationBridge(self)
