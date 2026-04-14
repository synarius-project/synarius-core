from __future__ import annotations

import json
import shlex
from datetime import datetime
from operator import attrgetter
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

import numpy as np
from immutables import Map

from synarius_core.library import LibraryCatalog
from synarius_core.plugins.registry import PluginRegistry
from synarius_core.model import (
    BaseObject,
    BasicOperator,
    BasicOperatorType,
    ComplexInstance,
    Connector,
    DataViewer,
    DuplicateIdError,
    ElementaryInstance,
    LocatableInstance,
    Model,
    Size2D,
    Variable,
    VariableMappingEntry,
    elementary_fmu_block,
    pin_map_from_library_ports,
)
from synarius_core.model.attribute_path import split_attribute_path
from synarius_core.model.connector_routing import bends_absolute_to_relative
from synarius_core.model.diagram_geometry import instance_source_pin_diagram_xy
from synarius_core.dataflow_sim.stimulation import STIMULATION_DISPLAY_KEYS, ensure_variable_stimulation_schema
from synarius_core.fmu.bind import FmuBindError, bind_elementary_from_fmu_path, bind_fmu_inspection_to_elementary
from synarius_core.fmu.inspection import FmuInspectError, inspect_fmu_path
from synarius_core.library.fmu_descriptor import default_fmu_library_type_key
from synarius_core.plugins.element_type_registry import ElementTypeRegistry
from synarius_core.plugins.element_types import (
    NEW_CONTEXT_OPTION_EXPLICIT_ID,
    InspectContext,
    NewContext,
    SyncContext,
)
from synarius_core.parameters.ndarray_format import format_ndarray_summary
from synarius_core.parameters.repository import ParameterRecord

from .command_undo import CommandUndoManager, UndoRedoPair
from .errors import CommandError
from .parse_helpers import (
    get_target_attr,
    optional_float_kw,
    parse_bool,
    parse_fmu_extra_meta_kw,
    parse_fmu_ports_kw,
    parse_fmu_variables_kw,
    parse_kw_pairs,
    parse_value,
    resolve_path_segment,
    set_target_attr,
    try_resolve_global_object_ref,
)


class SynariusController:
    """Text-command controller implementing core protocol commands."""

    _COMMAND_HANDLERS: ClassVar[Map[str, Callable[[SynariusController, list[str]], str | None]]]

    def __init__(
        self,
        model: Model | None = None,
        *,
        library_catalog: LibraryCatalog | None = None,
        plugin_registry: PluginRegistry | None = None,
        element_type_registry: ElementTypeRegistry | None = None,
        use_element_type_handlers: bool = True,
        max_undo_depth: int = 100,
        record_undo: bool = True,
    ) -> None:
        self.model = model or Model.new("main")
        self.library_catalog = library_catalog if library_catalog is not None else LibraryCatalog.load_default()
        self.plugin_registry = plugin_registry if plugin_registry is not None else PluginRegistry.load_default()
        self.element_type_registry = (
            element_type_registry if element_type_registry is not None else ElementTypeRegistry()
        )
        self.use_element_type_handlers = bool(use_element_type_handlers)
        self._undo_state = CommandUndoManager(max_undo_depth, recording=record_undo)
        self.max_undo_depth = self._undo_state.max_undo_depth
        self.current: Any = self.model.root
        self.selection: list[Any] = []
        self.alias_roots: dict[str, Any] = {
            "@main": self.model.root,
            "@objects": self.model.root,
            "@controller": self.model.root,
            "@latent": self.model.root,
            "@signals": self.model.root,
            "@libraries": self.library_catalog.root,
        }
        self.refresh_element_type_handlers()
        #: Set when ``load <script>`` succeeds; used to resolve relative ``fmu.path`` during simulation.
        self.last_loaded_script_path: Path | None = None
        #: Optional GUI hooks for ``import -dcm=…`` (e.g. copied onto the transactional clone inside ``load``).
        self.dcm_import_progress_hook: Callable[[int, int], None] | None = None
        self.dcm_import_phase_hook: Callable[[str, int], None] | None = None
        self.dcm_import_cooperative_hook: Callable[[], None] | None = None
        #: Optional (idx 1-based, total) während ``cp @selection`` — z. B. GUI processEvents.
        self.cp_selection_progress_hook: Callable[[int, int], None] | None = None

    @property
    def _undo_stack(self) -> list[UndoRedoPair]:
        return self._undo_state.undo_stack

    @property
    def _redo_stack(self) -> list[UndoRedoPair]:
        return self._undo_state.redo_stack

    @property
    def _undo_recording_enabled(self) -> bool:
        return self._undo_state.recording_enabled

    def _rebind_model_root_aliases(self) -> None:
        """Point workspace aliases at ``self.model.root`` after the model instance was replaced (e.g. ``load``)."""
        root = self.model.root
        self.alias_roots["@main"] = root
        self.alias_roots["@objects"] = root
        self.alias_roots["@controller"] = root
        self.alias_roots["@latent"] = root
        self.alias_roots["@signals"] = root

    def refresh_element_type_handlers(self) -> None:
        """Reload ``type_key`` handlers from the plugin registry and rebuild ``@plugins`` / ``@types`` alias trees."""
        self.plugin_registry.register_element_handlers(self.element_type_registry)
        from synarius_core.plugins.ccp_alias_trees import build_plugins_nav_root, build_types_nav_root

        self.alias_roots["@plugins"] = build_plugins_nav_root(self.plugin_registry.loaded_plugins)
        self.alias_roots["@types"] = build_types_nav_root(self.element_type_registry)

    # ------------------------- Public API ------------------------------------

    def execute(self, line: str) -> str | None:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            return None

        tokens = shlex.split(raw)
        if not tokens:
            return None

        cmd = tokens[0]
        args = tokens[1:]

        if cmd == "undo":
            return self._cmd_undo(args)
        if cmd == "redo":
            return self._cmd_redo(args)
        if cmd == "load":
            out = self._dispatch_command(cmd, args)
            self._undo_state.clear()
            return out

        if cmd == "import":
            out = self._dispatch_command(cmd, args)
            self._undo_state.clear()
            return out

        if cmd == "write":
            return self._dispatch_command(cmd, args)

        if cmd == "cp":
            out = self._dispatch_command(cmd, args)
            return out

        if cmd == "new":
            out = self._dispatch_command(cmd, args)
            pair = self._undo_pair_after_new(raw, out)
            self._undo_state.record_pair(pair)
            return out

        if cmd == "select":
            old_refs = [o.hash_name for o in self.selection]
            out = self._dispatch_command(cmd, args)
            if self._undo_recording_enabled:
                new_refs = [o.hash_name for o in self.selection]
                undo_ln = "select " + " ".join(shlex.quote(r) for r in old_refs) if old_refs else "select"
                redo_ln = "select " + " ".join(shlex.quote(r) for r in new_refs) if new_refs else "select"
                self._undo_state.record_pair(([undo_ln], [redo_ln]))
            return out

        if cmd == "inspect":
            return self._cmd_inspect(args)
        if cmd == "sync":
            return self._cmd_sync(args)
        if cmd == "fmu":
            return self._cmd_fmu(args)

        pair = self._try_build_undo_pair(cmd, args, raw)
        out = self._dispatch_command(cmd, args)
        self._undo_state.record_pair(pair)
        return out

    def _dispatch_command(self, cmd: str, args: list[str]) -> str | None:
        handler = self._COMMAND_HANDLERS.get(cmd)
        if handler is None:
            raise CommandError(f"Unknown command '{cmd}'.")
        return handler(self, args)

    def _cmd_undo(self, args: list[str]) -> str:
        n = int(args[0]) if args else 1
        if n < 1:
            raise CommandError("undo requires a positive step count.")
        steps = 0
        for _ in range(n):
            pair = self._undo_state.prepare_undo()
            if pair is None:
                break
            undo_cmds, _redo_cmds = pair

            def _run() -> None:
                for ln in undo_cmds:
                    self.execute(ln)

            self._undo_state.run_without_recording(_run)
            self._undo_state.complete_undo(pair)
            steps += 1
        return str(steps)

    def _cmd_redo(self, args: list[str]) -> str:
        n = int(args[0]) if args else 1
        if n < 1:
            raise CommandError("redo requires a positive step count.")
        steps = 0
        for _ in range(n):
            pair = self._undo_state.prepare_redo()
            if pair is None:
                break
            undo_cmds, redo_cmds = pair

            def _run() -> None:
                for ln in redo_cmds:
                    self.execute(ln)

            self._undo_state.run_without_recording(_run)
            self._undo_state.complete_redo(undo_cmds, redo_cmds)
            steps += 1
        return str(steps)

    def _container_path_for_mv(self, c: ComplexInstance) -> str:
        if c is self.model.root:
            return "@main"
        parts: list[str] = []
        n: BaseObject | None = c
        while n is not None and n is not self.model.root:
            parts.append(n.hash_name)
            n = n.parent
        parts.reverse()
        return "/" + "/".join(parts)

    def _format_cli_value(self, value: Any) -> str:
        if isinstance(value, datetime):
            return shlex.quote(value.isoformat(sep=" ", timespec="seconds"))
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            return repr(value)
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return shlex.quote(value)
        if isinstance(value, list):
            return repr(value)
        return shlex.quote(repr(value))

    def _try_build_undo_pair(self, cmd: str, args: list[str], raw: str) -> UndoRedoPair | None:
        if not self._undo_recording_enabled:
            return None
        if cmd == "set":
            return self._undo_pair_set(args, raw)
        if cmd == "mv":
            return self._undo_pair_mv(args)
        if cmd == "del":
            return self._undo_pair_before_del(args)
        return None

    def _undo_pair_mv(self, args: list[str]) -> UndoRedoPair | None:
        if len(args) != 2:
            return None
        obj = self._resolve_ref(args[0])
        dest = self._resolve_path(args[1])
        if not isinstance(dest, ComplexInstance):
            return None
        op = obj.parent
        if not isinstance(op, ComplexInstance):
            return None
        h = obj.hash_name
        old_p = self._container_path_for_mv(op)
        new_p = self._container_path_for_mv(dest)
        undo = [f"mv {shlex.quote(h)} {shlex.quote(old_p)}"]
        redo = [f"mv {shlex.quote(h)} {shlex.quote(new_p)}"]
        return (undo, redo)

    def _undo_pair_before_del_resolve_targets(self, args: list[str]) -> list[Any] | None:
        if args and args[0] == "@selected":
            if len(args) != 1:
                return None
            return self._ordered_selection_for_delete()
        return [self._resolve_ref(r) for r in args]

    def _undo_pair_before_del_rejects_parameter_data_sets(self, objs: list[Any]) -> bool:
        for o in objs:
            if isinstance(o, ComplexInstance) and o.id is not None:
                try:
                    if str(o.get("type")) == "MODEL.PARAMETER_DATA_SET":
                        return True
                except KeyError:
                    pass
        return False

    def _undo_pair_before_del_build_plans(self, objs: list[Any]) -> list[tuple[str, str]]:
        plans: list[tuple[str, str]] = []
        for obj in objs:
            if obj.parent is None or not isinstance(obj.parent, ComplexInstance):
                continue
            plans.append((obj.hash_name, self._container_path_for_mv(obj.parent)))
        return plans

    def _undo_pair_before_del_undo_redo_cmds(
        self, trash_p: str, plans: list[tuple[str, str]]
    ) -> UndoRedoPair:
        undo_cmds = [f"mv {shlex.quote(h)} {shlex.quote(p)}" for h, p in reversed(plans)]
        redo_cmds = [f"mv {shlex.quote(h)} {shlex.quote(trash_p)}" for h, _p in plans]
        return (undo_cmds, redo_cmds)

    def _undo_pair_before_del_trash_flags_ok(self, objs: list[Any]) -> bool:
        trash_flags = [self.model.is_in_trash_subtree(o) for o in objs]
        if any(trash_flags) and not all(trash_flags):
            raise CommandError("del cannot combine objects inside trash with live objects in one command.")
        if all(trash_flags):
            return False
        return True

    def _undo_pair_before_del(self, args: list[str]) -> UndoRedoPair | None:
        trash = self.model.get_trash_folder()
        trash_p = self._container_path_for_mv(trash)

        objs = self._undo_pair_before_del_resolve_targets(args)
        if objs is None:
            return None
        if not objs:
            return None
        if self._undo_pair_before_del_rejects_parameter_data_sets(objs):
            return None
        if not self._undo_pair_before_del_trash_flags_ok(objs):
            return None

        plans = self._undo_pair_before_del_build_plans(objs)
        if not plans:
            return None
        return self._undo_pair_before_del_undo_redo_cmds(trash_p, plans)

    def _undo_pair_after_new(self, raw_line: str, created_line: str | None) -> UndoRedoPair | None:
        if not self._undo_recording_enabled or not created_line:
            return None
        h = created_line.strip()
        if not h:
            return None
        try:
            obj = self._resolve_ref(h)
        except CommandError:
            return None
        parent = obj.parent
        if not isinstance(parent, ComplexInstance):
            return None
        trash = self.model.get_trash_folder()
        trash_p = self._container_path_for_mv(trash)
        back_p = self._container_path_for_mv(parent)
        undo = [f"mv {shlex.quote(h)} {shlex.quote(trash_p)}"]
        redo = [f"mv {shlex.quote(h)} {shlex.quote(back_p)}"]
        return (undo, redo)

    def _undo_pair_set_selection_delta_position(self, items: list[Any], redo: list[str]) -> UndoRedoPair | None:
        undo_cmds: list[str] = []
        for item in items:
            if not isinstance(item, LocatableInstance):
                continue
            ox = item.position.x
            oy = item.position.y
            hr = item.hash_name
            undo_cmds.append(f"set {shlex.quote(hr)}.x {self._format_cli_value(ox)}")
            undo_cmds.append(f"set {shlex.quote(hr)}.y {self._format_cli_value(oy)}")
        if not undo_cmds:
            return None
        return (undo_cmds, redo)

    def _undo_pair_set_selection_delta_scalar(
        self, items: list[Any], attr: str, tail: list[str], redo: list[str]
    ) -> UndoRedoPair | None:
        if len(tail) < 1:
            return None
        delta_val = parse_value(" ".join(tail))
        if not isinstance(delta_val, (int, float)):
            return None
        undo_cmds: list[str] = []
        for item in items:
            try:
                cur = get_target_attr(item, attr)
            except CommandError:
                continue
            if not isinstance(cur, (int, float)):
                continue
            prev = float(cur) - float(delta_val)
            undo_cmds.append(f"set {shlex.quote(item.hash_name)}.{attr} {self._format_cli_value(prev)}")
        if not undo_cmds:
            return None
        return (undo_cmds, redo)

    def _undo_pair_set_p_selection(self, args: list[str], raw: str) -> UndoRedoPair | None:
        redo = [raw]
        rest = args[2:]
        attr = rest[0]
        tail = rest[1:]
        items = list(self.selection)
        if not items:
            return None
        if attr == "position" and len(tail) >= 2:
            _ = float(tail[0]), float(tail[1])
            return self._undo_pair_set_selection_delta_position(items, redo)
        return self._undo_pair_set_selection_delta_scalar(items, attr, tail, redo)

    def _undo_pair_set_at_selection(self, args: list[str], raw: str) -> UndoRedoPair | None:
        redo = [raw]
        rest = args[1:]
        if len(rest) < 2:
            return None
        attr = rest[0]
        _ = parse_value(" ".join(rest[1:]))
        undo_cmds: list[str] = []
        for item in self.selection:
            try:
                old = get_target_attr(item, attr)
            except CommandError:
                continue
            undo_cmds.append(f"set {shlex.quote(item.hash_name)}.{attr} {self._format_cli_value(old)}")
        if not undo_cmds:
            return None
        return (undo_cmds, redo)

    def _undo_pair_set_dotted_or_current(self, args: list[str], raw: str) -> UndoRedoPair | None:
        redo = [raw]
        target_expr = args[0]
        _ = parse_value(" ".join(args[1:]))
        if "." in target_expr:
            path, attr = self._cli_ref_and_attrpath(target_expr)
            target = self._resolve_ref(path)
            try:
                old = get_target_attr(target, attr)
            except CommandError:
                return None
            undo = [f"set {target_expr} {self._format_cli_value(old)}"]
            return (undo, redo)
        try:
            old = get_target_attr(self.current, target_expr)
        except CommandError:
            return None
        undo = [f"set {target_expr} {self._format_cli_value(old)}"]
        return (undo, redo)

    def _undo_pair_set_dispatch_form(self, args: list[str], raw: str) -> UndoRedoPair | None:
        if args[0] == "-p" and len(args) >= 3 and args[1] == "@selection":
            return self._undo_pair_set_p_selection(args, raw)
        if args[0] == "@selection":
            return self._undo_pair_set_at_selection(args, raw)
        return self._undo_pair_set_dotted_or_current(args, raw)

    def _undo_pair_set(self, args: list[str], raw: str) -> UndoRedoPair | None:
        if len(args) < 2:
            return None
        return self._undo_pair_set_dispatch_form(args, raw)

    def _cmd_mv(self, args: list[str]) -> str:
        if len(args) != 2:
            raise CommandError("mv requires exactly <objectRef> <destContainerPath>.")
        obj = self._resolve_ref(args[0])
        dest = self._resolve_path(args[1])
        if not isinstance(dest, ComplexInstance):
            raise CommandError("mv destination must resolve to a container (ComplexInstance).")
        if obj is self.model.root:
            raise CommandError("Cannot move the model root.")
        if obj is self.model.get_trash_folder():
            raise CommandError("Cannot move the trash folder.")
        if not isinstance(obj, BaseObject):
            raise CommandError("mv source must be a model object.")
        self.model.reparent(obj, dest)
        return ""

    def execute_script(self, script_path: str | Path, *, command_trace: list[str] | None = None) -> list[str]:
        path = Path(script_path).expanduser().resolve()
        if not path.exists():
            raise CommandError(f"Script not found: {path}")
        # Damit ``import -dcm=… <relativerPfad>`` während dieses Skripts auflösbar ist (z. B. bei ``load``).
        self.last_loaded_script_path = path

        outputs: list[str] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if command_trace is not None:
                prompt = str(self.current.get("prompt_path")) if self.current is not None else "<none>"
                command_trace.append(f"  {prompt}> {stripped}")
            try:
                result = self.execute(stripped)
            except Exception as exc:
                raise CommandError(f"Script error at line {line_no}: {stripped} -> {exc}") from exc
            if result is not None:
                outputs.append(result)
        return outputs

    # ------------------------ Command handlers --------------------------------

    def _cmd_ls(self, args: list[str]) -> str:
        """List child names under the current container. *args* reserved for future options or path."""
        _ = args
        children = getattr(self.current, "children", None)
        if not children:
            return ""
        lines: list[str] = []
        for child in children:
            lines.append(str(get_target_attr(child, "name")))
        return "\n".join(lines)

    def _cmd_lsattr(self, args: list[str]) -> str:
        long_mode = False
        context = self.current

        for token in args:
            if token == "-l":
                long_mode = True
                continue
            if context is not self.current:
                raise CommandError("lsattr accepts at most one context argument.")
            resolved = self._resolve_path(token)
            if not hasattr(resolved, "attribute_dict"):
                raise CommandError("lsattr context must resolve to an object with attributes.")
            context = resolved

        rows2 = self._build_lsattr_rows(context)
        return self._format_lsattr_rows(context, rows2, long_mode=long_mode)

    def _flatten_mapping_for_lsattr(self, prefix: str, d: dict[str, Any]) -> list[tuple[str, Any]]:
        out: list[tuple[str, Any]] = []
        for k in sorted(d.keys()):
            v = d[k]
            path = f"{prefix}.{k}"
            if isinstance(v, dict):
                out.extend(self._flatten_mapping_for_lsattr(path, v))
            else:
                out.append((path, v))
        return out

    def _build_lsattr_rows(self, context: Any) -> list[tuple[str, Any]]:
        rows: list[tuple[str, Any]] = []
        # Gap only between flattened dict sub-rows when the top prefix changes (e.g. fmu.* vs pin.*).
        # Scalar attrs use the whole key as "first segment", so comparing groups would insert a blank
        # line between every row — wrong for normal lsattr output.
        prev_flat_group: str | None = None
        for key in sorted(context.attribute_dict.keys()):
            raw_val = context.attribute_dict.stored_value(key)
            if isinstance(raw_val, dict) and not context.attribute_dict.virtual(key):
                flat = self._flatten_mapping_for_lsattr(key, raw_val)
                for fk, fv in flat:
                    g = fk.split(".", 1)[0]
                    if prev_flat_group is not None and g != prev_flat_group:
                        rows.append(("__gap__", None))
                    prev_flat_group = g
                    rows.append((fk, fv))
                continue
            rows.append((key, context.attribute_dict[key]))
        return rows

    def _lsattr_meta_for_key(self, context: Any, flat_key: str) -> tuple[bool, bool, bool]:
        root = flat_key.split(".", 1)[0]
        return (
            context.attribute_dict.virtual(root),
            context.attribute_dict.exposed(root),
            context.attribute_dict.writable(root),
        )

    def _merge_lsattr_gap_row(self, *, long_mode: bool) -> tuple[str, ...]:
        if long_mode:
            return (" ", " ", " ", " ", " ")
        return (" ", " ")

    def _merge_lsattr_value_row(self, context: Any, key: str, value: Any, *, long_mode: bool) -> tuple[str, ...]:
        val = self._format_value(value)
        if long_mode:
            virt, exp, wr = self._lsattr_meta_for_key(context, key)
            return (
                key,
                val,
                "true" if virt else "false",
                "true" if exp else "false",
                "true" if wr else "false",
            )
        return (key, val)

    def _merge_lsattr_cells(self, context: Any, rows: list[tuple[str, Any]], *, long_mode: bool) -> list[tuple[str, ...]]:
        rows_out_merged: list[tuple[str, ...]] = []
        for key, value in rows:
            if key == "__gap__":
                rows_out_merged.append(self._merge_lsattr_gap_row(long_mode=long_mode))
                continue
            rows_out_merged.append(self._merge_lsattr_value_row(context, key, value, long_mode=long_mode))
        return rows_out_merged

    @staticmethod
    def _format_aligned_table_row(widths: list[int], cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    def _format_aligned_table(self, headers: tuple[str, ...], rows_out_merged: list[tuple[str, ...]]) -> str:
        widths = [len(h) for h in headers]
        for row in rows_out_merged:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        output = [self._format_aligned_table_row(widths, headers)]
        output.extend(self._format_aligned_table_row(widths, row) for row in rows_out_merged)
        return "\n".join(output)

    def _format_lsattr_rows(self, context: Any, rows: list[tuple[str, Any]], *, long_mode: bool) -> str:
        merged = self._merge_lsattr_cells(context, rows, long_mode=long_mode)
        headers: tuple[str, ...] = (
            ("NAME", "VALUE", "VIRTUAL", "EXPOSED", "WRITABLE")
            if long_mode
            else ("NAME", "VALUE")
        )
        return self._format_aligned_table(headers, merged)

    def _cli_ref_and_attrpath(self, target_expr: str) -> tuple[str, str]:
        parts = split_attribute_path(target_expr.strip())
        if len(parts) < 2:
            raise CommandError(f"Expected <objectRef>.<attr.path>, got {target_expr!r}.")
        ref = parts[0]
        attr = ".".join(parts[1:])
        return ref, attr

    def _format_value(self, value: Any) -> str:
        if isinstance(value, datetime):
            # Use an explicit ISO representation with timezone if present.
            return value.isoformat(sep=" ", timespec="seconds")
        return repr(value)

    def _cmd_cd(self, args: list[str]) -> str:
        if len(args) != 1:
            raise CommandError("cd requires exactly one path argument.")
        target = self._resolve_path(args[0])
        self.current = target
        return str(self.current.get("prompt_path"))

    def _library_pin_seed_for_type_key(self, type_key: str) -> dict[str, dict[str, Any]] | None:
        if "." not in type_key:
            return None
        lib_name, elem_id = type_key.split(".", 1)
        for lib in self.library_catalog.libraries:
            if lib.name != lib_name:
                continue
            for elem in lib.elements:
                if elem.element_id == elem_id:
                    return pin_map_from_library_ports(elem.ports)
        return None

    def _resolve_fmu_file_for_inspect(self, raw_path: str) -> Path:
        """Resolve a ``.fmu`` path for reading; same script-relative rule as ``import -dcm=…`` / ``execute_script``."""
        raw = str(raw_path).strip()
        if not raw:
            raise CommandError("fmu_path is empty.")
        p = Path(raw).expanduser()
        if p.is_file():
            return p.resolve()
        base = self.last_loaded_script_path
        if base is not None:
            alt = (base.parent / raw).expanduser()
            try:
                alt_r = alt.resolve()
            except OSError:
                alt_r = alt
            if alt_r.is_file():
                return alt_r
        raise CommandError(f"FMU file not found: {raw_path}")

    @staticmethod
    def _fmu_kwargs_need_autofill_from_archive(
        ports_kw: list[dict[str, Any]] | None,
        vars_kw: list[dict[str, Any]] | None,
    ) -> bool:
        ports_empty = ports_kw is None or len(ports_kw) == 0
        vars_empty = vars_kw is None or len(vars_kw) == 0
        return ports_empty and vars_empty

    def _autofill_fmu_elementary_from_path(
        self, el: ElementaryInstance, raw_fmu_path: str, *, type_key: str
    ) -> None:
        resolved = self._resolve_fmu_file_for_inspect(raw_fmu_path)
        lib = self._library_pin_seed_for_type_key(type_key)
        try:
            data = inspect_fmu_path(str(resolved))
            bind_fmu_inspection_to_elementary(
                el,
                data,
                library_pin_seed=lib,
                path_override=None,
            )
        except FmuInspectError as exc:
            raise CommandError(str(exc)) from exc
        except FmuBindError as exc:
            raise CommandError(str(exc)) from exc

    def _parse_placed_elementary(
        self, positional: list[str], *, label: str
    ) -> tuple[str, tuple[float, float], Size2D]:
        if not positional:
            raise CommandError(f"{label} requires <name>.")
        name = positional[0]
        pos: tuple[float, float] = (0.0, 0.0)
        size = Size2D(1.0, 1.0)
        if len(positional) == 1:
            pass
        elif len(positional) == 4:
            pos = (float(positional[1]), float(positional[2]))
            s = float(positional[3])
            size = Size2D(s, s)
        else:
            raise CommandError(f"{label} expects <name> or <name> <x> <y> <size>.")
        return name, pos, size

    def _pop_optional_uuid_kw(self, kwargs: dict[str, str], key: str = "id") -> UUID | None:
        """Consume ``id=<uuid>`` style kwargs; return ``None`` if absent or empty."""
        if key not in kwargs:
            return None
        raw = kwargs.pop(key)
        if raw is None or str(raw).strip() == "":
            return None
        s = str(raw).strip()
        try:
            return UUID(s)
        except ValueError:
            pass
        hx = s.replace("-", "")
        if len(hx) == 32:
            try:
                return UUID(hex=hx)
            except ValueError:
                pass
        raise CommandError(f"Invalid UUID for {key}: {raw!r}")

    def _pop_optional_dataviewer_id_kw(self, kwargs: dict[str, str]) -> int | None:
        """Consume ``dataviewer_id=<int>`` for ``new DataViewer`` replay."""
        if "dataviewer_id" not in kwargs:
            return None
        raw = kwargs.pop("dataviewer_id")
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return int(str(raw).strip(), 10)
        except ValueError as exc:
            raise CommandError(f"dataviewer_id must be an integer: {raw!r}") from exc

    def _cmd_new_variable(self, positional: list[str], kwargs: dict[str, str], explicit_id: UUID | None) -> Variable:
        if not positional:
            raise CommandError("new Variable requires <name>.")
        name = positional[0]
        pos: tuple[float, float] = (0.0, 0.0)
        size = Size2D(1.0, 1.0)
        if len(positional) == 1:
            pass
        elif len(positional) == 4:
            pos = (float(positional[1]), float(positional[2]))
            s = float(positional[3])
            size = Size2D(s, s)
        else:
            raise CommandError("new Variable expects <name> or <name> <x> <y> <size>.")
        return Variable(
            name=name,
            type_key=kwargs.get("type_key", "Variable"),
            value=kwargs.get("value"),
            unit=kwargs.get("unit", ""),
            position=pos,
            size=size,
            obj_id=explicit_id,
        )

    def _cmd_new_basic_operator(self, positional: list[str], kwargs: dict[str, str], explicit_id: UUID | None) -> BasicOperator:
        if not positional:
            raise CommandError("new BasicOperator requires <opSymbol>.")
        symbol = positional[0]
        mapping = {
            "+": BasicOperatorType.PLUS,
            "-": BasicOperatorType.MINUS,
            "*": BasicOperatorType.MULTIPLY,
            "/": BasicOperatorType.DIVIDE,
        }
        if symbol not in mapping:
            raise CommandError("BasicOperator opSymbol must be one of +, -, *, /.")
        pos_bo: tuple[float, float] = (0.0, 0.0)
        size_bo = Size2D(1.0, 1.0)
        if len(positional) == 1:
            pass
        elif len(positional) == 3:
            pos_bo = (float(positional[1]), float(positional[2]))
        elif len(positional) == 4:
            pos_bo = (float(positional[1]), float(positional[2]))
            s_bo = float(positional[3])
            size_bo = Size2D(s_bo, s_bo)
        else:
            raise CommandError(
                "new BasicOperator expects <opSymbol> or <opSymbol> <x> <y> or <opSymbol> <x> <y> <size>."
            )
        return BasicOperator(
            name=kwargs.get("name", f"op_{symbol}"),
            type_key=kwargs.get("type_key", "BasicOperator"),
            operation=mapping[symbol],
            position=pos_bo,
            size=size_bo,
            obj_id=explicit_id,
        )

    def _cmd_new_dataviewer(self, positional: list[str], kwargs: dict[str, str], explicit_id: UUID | None) -> DataViewer:
        pos_dv: tuple[float, float] = self.model.next_dataviewer_default_position()
        if len(positional) >= 2:
            pos_dv = (float(positional[0]), float(positional[1]))
        elif len(positional) == 1:
            raise CommandError("new DataViewer expects no args or <x> <y>.")
        opt_dv_id = self._pop_optional_dataviewer_id_kw(kwargs)
        vid = opt_dv_id if opt_dv_id is not None else self.model.allocate_dataviewer_id()
        return DataViewer(
            viewer_id=vid,
            position=pos_dv,
            size=Size2D(1.0, 1.0),
            obj_id=explicit_id,
        )

    def _cmd_new_connector(self, positional: list[str], kwargs: dict[str, str], explicit_id: UUID | None) -> Connector:
        if len(positional) < 2:
            raise CommandError("new Connector requires <fromRef> <toRef>.")
        src = self._resolve_ref(positional[0])
        dst = self._resolve_ref(positional[1])
        ob_raw = kwargs.get("orthogonal_bends")
        ob_list: list[float] | None = None
        if ob_raw is not None and str(ob_raw).strip() != "":
            parts = [p.strip() for p in str(ob_raw).replace(";", ",").split(",") if p.strip()]
            try:
                ob_list = [float(p) for p in parts]
            except ValueError as exc:
                raise CommandError(f"orthogonal_bends must be comma-separated numbers: {exc}") from exc
        sp = str(kwargs.get("source_pin", "out"))
        if ob_list is not None:
            xy = instance_source_pin_diagram_xy(src, sp)
            if xy is not None:
                sx, sy = xy
                ob_list = bends_absolute_to_relative(sx, sy, ob_list)
        return Connector(
            name=kwargs.get("name", "connector"),
            source_instance_id=src.id,  # type: ignore[arg-type]
            source_pin=sp,
            target_instance_id=dst.id,  # type: ignore[arg-type]
            target_pin=kwargs.get("target_pin", "in"),
            directed=parse_bool(kwargs.get("directed", "true")),
            orthogonal_bends=ob_list,
            obj_id=explicit_id,
        )

    def _cmd_new_elementary(self, positional: list[str], kwargs: dict[str, str], explicit_id: UUID | None) -> ElementaryInstance:
        el_name, pos_el, size_el = self._parse_placed_elementary(positional, label="new Elementary")
        tk = kwargs.get("type_key")
        if not tk or str(tk).strip() == "":
            raise CommandError("new Elementary requires type_key=…")
        tk_s = str(tk)
        lib_pins = self._library_pin_seed_for_type_key(tk_s)
        pin_seed = lib_pins if lib_pins else None
        fmu_path_kw = kwargs.get("fmu_path")
        if fmu_path_kw and str(fmu_path_kw).strip() != "":
            ports_kw = parse_fmu_ports_kw(kwargs)
            vars_kw = parse_fmu_variables_kw(kwargs)
            extra_kw = parse_fmu_extra_meta_kw(kwargs)
            el = elementary_fmu_block(
                name=el_name,
                type_key=tk_s,
                library_pin_seed=pin_seed,
                fmu_path=str(fmu_path_kw),
                fmi_version=str(kwargs.get("fmi_version", "2.0")),
                fmu_type=str(kwargs.get("fmu_type", "CoSimulation")),
                guid=str(kwargs.get("guid", "")),
                model_identifier=str(kwargs.get("model_identifier", "")),
                fmu_description=str(kwargs.get("fmu_description", "")),
                fmu_author=str(kwargs.get("fmu_author", "")),
                fmu_model_version=str(kwargs.get("fmu_model_version", "")),
                fmu_generation_tool=str(kwargs.get("fmu_generation_tool", "")),
                fmu_generation_date=str(kwargs.get("fmu_generation_date", "")),
                step_size_hint=optional_float_kw(kwargs, "step_size_hint"),
                tolerance=optional_float_kw(kwargs, "tolerance"),
                start_time=optional_float_kw(kwargs, "start_time"),
                stop_time=optional_float_kw(kwargs, "stop_time"),
                fmu_ports=ports_kw,
                fmu_variables=vars_kw,
                fmu_extra_meta=extra_kw,
                position=pos_el,
                size=size_el,
                obj_id=explicit_id,
            )
            if self._fmu_kwargs_need_autofill_from_archive(ports_kw, vars_kw):
                self._autofill_fmu_elementary_from_path(el, str(fmu_path_kw), type_key=tk_s)
            return el
        return ElementaryInstance(
            name=el_name,
            type_key=tk_s,
            pin=pin_seed,
            position=pos_el,
            size=size_el,
            obj_id=explicit_id,
        )

    def _cmd_new_fmu_instance(self, positional: list[str], kwargs: dict[str, str], explicit_id: UUID | None) -> ElementaryInstance:
        fm_name, pos_fm, size_fm = self._parse_placed_elementary(positional, label="new FmuInstance")
        fmu_path_kw = kwargs.get("fmu_path")
        if not fmu_path_kw or str(fmu_path_kw).strip() == "":
            raise CommandError("new FmuInstance requires fmu_path=…")
        tk_s = str(kwargs.get("type_key", default_fmu_library_type_key()))
        lib_pins = self._library_pin_seed_for_type_key(tk_s)
        ports_kw = parse_fmu_ports_kw(kwargs)
        vars_kw = parse_fmu_variables_kw(kwargs)
        extra_kw = parse_fmu_extra_meta_kw(kwargs)
        el = elementary_fmu_block(
            name=fm_name,
            type_key=tk_s,
            library_pin_seed=lib_pins if lib_pins else None,
            fmu_path=str(fmu_path_kw),
            fmi_version=str(kwargs.get("fmi_version", "2.0")),
            fmu_type=str(kwargs.get("fmu_type", "CoSimulation")),
            guid=str(kwargs.get("guid", "")),
            model_identifier=str(kwargs.get("model_identifier", "")),
            fmu_description=str(kwargs.get("fmu_description", "")),
            fmu_author=str(kwargs.get("fmu_author", "")),
            fmu_model_version=str(kwargs.get("fmu_model_version", "")),
            fmu_generation_tool=str(kwargs.get("fmu_generation_tool", "")),
            fmu_generation_date=str(kwargs.get("fmu_generation_date", "")),
            step_size_hint=optional_float_kw(kwargs, "step_size_hint"),
            tolerance=optional_float_kw(kwargs, "tolerance"),
            start_time=optional_float_kw(kwargs, "start_time"),
            stop_time=optional_float_kw(kwargs, "stop_time"),
            fmu_ports=ports_kw,
            fmu_variables=vars_kw,
            fmu_extra_meta=extra_kw,
            position=pos_fm,
            size=size_fm,
            obj_id=explicit_id,
        )
        if self._fmu_kwargs_need_autofill_from_archive(ports_kw, vars_kw):
            self._autofill_fmu_elementary_from_path(el, str(fmu_path_kw), type_key=tk_s)
        return el

    def _cmd_new_data_set(self, positional: list[str], explicit_id: UUID | None) -> ComplexInstance:
        if not positional:
            raise CommandError("new DataSet requires <name>.")
        if self._node_model_type(self.current) != "MODEL.PARAMETER_DATA_SETS":
            raise CommandError("new DataSet is only allowed in parameters/data_sets.")
        obj = ComplexInstance(name=positional[0], obj_id=explicit_id)
        obj.attribute_dict["type"] = "MODEL.PARAMETER_DATA_SET"
        return obj

    def _cmd_new_data_container(self, positional: list[str], explicit_id: UUID | None) -> ComplexInstance:
        if not positional:
            raise CommandError("new DataContainer requires <name>.")
        if self._node_model_type(self.current) != "MODEL.PARAMETER_DATA_SET":
            raise CommandError("new DataContainer is only allowed directly under a DataSet.")
        obj = ComplexInstance(name=positional[0], obj_id=explicit_id)
        obj.attribute_dict["type"] = "MODEL.PARAMETER_DATA_CONTAINER"
        return obj

    def _cmd_new_cal_param(self, positional: list[str], explicit_id: UUID | None) -> ComplexInstance:
        if not positional:
            raise CommandError("new CalParam requires <name>.")
        cur_t = self._node_model_type(self.current)
        if cur_t not in {"MODEL.PARAMETER_DATA_SET", "MODEL.PARAMETER_DATA_CONTAINER"}:
            raise CommandError("new CalParam is only allowed under a DataSet/DataContainer subtree.")
        obj = ComplexInstance(name=positional[0], obj_id=explicit_id)
        obj.attribute_dict["type"] = "MODEL.CAL_PARAM"
        return obj

    def _cmd_new_resolve_cal_param_data_set(self, kwargs: dict[str, str]) -> UUID | None:
        ds_id2: UUID | None = None
        ds_ref = kwargs.get("data_set")
        if ds_ref is not None and str(ds_ref).strip() != "":
            ds_obj = self._resolve_ref(str(ds_ref))
            did = getattr(ds_obj, "id", None)
            if not isinstance(ds_obj, ComplexInstance) or not isinstance(did, UUID):
                raise CommandError("data_set must resolve to an attached DataSet with UUID.")
            if self._node_model_type(ds_obj) != "MODEL.PARAMETER_DATA_SET":
                raise CommandError("data_set must reference a MODEL.PARAMETER_DATA_SET node.")
            ds_id2 = did
            cur_owner = self._ancestor_parameter_data_set(self.current)
            if cur_owner is not None and cur_owner.id is not None and cur_owner.id != ds_id2:
                raise CommandError("data_set=... must match the current parent DataSet subtree.")
        return ds_id2

    def _cmd_new_register_runtime(
        self,
        type_name: str,
        obj: BaseObject,
        kwargs: dict[str, str],
        *,
        ds_id2: UUID | None,
    ) -> None:
        if type_name == "DataSet":
            if "data_source" in kwargs:
                raise CommandError(
                    "new DataSet data_source=... is no longer supported. "
                    "Use source_path=... (and optional source_format/source_hash)."
                )
            self.model.parameter_runtime().register_data_set_node(
                obj,
                source_path=str(kwargs.get("source_path", "")),
                source_format=str(kwargs.get("source_format", "unknown")),
                source_hash=str(kwargs.get("source_hash", "")),
            )
        elif type_name == "DataContainer":
            self.model.parameter_runtime().register_data_container_node(obj)
        elif type_name == "CalParam":
            self.model.parameter_runtime().register_cal_param_node(
                obj,
                data_set_id=ds_id2,
                category=str(kwargs.get("category", "VALUE")),
            )

    def _cmd_new_instantiate(
        self,
        type_name: str,
        positional: list[str],
        kwargs: dict[str, str],
        explicit_id: UUID | None,
    ) -> BaseObject:
        if type_name == "Variable":
            return self._cmd_new_variable(positional, kwargs, explicit_id)
        if type_name == "BasicOperator":
            return self._cmd_new_basic_operator(positional, kwargs, explicit_id)
        if type_name == "DataViewer":
            return self._cmd_new_dataviewer(positional, kwargs, explicit_id)
        if type_name == "Connector":
            return self._cmd_new_connector(positional, kwargs, explicit_id)
        if type_name == "Elementary":
            return self._cmd_new_elementary(positional, kwargs, explicit_id)
        if type_name == "FmuInstance":
            return self._cmd_new_fmu_instance(positional, kwargs, explicit_id)
        if type_name == "DataSet":
            return self._cmd_new_data_set(positional, explicit_id)
        if type_name == "DataContainer":
            return self._cmd_new_data_container(positional, explicit_id)
        if type_name == "CalParam":
            return self._cmd_new_cal_param(positional, explicit_id)
        raise CommandError(f"Unsupported new type '{type_name}'.")

    def _cmd_new(self, args: list[str]) -> str:
        if not args:
            raise CommandError("new requires a type argument.")
        type_name = args[0]
        rest = args[1:]
        kwargs = parse_kw_pairs(rest)
        positional = [t for t in rest if "=" not in t]
        explicit_id = self._pop_optional_uuid_kw(kwargs, "id")

        if not isinstance(self.current, ComplexInstance):
            raise CommandError("new requires a model container as cwd (e.g. cd @main first; not under @libraries).")

        obj: BaseObject | None = None
        if self.use_element_type_handlers:
            h = self.element_type_registry.get(type_name)
            if h is not None:
                nc_opts: dict[str, Any] = {}
                if explicit_id is not None:
                    nc_opts[NEW_CONTEXT_OPTION_EXPLICIT_ID] = explicit_id
                nctx = NewContext(
                    controller=self,
                    model=self.model,
                    diagnostics=[],
                    options=nc_opts,
                )
                name_token = positional[0] if positional else ""
                obj = h.new(nctx, name_token, positional, kwargs)
        if obj is None:
            obj = self._cmd_new_instantiate(type_name, positional, kwargs, explicit_id)

        ds_id2: UUID | None = None
        if type_name == "CalParam":
            ds_id2 = self._cmd_new_resolve_cal_param_data_set(kwargs)

        try:
            self.model.attach(
                obj,
                parent=self.current,
                reserve_existing=(explicit_id is not None),
                remap_ids=False,
            )
        except DuplicateIdError as exc:
            raise CommandError(str(exc)) from exc
        try:
            self._cmd_new_register_runtime(type_name, obj, kwargs, ds_id2=ds_id2)
        except (ValueError, CommandError) as exc:
            if isinstance(obj, ComplexInstance) and obj.parent is not None and obj.id is not None:
                try:
                    self.model.delete(obj.parent, obj.id)
                except Exception:
                    pass
            raise CommandError(str(exc)) from exc
        return obj.hash_name

    def _cmd_select(self, args: list[str]) -> str:
        if not args:
            self.selection = []
            return ""
        if args[0] == "-m":
            tokens = args[1:]
            if not tokens:
                raise CommandError("select -m requires at least one reference.")
            resolved = [self._resolve_ref(token) for token in tokens]
            remove_keys: set[str] = set()
            for obj in resolved:
                oid = getattr(obj, "id", None)
                key = str(oid) if oid is not None else f"obj:{id(obj)}"
                remove_keys.add(key)
            kept: list[Any] = []
            for obj in self.selection:
                oid = getattr(obj, "id", None)
                key = str(oid) if oid is not None else f"obj:{id(obj)}"
                if key not in remove_keys:
                    kept.append(obj)
            self.selection = kept
            return ""
        append_mode = False
        tokens = list(args)
        if tokens and tokens[0] == "-p":
            append_mode = True
            tokens = tokens[1:]
            if not tokens:
                raise CommandError("select -p requires at least one reference.")
        resolved = [self._resolve_ref(token) for token in tokens]
        if not append_mode:
            self.selection = resolved
            return ""

        merged = list(self.selection)
        seen: set[str] = set()
        for obj in merged:
            oid = getattr(obj, "id", None)
            key = str(oid) if oid is not None else f"obj:{id(obj)}"
            seen.add(key)
        for obj in resolved:
            oid = getattr(obj, "id", None)
            key = str(oid) if oid is not None else f"obj:{id(obj)}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(obj)
        self.selection = merged
        return ""

    def _cmd_set(self, args: list[str]) -> str:
        if len(args) < 2:
            raise CommandError("set requires at least two arguments.")

        # Unix-style: options before operands — ``set -p @selection <attr> …``
        if args[0] == "-p":
            if len(args) < 3 or args[1] != "@selection":
                raise CommandError("set -p requires @selection as the next argument.")
            return self._cmd_set_selection(args[2:], delta_mode=True)

        if args[0] == "@selection":
            rest = args[1:]
            if rest and rest[0] == "-p":
                raise CommandError("Delta updates use: set -p @selection <attr> <value> (not set @selection -p …).")
            return self._cmd_set_selection(rest, delta_mode=False)

        target_expr = args[0]
        value = parse_value(" ".join(args[1:]))
        if "." in target_expr:
            path, attr = self._cli_ref_and_attrpath(target_expr)
            target = self._resolve_ref(path)
            set_target_attr(target, attr, value)
        else:
            set_target_attr(self.current, target_expr, value)
        return "ok"

    def _cmd_set_selection(self, args: list[str], *, delta_mode: bool) -> str:
        """``set @selection <attr> <value>`` or ``set -p @selection …`` (via ``delta_mode``)."""
        if len(args) < 2:
            raise CommandError(
                "set -p @selection requires <attr> <value>."
                if delta_mode
                else "set @selection requires <attr> <value>."
            )

        attr = args[0]
        tail = args[1:]

        if delta_mode:
            if attr == "position":
                if len(tail) < 2:
                    raise CommandError("set -p @selection position requires <dx> <dy>.")
                dx = float(tail[0])
                dy = float(tail[1])
                updated = 0
                for item in self.selection:
                    try:
                        self._apply_position_delta(item, dx, dy)
                        updated += 1
                    except CommandError:
                        continue
                return str(updated)

            delta_val = parse_value(" ".join(tail))
            if not isinstance(delta_val, (int, float)):
                raise CommandError("set -p @selection requires a numeric delta for this attribute.")
            updated = 0
            for item in self.selection:
                try:
                    self._apply_scalar_delta(item, attr, float(delta_val))
                    updated += 1
                except CommandError:
                    continue
            return str(updated)

        value = parse_value(" ".join(tail))
        for item in self.selection:
            set_target_attr(item, attr, value)
        return str(len(self.selection))

    def _apply_scalar_delta(self, obj: Any, attr: str, delta: float) -> None:
        cur = get_target_attr(obj, attr)
        if not isinstance(cur, (int, float)):
            raise CommandError(f"Attribute '{attr}' is not numeric; cannot apply delta.")
        set_target_attr(obj, attr, float(cur) + delta)

    def _apply_position_delta(self, obj: Any, dx: float, dy: float) -> None:
        if not isinstance(obj, LocatableInstance):
            raise CommandError("position delta requires a locatable object.")
        obj.set_xy((obj.position.x + dx, obj.position.y + dy))

    def _cmd_get(self, args: list[str]) -> str:
        if not args:
            raise CommandError("get requires at least one argument.")

        if args[0] == "@selection":
            if len(args) != 2:
                raise CommandError("get @selection requires exactly one attribute.")
            attr = args[1]
            return "\n".join(str(get_target_attr(item, attr)) for item in self.selection)

        target_expr = args[0]
        if "." in target_expr:
            path, attr = self._cli_ref_and_attrpath(target_expr)
            target = self._resolve_ref(path)
            return str(get_target_attr(target, attr))
        return str(get_target_attr(self.current, target_expr))

    def _node_model_type(self, obj: Any) -> str | None:
        if not isinstance(obj, BaseObject):
            return None
        try:
            t = obj.get("type")
        except Exception:
            return None
        return str(t) if t is not None else None

    def _ancestor_parameter_data_set(self, node: Any) -> ComplexInstance | None:
        cur = node if isinstance(node, ComplexInstance) else None
        while isinstance(cur, ComplexInstance):
            if self._node_model_type(cur) == "MODEL.PARAMETER_DATA_SET":
                return cur
            cur = cur.parent
        return None

    def _format_print_cal_param(self, rec: ParameterRecord) -> str:
        lines: list[str] = [
            f"Kenngröße: {rec.name}",
            f"Kategorie: {rec.category}",
            f"Parameter-ID: {rec.parameter_id}",
            f"Datensatz-ID: {rec.data_set_id}",
        ]
        ds_name = self.model.parameter_runtime().repo.get_dataset_name(rec.data_set_id)
        if ds_name:
            lines.append(f"Datensatz: {ds_name}")
        if rec.display_name:
            lines.append(f"Anzeigename: {rec.display_name}")
        if rec.comment:
            lines.append(f"Kommentar: {rec.comment}")
        if rec.unit:
            lines.append(f"Einheit: {rec.unit}")
        if rec.conversion_ref:
            lines.append(f"Umrechnung: {rec.conversion_ref}")
        if rec.source_identifier:
            lines.append(f"Quelle: {rec.source_identifier}")
        lines.append(f"Numerikformat: {rec.numeric_format}  Wertsemantik: {rec.value_semantics}")
        if rec.is_text:
            lines.append(f"Textwert: {rec.text_value!r}")
            return "\n".join(lines)
        lines.append(f"Werte: {format_ndarray_summary(rec.values)}")
        for i in range(rec.values.ndim):
            ax = rec.axes.get(i)
            an = rec.axis_names.get(i, "") or "?"
            au = rec.axis_units.get(i, "") or ""
            if ax is not None and ax.size:
                a0, a1 = float(ax[0]), float(ax[-1])
                lines.append(
                    f"Achse {i + 1} ({an}) [{au}]: Stützstellen={ax.size}  "
                    f"Bereich={a0:g} … {a1:g}"
                )
            else:
                lines.append(f"Achse {i + 1} ({an}) [{au}]: (keine Stützstellen)")
        return "\n".join(lines)

    def _format_print_dataset_node(self, obj: ComplexInstance) -> str:
        lines = [
            f"Datensatz: {obj.name}",
            "Typ: PARAMETER_DATA_SET",
            f"ID: {obj.id}",
        ]
        try:
            sp = obj.get("source_path")
            sf = obj.get("source_format")
            sh = obj.get("source_hash")
            if sp:
                lines.append(f"Quelldatei: {sp}")
            if sf:
                lines.append(f"Format: {sf}")
            if sh:
                lines.append(f"Hash: {sh}")
        except Exception:
            pass
        n_children = len(obj.children) if obj.children else 0
        lines.append(f"Direkte Kinder im Modell: {n_children}")
        return "\n".join(lines)

    def _format_print_data_container(self, obj: ComplexInstance) -> str:
        lines = [f"Datencontainer: {obj.name}", f"ID: {obj.id}"]
        try:
            ct = obj.get("container_type")
            lines.append(f"Container-Typ: {ct}")
        except Exception:
            pass
        n_children = len(obj.children) if obj.children else 0
        lines.append(f"Kinder: {n_children}")
        return "\n".join(lines)

    def _cmd_print_branch_model_root(self, ci: ComplexInstance, mt: str | None) -> str:
        lines = [
            f"Modellroot: {ci.name}",
            f"Kinder: {len(ci.children) if ci.children else 0}",
        ]
        if mt:
            lines.append(f"Typ: {mt}")
        return "\n".join(lines)

    def _cmd_print_branch_cal_param(self, ci: ComplexInstance) -> str:
        pid = getattr(ci, "id", None)
        if not isinstance(pid, UUID):
            raise CommandError("CalParam ohne gültige UUID.")
        try:
            rec = self.model.parameter_runtime().repo.get_record(pid)
        except ValueError as exc:
            raise CommandError(f"Kein Parameterdatensatz im Repository: {exc}") from exc
        return self._format_print_cal_param(rec)

    def _cmd_print_branch_parameter_data_sets(self, ci: ComplexInstance) -> str:
        n = len(ci.children) if ci.children else 0
        return f"Parameter-Datensätze (Ordner): {n} Einträge"

    def _cmd_print_branch_parameters_folder(self, ci: ComplexInstance) -> str:
        lines = ["Parameter-Bereich (Modell)"]
        try:
            adn = ci.get("active_dataset_name")
            if adn:
                lines.append(f"Aktiver Datensatz: {adn}")
        except Exception:
            pass
        try:
            order = ci.get("dataset_display_order")
            if order:
                lines.append(f"Spaltenreihenfolge (Vergleich): {order!r}")
        except Exception:
            pass
        try:
            tc = ci.get("target_column_data_set_id")
            if tc is not None and str(tc).strip() not in ("", "None"):
                lines.append(f"Zielspalte zeigt Datensatz-ID: {tc}")
        except Exception:
            pass
        lines.append(f"Direkte Kinder: {len(ci.children) if ci.children else 0}")
        return "\n".join(lines)

    def _cmd_print_branch_variable(self, v: Variable) -> str:
        ensure_variable_stimulation_schema(v)
        lines = [
            f"Variable: {v.name}",
            f"type_key: {v.type_key}",
            f"Wert: {self._format_value(v.value)}",
            f"Einheit: {v.unit!r}",
            f"Position: ({v.position.x:g}, {v.position.y:g})",
        ]
        for k in STIMULATION_DISPLAY_KEYS:
            try:
                lines.append(f"{k}: {self._format_value(v.get(k))}")
            except Exception:
                pass
        return "\n".join(lines)

    def _cmd_print_branch_basic_operator(self, bo: BasicOperator) -> str:
        return (
            f"BasicOperator: {bo.name}\n"
            f"Operation: {bo.operation.value}\n"
            f"type_key: {bo.type_key}"
        )

    def _cmd_print_branch_connector(self, cn: Connector) -> str:
        return (
            f"Connector: {cn.name}\n"
            f"Quelle: {cn.source_instance_id} pin={cn.source_pin!r}\n"
            f"Ziel: {cn.target_instance_id} pin={cn.target_pin!r}\n"
            f"directed: {cn.directed}"
        )

    def _cmd_print_branch_dataviewer(self, dv: DataViewer) -> str:
        try:
            vid = dv.get("dataviewer_id")
        except Exception:
            vid = "?"
        return f"DataViewer: {dv.name}  dataviewer_id={vid}"

    def _cmd_print_branch_elementary(self, el: ElementaryInstance) -> str:
        lines = [f"ElementaryInstance: {el.name}", f"type_key: {el.type_key}"]
        try:
            fp = el.get("fmu.path")
            if fp:
                lines.append(f"fmu.path: {fp}")
        except Exception:
            pass
        lines.append(f"Position: ({el.position.x:g}, {el.position.y:g})")
        return "\n".join(lines)

    def _cmd_print_branch_complex_generic(self, ci: ComplexInstance, mt: str | None) -> str:
        lines = [
            f"ComplexInstance: {ci.name}",
            f"ID: {ci.id}",
        ]
        if mt:
            lines.append(f"Typ: {mt}")
        lines.append(f"Kinder: {len(ci.children) if ci.children else 0}")
        return "\n".join(lines)

    def _cmd_print_branch_var_mapping(self, vm: VariableMappingEntry) -> str:
        lines = [f"VariableMappingEntry: {vm.name}"]
        try:
            ms = vm.get("mapped_signal")
            lines.append(f"zugeordnetes Signal: {self._format_value(ms)}")
        except Exception:
            pass
        return "\n".join(lines)

    def _cmd_print_branch_fallback(self, target: Any) -> str:
        name = getattr(target, "name", None)
        return f"{type(target).__name__}" + (f": {name}" if name else "")

    def _cmd_print(self, args: list[str]) -> str:
        if len(args) > 1:
            raise CommandError("print erwartet höchstens ein Ziel (Referenz oder Kontext).")
        if args:
            target: Any = self._resolve_ref(args[0])
        else:
            target = self.current

        mt = self._node_model_type(target)

        def branch_model_root(ci: ComplexInstance) -> str:
            return self._cmd_print_branch_model_root(ci, mt)

        def branch_cal_param(ci: ComplexInstance) -> str:
            return self._cmd_print_branch_cal_param(ci)

        def branch_parameter_data_sets(ci: ComplexInstance) -> str:
            return self._cmd_print_branch_parameter_data_sets(ci)

        def branch_parameters_folder(ci: ComplexInstance) -> str:
            return self._cmd_print_branch_parameters_folder(ci)

        def branch_variable(v: Variable) -> str:
            return self._cmd_print_branch_variable(v)

        def branch_basic_operator(bo: BasicOperator) -> str:
            return self._cmd_print_branch_basic_operator(bo)

        def branch_connector(cn: Connector) -> str:
            return self._cmd_print_branch_connector(cn)

        def branch_dataviewer(dv: DataViewer) -> str:
            return self._cmd_print_branch_dataviewer(dv)

        def branch_elementary(el: ElementaryInstance) -> str:
            return self._cmd_print_branch_elementary(el)

        def branch_complex_generic(ci: ComplexInstance) -> str:
            return self._cmd_print_branch_complex_generic(ci, mt)

        def branch_var_mapping(vm: VariableMappingEntry) -> str:
            return self._cmd_print_branch_var_mapping(vm)

        def branch_fallback() -> str:
            return self._cmd_print_branch_fallback(target)

        if isinstance(target, ComplexInstance) and target is self.model.root:
            return branch_model_root(target)
        if isinstance(target, ComplexInstance) and mt == "MODEL.CAL_PARAM":
            return branch_cal_param(target)
        if isinstance(target, ComplexInstance) and mt == "MODEL.PARAMETER_DATA_SET":
            return self._format_print_dataset_node(target)
        if isinstance(target, ComplexInstance) and mt == "MODEL.PARAMETER_DATA_CONTAINER":
            return self._format_print_data_container(target)
        if isinstance(target, ComplexInstance) and mt == "MODEL.PARAMETER_DATA_SETS":
            return branch_parameter_data_sets(target)
        if isinstance(target, ComplexInstance) and mt == "MODEL.PARAMETERS":
            return branch_parameters_folder(target)
        if isinstance(target, Variable):
            return branch_variable(target)
        if isinstance(target, BasicOperator):
            return branch_basic_operator(target)
        if isinstance(target, Connector):
            return branch_connector(target)
        if isinstance(target, DataViewer):
            return branch_dataviewer(target)
        if isinstance(target, ElementaryInstance):
            return branch_elementary(target)
        if isinstance(target, ComplexInstance):
            return branch_complex_generic(target)
        if isinstance(target, VariableMappingEntry):
            return branch_var_mapping(target)
        return branch_fallback()

    def _cmd_del(self, args: list[str]) -> str:
        if not args:
            raise CommandError("del requires at least one reference or @selected.")

        if args[0] == "@selected":
            if len(args) != 1:
                raise CommandError("del @selected must not be combined with other references.")
            removed = self._delete_objects_ordered(self._ordered_selection_for_delete())
            self._prune_selection_after_delete()
            return str(removed)

        removed = 0
        for ref in args:
            obj = self._resolve_ref(ref)
            if obj.parent is None:
                continue
            self._delete_one_object(obj)
            removed += 1
        self._prune_selection_after_delete()
        return str(removed)

    def _cmd_cp(self, args: list[str]) -> str:
        """Copy cal-param payloads either pairwise or selection-based."""
        if not args:
            raise CommandError("usage: cp cal_param <sourceRef> <destRef> | cp @selection <targetDataSetRef>")
        if args[0] == "@selection":
            if len(args) != 2:
                raise CommandError("usage: cp @selection <targetDataSetRef>")
            target = self._resolve_ref(args[1])
            if not isinstance(target, ComplexInstance) or target.id is None:
                raise CommandError("target data set must resolve to an attached object with id")
            if self._node_model_type(target) != "MODEL.PARAMETER_DATA_SET":
                raise CommandError("target must be a MODEL.PARAMETER_DATA_SET")
            return self._cmd_cp_selection_to_dataset(target)
        if len(args) < 3:
            raise CommandError("usage: cp cal_param <sourceRef> <destRef>")
        if args[0] != "cal_param":
            raise CommandError("cp: only 'cal_param' or '@selection' is supported")
        src = self._resolve_ref(args[1])
        dst = self._resolve_ref(args[2])
        if not isinstance(src, ComplexInstance) or src.id is None:
            raise CommandError("source must resolve to an attached object with id")
        if not isinstance(dst, ComplexInstance) or dst.id is None:
            raise CommandError("destination must resolve to an attached object with id")
        if self._node_model_type(src) != "MODEL.CAL_PARAM":
            raise CommandError("source must be a CAL_PARAM")
        if self._node_model_type(dst) != "MODEL.CAL_PARAM":
            raise CommandError("destination must be a CAL_PARAM")
        rt = self.model.parameter_runtime()
        rt.ensure_tree()
        rt.repo.copy_cal_param_payload(src.id, dst.id)
        return f"ok {args[1]} -> {args[2]}"

    def _iter_cal_params_under(self, node: ComplexInstance) -> list[ComplexInstance]:
        out: list[ComplexInstance] = []
        stack: list[ComplexInstance] = [node]
        while stack:
            cur = stack.pop()
            for child in cur.children:
                if not isinstance(child, ComplexInstance):
                    continue
                stack.append(child)
                if self._node_model_type(child) == "MODEL.CAL_PARAM" and child.id is not None:
                    out.append(child)
        return out

    def _create_cal_param_for_copy(
        self, target_ds: ComplexInstance, src: ComplexInstance, src_rec: ParameterRecord
    ) -> ComplexInstance:
        """Leere Ziel-Kenngröße unter ``target_ds`` (gleicher Name/Kategorie) für ``cp @selection``."""
        rt = self.model.parameter_runtime()
        rt.ensure_tree()
        obj = ComplexInstance(name=src.name)
        obj.attribute_dict["type"] = "MODEL.CAL_PARAM"
        try:
            self.model.attach(obj, parent=target_ds, reserve_existing=False, remap_ids=False)
        except DuplicateIdError as exc:
            raise CommandError(str(exc)) from exc
        try:
            rt.register_cal_param_node(
                obj,
                data_set_id=target_ds.id,
                category=str(src_rec.category),
            )
        except Exception as exc:
            if obj.parent is not None and obj.id is not None:
                try:
                    self.model.delete(obj.parent, obj.id)
                except Exception:
                    pass
            raise CommandError(f"Ziel-Kenngröße {src.name!r} anlegen: {exc}") from exc
        return obj

    def _selected_cal_params(self) -> list[ComplexInstance]:
        out: list[ComplexInstance] = []
        seen: set[UUID] = set()
        for obj in self.selection:
            if not isinstance(obj, ComplexInstance) or obj.id is None:
                continue
            if self._node_model_type(obj) != "MODEL.CAL_PARAM":
                continue
            if obj.id in seen:
                continue
            seen.add(obj.id)
            out.append(obj)
        return out

    def _cp_selection_index_targets(self, target_ds: ComplexInstance) -> dict[str, list[ComplexInstance]]:
        target_by_name: dict[str, list[ComplexInstance]] = {}
        for node in self._iter_cal_params_under(target_ds):
            target_by_name.setdefault(node.name, []).append(node)
        return target_by_name

    def _cp_selection_collect_pairs(
        self,
        selected: list[ComplexInstance],
        target_ds: ComplexInstance,
        target_by_name: dict[str, list[ComplexInstance]],
        rt: Any,
        src_rec_map: dict[UUID, ParameterRecord],
        hook: Any,
        n_sel: int,
    ) -> tuple[
        list[tuple[UUID, UUID]],
        list[str],
        int,
        list[dict[str, str]],
        list[str],
    ]:
        pairs: list[tuple[UUID, UUID]] = []
        pair_names: list[str] = []
        skipped = 0
        skipped_details: list[dict[str, str]] = []
        errors: list[str] = []
        for idx, src in enumerate(selected):
            if hook is not None and idx % 50 == 0:
                try:
                    hook(idx + 1, n_sel)
                except Exception:
                    pass
            src_id = src.id
            if src_id is None:
                skipped += 1
                skipped_details.append({"name": src.name, "reason": "missing_source_id"})
                continue
            src_rec = src_rec_map.get(src_id)
            if src_rec is None:
                try:
                    src_rec = rt.repo.get_record(src_id)
                except Exception as exc:
                    errors.append(f"{src.name}: {exc}")
                    continue
            if src_rec.data_set_id == target_ds.id:
                skipped += 1
                skipped_details.append({"name": src.name, "reason": "source_already_in_target_dataset"})
                continue
            cands = target_by_name.get(src.name, [])
            if not cands:
                try:
                    dst_new = self._create_cal_param_for_copy(target_ds, src, src_rec)
                except CommandError as exc:
                    errors.append(str(exc))
                    continue
                target_by_name.setdefault(src.name, []).append(dst_new)
                cands = [dst_new]
            if len(cands) != 1:
                errors.append(f"{src.name}: target ambiguous ({len(cands)})")
                continue
            dst = cands[0]
            if dst.id is None:
                skipped += 1
                skipped_details.append({"name": src.name, "reason": "target_parameter_has_no_id"})
                continue
            pairs.append((src_id, dst.id))
            pair_names.append(src.name)
        return pairs, pair_names, skipped, skipped_details, errors

    def _cp_selection_apply_bulk_copy(
        self,
        pairs: list[tuple[UUID, UUID]],
        pair_names: list[str],
        rt: Any,
        hook: Any,
        n_sel: int,
        errors: list[str],
    ) -> tuple[int, list[str], list[str]]:
        copied = 0
        copied_dst_ids: list[str] = []
        copied_src_ids: list[str] = []
        if not pairs:
            return copied, copied_dst_ids, copied_src_ids

        def bulk_progress(done: int, _n_pairs: int) -> None:
            if hook is None:
                return
            try:
                hook(min(done, n_sel), n_sel)
            except Exception:
                pass

        bulk_errs = rt.repo.copy_cal_param_payload_bulk(
            pairs,
            chunk_size=300,
            cooperative_hook=None,
            progress_hook=bulk_progress,
        )
        for (src_uid, dst_id), name, err in zip(pairs, pair_names, bulk_errs, strict=True):
            if err:
                errors.append(f"{name}: {err}")
            else:
                copied += 1
                copied_dst_ids.append(str(dst_id))
                copied_src_ids.append(str(src_uid))
        return copied, copied_dst_ids, copied_src_ids

    def _cmd_cp_selection_report_json(
        self,
        *,
        copied: int,
        skipped: int,
        errors: list[str],
        copied_dst_ids: list[str],
        copied_src_ids: list[str],
        skipped_details: list[dict[str, str]],
    ) -> str:
        return json.dumps(
            {
                "copied": copied,
                "skipped": skipped,
                "errors": errors,
                "copied_dst_ids": copied_dst_ids,
                "copied_src_ids": copied_src_ids,
                "skipped_details": skipped_details,
            },
            ensure_ascii=False,
        )

    def _cmd_cp_selection_to_dataset(self, target_ds: ComplexInstance) -> str:
        selected = self._selected_cal_params()
        if not selected:
            raise CommandError("cp @selection requires at least one selected CAL_PARAM")
        if target_ds.id is None:
            raise CommandError("target data set must have an id")

        target_by_name = self._cp_selection_index_targets(target_ds)
        rt = self.model.parameter_runtime()
        rt.ensure_tree()

        n_sel = len(selected)
        hook = self.cp_selection_progress_hook
        if hook is not None and n_sel:
            try:
                hook(0, n_sel)
            except Exception:
                pass

        prefetch_ids = [s.id for s in selected if s.id is not None]
        src_rec_map: dict[UUID, ParameterRecord] = (
            rt.repo.get_records_for_ids(prefetch_ids) if prefetch_ids else {}
        )

        pairs, pair_names, skipped, skipped_details, errors = self._cp_selection_collect_pairs(
            selected, target_ds, target_by_name, rt, src_rec_map, hook, n_sel
        )
        copied, copied_dst_ids, copied_src_ids = self._cp_selection_apply_bulk_copy(
            pairs, pair_names, rt, hook, n_sel, errors
        )

        if hook is not None and n_sel:
            try:
                hook(n_sel, n_sel)
            except Exception:
                pass

        return self._cmd_cp_selection_report_json(
            copied=copied,
            skipped=skipped,
            errors=errors,
            copied_dst_ids=copied_dst_ids,
            copied_src_ids=copied_src_ids,
            skipped_details=skipped_details,
        )

    def _delete_one_object(self, obj: Any) -> None:
        if obj.parent is None or obj.id is None:
            return
        if isinstance(obj, ComplexInstance):
            try:
                if str(obj.get("type")) == "MODEL.PARAMETER_DATA_SET":
                    self._delete_parameter_data_set_cascade(obj)
                    return
            except KeyError:
                pass
        # Wenn ein DataViewer gelöscht wird, entferne seine ID aus allen Variablen-Messzuordnungen.
        if isinstance(obj, DataViewer):
            try:
                dv_id = int(obj.get("dataviewer_id"))
            except (KeyError, TypeError, ValueError):
                dv_id = None
            if dv_id is not None:
                from synarius_core.model import Variable  # lokaler Import, um Zyklen zu vermeiden

                for node in self.model.iter_objects():
                    if isinstance(node, Variable):
                        try:
                            ids = list(node.get("dataviewer_measure_ids") or [])
                        except Exception:
                            continue
                        if dv_id in ids:
                            new_ids = [i for i in ids if i != dv_id]
                            try:
                                node.set("dataviewer_measure_ids", new_ids)
                            except Exception:
                                continue
        if self.model.is_in_trash_subtree(obj):
            self.model.delete(obj.parent, obj.id)  # type: ignore[arg-type]
        else:
            self.model.reparent(obj, self.model.get_trash_folder())

    def _delete_parameter_data_set_cascade(self, ds_node: ComplexInstance) -> None:
        """Alle Kenngrößen dieses Satzes aus dem Modell, DuckDB-Einträge und den DataSet-Knoten entfernen."""
        ds_id = ds_node.id
        if ds_id is None:
            return
        root = self.model.parameter_runtime().data_sets_root()
        pairs: list[tuple[ComplexInstance, UUID]] = []
        stack: list[ComplexInstance] = [ds_node]
        while stack:
            cur = stack.pop()
            for child in list(cur.children):
                if isinstance(child, ComplexInstance):
                    stack.append(child)
                    if self._node_model_type(child) == "MODEL.CAL_PARAM" and child.id is not None:
                        pairs.append((cur, child.id))
        if pairs:
            self.model.delete_many(pairs)

        rt = self.model.parameter_runtime()
        try:
            ad = rt.active_dataset()
            if ad is not None and ad.id == ds_id:
                rt.set_active_dataset_name(None)
        except Exception:
            pass
        rt.repo.delete_data_set_and_parameters(ds_id)
        self.model.delete(root, ds_id)

    def _ordered_selection_for_delete(self) -> list[Any]:
        """Stable delete order: connectors, then operators, then variables, then other types."""
        seen: set[UUID] = set()
        unique: list[Any] = []
        for obj in self.selection:
            oid = getattr(obj, "id", None)
            if oid is None or oid in seen:
                continue
            seen.add(oid)
            unique.append(obj)

        connectors: list[Any] = []
        operators: list[Any] = []
        variables: list[Any] = []
        other: list[Any] = []
        for obj in unique:
            if isinstance(obj, Connector):
                connectors.append(obj)
            elif isinstance(obj, BasicOperator):
                operators.append(obj)
            elif isinstance(obj, Variable):
                variables.append(obj)
            else:
                other.append(obj)

        key = attrgetter("hash_name")
        connectors.sort(key=key)
        operators.sort(key=key)
        variables.sort(key=key)
        other.sort(key=key)
        return connectors + operators + variables + other

    def _delete_objects_ordered(self, objects: list[Any]) -> int:
        removed = 0
        for obj in objects:
            if obj.parent is None:
                continue
            oid = getattr(obj, "id", None)
            if oid is None:
                continue
            self._delete_one_object(obj)
            removed += 1
        return removed

    def _prune_selection_after_delete(self) -> None:
        """Drop selection entries removed from the model or moved into trash."""
        kept: list[Any] = []
        for obj in self.selection:
            oid = getattr(obj, "id", None)
            if oid is None:
                continue
            hit = self.model.find_by_id(oid)
            if hit is None:
                continue
            if self.model.is_in_trash_subtree(hit):
                continue
            kept.append(hit)
        self.selection = kept

    def _cmd_import(self, args: list[str]) -> str:
        """``import -dcm=<filePath> [<DataSetRef>]`` — DCM import; see controller_command_protocol.rst."""
        dcm_paths: list[str] = []
        positionals: list[str] = []
        for t in args:
            if t.startswith("-dcm="):
                dcm_paths.append(t[len("-dcm=") :])
            elif t == "-dcm":
                raise CommandError('import DCM requires -dcm="<path>" (single token with =).')
            else:
                positionals.append(t)
        if not dcm_paths:
            raise CommandError(
                'import DCM requires -dcm="<filePath>" '
                "(optional <DataSetRef> only when cwd is not a PARAMETER_DATA_SET)."
            )
        if len(dcm_paths) > 1:
            raise CommandError("import DCM accepts only one -dcm= option.")
        raw_path = dcm_paths[0].strip()
        if not raw_path:
            raise CommandError("import DCM: -dcm= path is empty.")
        if len(positionals) > 1:
            raise CommandError("import DCM accepts at most one <DataSetRef> after options.")
        on_dataset = self._node_model_type(self.current) == "MODEL.PARAMETER_DATA_SET"
        if on_dataset:
            if positionals:
                raise CommandError(
                    "import DCM: cwd is already a PARAMETER_DATA_SET; use only -dcm=... "
                    "(omit <DataSetRef>, or cd out of the data set to target another by reference)."
                )
            ds_ref = "."
        else:
            if not positionals:
                raise CommandError(
                    "import DCM: cwd is not a PARAMETER_DATA_SET; "
                    "give <DataSetRef> after -dcm=... or cd into the target data set first."
                )
            ds_ref = positionals[0]
        p = Path(raw_path).expanduser()
        if not p.is_file():
            base = self.last_loaded_script_path
            if base is not None:
                alt = (base.parent / raw_path).expanduser().resolve()
                if alt.is_file():
                    p = alt
        if not p.is_file():
            raise CommandError(f"DCM file not found: {p}")
        from synarius_core.parameters.dcm_io import import_dcm_for_dataset

        try:
            n = import_dcm_for_dataset(
                self,
                ds_ref,
                str(p.resolve()),
                progress_hook=self.dcm_import_progress_hook,
                import_phase_hook=self.dcm_import_phase_hook,
                cooperative_hook=self.dcm_import_cooperative_hook,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        return str(n)

    def _cmd_write(self, args: list[str]) -> str:
        """``write "<outputPath>"`` — schreibt den aktiven Parametersatz als DCM-Datei (KONSERVIERUNG_FORMAT 2.0)."""
        if not args:
            raise CommandError('write requires "<outputPath>".')
        raw_path = args[0]
        p = Path(raw_path).expanduser()
        if not p.is_absolute():
            base = self.last_loaded_script_path
            if base is not None:
                p = (base.parent / raw_path).expanduser()
        p = p.resolve()
        from synarius_core.parameters.dcm_io import write_dcm_for_active_dataset

        try:
            n, skipped_text = write_dcm_for_active_dataset(self, p)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if skipped_text:
            return f"{n} ({skipped_text} text parameters omitted as comments)"
        return str(n)

    def _cmd_load_run_script_on_clone(
        self,
        script_path: Path,
        *,
        cwd_id: UUID | None,
        sel_ids: list[UUID],
        into: str | None,
        id_policy: str,
    ) -> tuple[Any, list[str]]:
        _ = id_policy, sel_ids
        temp_model = self.model.clone()
        temp_controller = SynariusController(
            temp_model,
            library_catalog=self.library_catalog,
            plugin_registry=self.plugin_registry,
            record_undo=False,
        )
        if cwd_id is not None:
            cloned_cwd = temp_model.find_by_id(cwd_id)
            if isinstance(cloned_cwd, ComplexInstance):
                temp_controller.current = cloned_cwd
        if into:
            target = temp_controller._resolve_path(into)
            if not isinstance(target, ComplexInstance):
                raise CommandError("load into=<path> must resolve to ComplexInstance.")
            temp_controller.current = target
        temp_controller.dcm_import_progress_hook = self.dcm_import_progress_hook
        temp_controller.dcm_import_phase_hook = self.dcm_import_phase_hook
        temp_controller.dcm_import_cooperative_hook = self.dcm_import_cooperative_hook
        command_trace: list[str] = []
        temp_controller.execute_script(script_path, command_trace=command_trace)
        return temp_model, command_trace

    def _cmd_load_commit_state(
        self,
        temp_model: Any,
        command_trace: list[str],
        *,
        script_path: Path,
        cwd_id: UUID | None,
        sel_ids: list[UUID],
        id_policy: str,
    ) -> str:
        _ = id_policy
        self.model = temp_model
        self._rebind_model_root_aliases()
        if cwd_id is not None:
            new_cwd = self.model.find_by_id(cwd_id)
            if isinstance(new_cwd, ComplexInstance):
                self.current = new_cwd
            else:
                self.current = self.model.root
        else:
            self.current = self.model.root
        self.selection = [obj for obj_id in sel_ids if (obj := self.model.find_by_id(obj_id)) is not None]
        try:
            self.last_loaded_script_path = script_path.expanduser().resolve()
        except OSError:
            self.last_loaded_script_path = script_path.expanduser()
        return "\n".join(command_trace)

    def _cmd_load(self, args: list[str]) -> str:
        if not args:
            raise CommandError('load requires "<scriptPath>".')

        script_path = Path(args[0])
        opts = parse_kw_pairs(args[1:])
        into = opts.get("into")
        id_policy = opts.get("idPolicy", "remap")
        if id_policy not in {"remap", "keep"}:
            raise CommandError("idPolicy must be remap or keep.")

        cwd_id = self.current.id
        sel_ids = [obj.id for obj in self.selection if obj.id is not None]

        temp_model, command_trace = self._cmd_load_run_script_on_clone(
            script_path,
            cwd_id=cwd_id,
            sel_ids=sel_ids,
            into=into,
            id_policy=id_policy,
        )
        return self._cmd_load_commit_state(
            temp_model,
            command_trace,
            script_path=script_path,
            cwd_id=cwd_id,
            sel_ids=sel_ids,
            id_policy=id_policy,
        )

    def _require_fmu_elementary(self, obj: Any, *, command: str) -> ElementaryInstance:
        if not isinstance(obj, ElementaryInstance):
            raise CommandError(
                f"{command} is not available for this object type "
                "(only FMU-backed elementaries are supported today)."
            )
        try:
            obj.get("fmu")
        except KeyError:
            raise CommandError(f"{command} is not available: target has no fmu subtree.")
        return obj

    def _fmu_inspect_path_json(self, path: str) -> str:
        try:
            data = inspect_fmu_path(path)
        except FmuInspectError as exc:
            raise CommandError(str(exc)) from exc
        return json.dumps(data, indent=2, sort_keys=True, default=str)

    def _parse_optional_fmu_file_kw(self, kwargs: dict[str, str]) -> str | None:
        """Optional alternate archive from ``from=`` or ``path=`` (must not disagree)."""
        fr = kwargs.get("from")
        pr = kwargs.get("path")
        s_from = str(fr).strip() if fr is not None and str(fr).strip() != "" else ""
        s_path = str(pr).strip() if pr is not None and str(pr).strip() != "" else ""
        if s_from and s_path and s_from != s_path:
            raise CommandError("from= and path= must not specify different files.")
        return s_from or s_path or None

    def _fmu_sync_elementary_from_path(
        self,
        obj: ElementaryInstance,
        *,
        alternate_fmu_file: str | None,
    ) -> None:
        lib = self._library_pin_seed_for_type_key(obj.type_key)
        try:
            if alternate_fmu_file:
                bind_elementary_from_fmu_path(
                    obj,
                    alternate_fmu_file,
                    library_pin_seed=lib,
                    set_path=True,
                )
            else:
                cur = obj.get("fmu.path")
                if cur is None or str(cur).strip() == "":
                    raise CommandError(
                        "No fmu.path on target; pass from=<path> or path=<path> to an FMU file."
                    )
                data = inspect_fmu_path(str(cur).strip())
                bind_fmu_inspection_to_elementary(obj, data, library_pin_seed=lib, path_override=None)
        except FmuInspectError as exc:
            raise CommandError(str(exc)) from exc
        except FmuBindError as exc:
            raise CommandError(str(exc)) from exc

    def _cmd_inspect(self, args: list[str]) -> str:
        """``inspect <ref>`` — JSON inspection for the target's ``fmu.path`` (read-only)."""
        if not args:
            raise CommandError(
                "inspect requires <ref>. For a file path without a model object use: fmu inspect <path>"
            )
        ref = args[0]
        for t in args[1:]:
            if "=" not in t:
                raise CommandError("inspect accepts only a single reference (no extra positional arguments).")
        obj = self._resolve_ref(ref)
        el = self._require_fmu_elementary(obj, command="inspect")
        if self.use_element_type_handlers:
            h = self.element_type_registry.get(el.type_key)
            if h is not None:
                ictx = InspectContext(controller=self, model=self.model)
                res = h.inspect(ictx, ref)
                from synarius_core.plugins.FmuRuntime.fmu_instance_handler import inspect_result_to_json

                return inspect_result_to_json(res)
        try:
            cur = el.get("fmu.path")
        except KeyError:
            cur = None
        if cur is None or str(cur).strip() == "":
            raise CommandError(
                "inspect needs a non-empty fmu.path on the target "
                "(deprecated alternative: fmu inspect <pathTo.fmu>)."
            )
        return self._fmu_inspect_path_json(str(cur).strip())

    def _cmd_sync(self, args: list[str]) -> str:
        """``sync <ref> [from=<path> | path=<path>]`` — refresh FMU metadata and pins (former fmu bind/reload)."""
        if not args:
            raise CommandError("sync requires <ref> [from=<path> | path=<path>].")
        ref = args[0]
        kwargs = parse_kw_pairs(args[1:])
        for t in args[1:]:
            if "=" not in t:
                raise CommandError("sync only accepts key=value options (from= or path=).")
        obj = self._resolve_ref(ref)
        el = self._require_fmu_elementary(obj, command="sync")
        if self.use_element_type_handlers:
            h = self.element_type_registry.get(el.type_key)
            if h is not None:
                sctx = SyncContext(controller=self, model=self.model, options=dict(kwargs))
                h.sync(sctx, ref)
                return "ok"
        alt = self._parse_optional_fmu_file_kw(kwargs)
        self._fmu_sync_elementary_from_path(el, alternate_fmu_file=alt)
        return "ok"

    def _cmd_fmu(self, args: list[str]) -> str:
        """``fmu inspect <path>`` (file-only). ``fmu bind`` / ``fmu reload`` were removed; use ``sync`` on a reference."""
        if not args:
            raise CommandError("fmu requires a subcommand: inspect.")
        sub = args[0]
        rest = args[1:]

        if sub == "inspect":
            if len(rest) != 1:
                raise CommandError("fmu inspect requires exactly one path (quote if it contains spaces).")
            return self._fmu_inspect_path_json(rest[0])

        if sub in {"bind", "reload"}:
            raise CommandError(
                f"fmu {sub} was removed; use: sync <ref> [from=<path> | path=<path>] "
                "(see controller_command_protocol)."
            )

        raise CommandError(f"Unknown fmu subcommand '{sub}' (use inspect).")

    # ------------------------ Parsing / resolution helpers --------------------
    # Stateless parsers and single-segment resolution live in ``parse_helpers``.
    # Only ``_resolve_path`` / ``_resolve_ref`` need ``current``, alias roots, and ``model``.

    def _resolve_ref(self, ref: str) -> Any:
        hit = try_resolve_global_object_ref(ref, self.model.find_by_id)
        if hit is not None:
            return hit
        obj = self._resolve_path(ref)
        if obj is None:
            raise CommandError(f"Could not resolve reference '{ref}'.")
        return obj

    def _resolve_path(self, path: str) -> Any:
        path = path.strip()
        if not path:
            return self.current

        if path == ".":
            return self.current
        if path == "..":
            return self.current.parent or self.current

        start = self.current
        tail = path
        if path.startswith("@"):
            alias, _, rest = path.partition("/")
            if alias not in self.alias_roots:
                raise CommandError(f"Unknown alias root '{alias}'.")
            start = self.alias_roots[alias]
            tail = rest
        elif path.startswith("/"):
            start = self.model.root
            tail = path.lstrip("/")

        node: Any = start
        if not tail:
            return node
        for segment in [part for part in tail.split("/") if part and part != "."]:
            if segment == "..":
                node = node.parent if getattr(node, "parent", None) is not None else node
                continue
            if not (isinstance(node, ComplexInstance) or callable(getattr(node, "get_child", None))):
                raise CommandError(f"Path segment '{segment}' cannot be resolved from non-container.")
            child = resolve_path_segment(node, segment)
            if child is None:
                raise CommandError(f"Path segment '{segment}' not found.")
            node = child
        return node


SynariusController._COMMAND_HANDLERS = Map(
    {
        "ls": SynariusController._cmd_ls,
        "lsattr": SynariusController._cmd_lsattr,
        "cd": SynariusController._cmd_cd,
        "new": SynariusController._cmd_new,
        "select": SynariusController._cmd_select,
        "set": SynariusController._cmd_set,
        "get": SynariusController._cmd_get,
        "print": SynariusController._cmd_print,
        "del": SynariusController._cmd_del,
        "mv": SynariusController._cmd_mv,
        "load": SynariusController._cmd_load,
        "import": SynariusController._cmd_import,
        "write": SynariusController._cmd_write,
        "cp": SynariusController._cmd_cp,
    }
)

