from __future__ import annotations

import shlex
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

UndoRedoPair = tuple[list[str], list[str]]

from synarius_core.library import LibraryCatalog
from synarius_core.model import (
    BaseObject,
    BasicOperator,
    BasicOperatorType,
    ComplexInstance,
    Connector,
    LocatableInstance,
    Model,
    Size2D,
    Variable,
)
from synarius_core.model.connector_routing import bends_absolute_to_relative
from synarius_core.model.diagram_geometry import instance_source_pin_diagram_xy


class CommandError(ValueError):
    """Raised for invalid protocol command usage."""


class MinimalController:
    """Minimal text-command controller implementing core protocol commands."""

    def __init__(
        self,
        model: Model | None = None,
        *,
        library_catalog: LibraryCatalog | None = None,
        max_undo_depth: int = 100,
        record_undo: bool = True,
    ) -> None:
        self.model = model or Model.new("main")
        self.library_catalog = library_catalog if library_catalog is not None else LibraryCatalog.load_default()
        self.max_undo_depth = max(1, int(max_undo_depth))
        self._undo_recording_enabled = bool(record_undo)
        self._undo_stack: list[UndoRedoPair] = []
        self._redo_stack: list[UndoRedoPair] = []
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

    def _rebind_model_root_aliases(self) -> None:
        """Point workspace aliases at ``self.model.root`` after the model instance was replaced (e.g. ``load``)."""
        root = self.model.root
        self.alias_roots["@main"] = root
        self.alias_roots["@objects"] = root
        self.alias_roots["@controller"] = root
        self.alias_roots["@latent"] = root
        self.alias_roots["@signals"] = root

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
            self._clear_undo_stacks()
            return out

        if cmd == "new":
            out = self._dispatch_command(cmd, args)
            pair = self._undo_pair_after_new(raw, out)
            self._record_undo_pair(pair)
            return out

        if cmd == "select":
            old_refs = [o.hash_name for o in self.selection]
            out = self._dispatch_command(cmd, args)
            if self._undo_recording_enabled:
                new_refs = [o.hash_name for o in self.selection]
                undo_ln = "select " + " ".join(shlex.quote(r) for r in old_refs) if old_refs else "select"
                redo_ln = "select " + " ".join(shlex.quote(r) for r in new_refs) if new_refs else "select"
                self._record_undo_pair(([undo_ln], [redo_ln]))
            return out

        pair = self._try_build_undo_pair(cmd, args, raw)
        out = self._dispatch_command(cmd, args)
        self._record_undo_pair(pair)
        return out

    def _dispatch_command(self, cmd: str, args: list[str]) -> str | None:
        if cmd == "ls":
            return self._cmd_ls()
        if cmd == "lsattr":
            return self._cmd_lsattr(args)
        if cmd == "cd":
            return self._cmd_cd(args)
        if cmd == "new":
            return self._cmd_new(args)
        if cmd == "select":
            return self._cmd_select(args)
        if cmd == "set":
            return self._cmd_set(args)
        if cmd == "get":
            return self._cmd_get(args)
        if cmd == "del":
            return self._cmd_del(args)
        if cmd == "mv":
            return self._cmd_mv(args)
        if cmd == "load":
            return self._cmd_load(args)

        raise CommandError(f"Unknown command '{cmd}'.")

    def _clear_undo_stacks(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def _push_undo_only(self, undo_cmds: list[str], redo_cmds: list[str]) -> None:
        self._undo_stack.append((undo_cmds, redo_cmds))
        while len(self._undo_stack) > self.max_undo_depth:
            self._undo_stack.pop(0)

    def _record_undo_pair(self, pair: UndoRedoPair | None) -> None:
        if pair is None or not self._undo_recording_enabled:
            return
        self._push_undo_only(pair[0], pair[1])
        self._redo_stack.clear()

    def _execute_command_lines_without_undo(self, lines: list[str]) -> None:
        prev = self._undo_recording_enabled
        self._undo_recording_enabled = False
        try:
            for ln in lines:
                self.execute(ln)
        finally:
            self._undo_recording_enabled = prev

    def _cmd_undo(self, args: list[str]) -> str:
        n = int(args[0]) if args else 1
        if n < 1:
            raise CommandError("undo requires a positive step count.")
        steps = 0
        for _ in range(n):
            if not self._undo_stack:
                break
            undo_cmds, redo_cmds = self._undo_stack.pop()
            self._execute_command_lines_without_undo(undo_cmds)
            self._redo_stack.append((undo_cmds, redo_cmds))
            steps += 1
        return str(steps)

    def _cmd_redo(self, args: list[str]) -> str:
        n = int(args[0]) if args else 1
        if n < 1:
            raise CommandError("redo requires a positive step count.")
        steps = 0
        for _ in range(n):
            if not self._redo_stack:
                break
            undo_cmds, redo_cmds = self._redo_stack.pop()
            self._execute_command_lines_without_undo(redo_cmds)
            self._push_undo_only(undo_cmds, redo_cmds)
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
            inner = ",".join(str(x) for x in value)
            return shlex.quote(inner)
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

    def _undo_pair_before_del(self, args: list[str]) -> UndoRedoPair | None:
        trash = self.model.get_trash_folder()
        trash_p = self._container_path_for_mv(trash)
        plans: list[tuple[str, str]] = []

        if args and args[0] == "@selected":
            if len(args) != 1:
                return None
            objs = self._ordered_selection_for_delete()
        else:
            objs = [self._resolve_ref(r) for r in args]

        if not objs:
            return None
        trash_flags = [self.model.is_in_trash_subtree(o) for o in objs]
        if any(trash_flags) and not all(trash_flags):
            raise CommandError("del cannot combine objects inside trash with live objects in one command.")
        if all(trash_flags):
            return None

        for obj in objs:
            if obj.parent is None or not isinstance(obj.parent, ComplexInstance):
                continue
            plans.append((obj.hash_name, self._container_path_for_mv(obj.parent)))

        if not plans:
            return None
        undo_cmds = [f"mv {shlex.quote(h)} {shlex.quote(p)}" for h, p in reversed(plans)]
        redo_cmds = [f"mv {shlex.quote(h)} {shlex.quote(trash_p)}" for h, _p in plans]
        return (undo_cmds, redo_cmds)

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

    def _undo_pair_set(self, args: list[str], raw: str) -> UndoRedoPair | None:
        if len(args) < 2:
            return None
        redo = [raw]

        if args[0] == "-p" and len(args) >= 3 and args[1] == "@selection":
            rest = args[2:]
            attr = rest[0]
            tail = rest[1:]
            items = list(self.selection)
            if not items:
                return None
            if attr == "position" and len(tail) >= 2:
                dx = float(tail[0])
                dy = float(tail[1])
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

            if len(tail) < 1:
                return None
            delta_val = self._parse_value(" ".join(tail))
            if not isinstance(delta_val, (int, float)):
                return None
            undo_cmds = []
            for item in items:
                try:
                    cur = self._get_attr(item, attr)
                except CommandError:
                    continue
                if not isinstance(cur, (int, float)):
                    continue
                prev = float(cur) - float(delta_val)
                undo_cmds.append(f"set {shlex.quote(item.hash_name)}.{attr} {self._format_cli_value(prev)}")
            if not undo_cmds:
                return None
            return (undo_cmds, redo)

        if args[0] == "@selection":
            rest = args[1:]
            if len(rest) < 2:
                return None
            attr = rest[0]
            value = self._parse_value(" ".join(rest[1:]))
            undo_cmds = []
            for item in self.selection:
                try:
                    old = self._get_attr(item, attr)
                except CommandError:
                    continue
                undo_cmds.append(f"set {shlex.quote(item.hash_name)}.{attr} {self._format_cli_value(old)}")
            if not undo_cmds:
                return None
            return (undo_cmds, redo)

        target_expr = args[0]
        value = self._parse_value(" ".join(args[1:]))
        if "." in target_expr:
            path, attr = target_expr.rsplit(".", 1)
            target = self._resolve_path(path)
            try:
                old = self._get_attr(target, attr)
            except CommandError:
                return None
            undo = [f"set {target_expr} {self._format_cli_value(old)}"]
            return (undo, redo)

        try:
            old = self._get_attr(self.current, target_expr)
        except CommandError:
            return None
        undo = [f"set {target_expr} {self._format_cli_value(old)}"]
        return (undo, redo)

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

    def execute_script(self, script_path: str | Path) -> list[str]:
        path = Path(script_path)
        if not path.exists():
            raise CommandError(f"Script not found: {path}")

        outputs: list[str] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                result = self.execute(line)
            except Exception as exc:
                raise CommandError(f"Script error at line {line_no}: {line.strip()} -> {exc}") from exc
            if result is not None:
                outputs.append(result)
        return outputs

    # ------------------------ Command handlers --------------------------------

    def _cmd_ls(self) -> str:
        children = getattr(self.current, "children", None)
        if not children:
            return ""
        lines: list[str] = []
        for child in children:
            lines.append(str(self._get_attr(child, "name")))
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

        keys = sorted(context.attribute_dict.keys())
        return self._format_lsattr_table(context, keys, long_mode=long_mode)

    def _format_lsattr_table(self, context: Any, keys: list[str], *, long_mode: bool) -> str:
        rows: list[tuple[str, ...]] = []
        for key in keys:
            value = self._format_value(self._get_attr(context, key))
            if long_mode:
                rows.append(
                    (
                        key,
                        value,
                        "true" if context.attribute_dict.virtual(key) else "false",
                        "true" if context.attribute_dict.exposed(key) else "false",
                        "true" if context.attribute_dict.writable(key) else "false",
                    )
                )
            else:
                rows.append((key, value))

        headers: tuple[str, ...]
        if long_mode:
            headers = ("NAME", "VALUE", "VIRTUAL", "EXPOSED", "WRITABLE")
        else:
            headers = ("NAME", "VALUE")

        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        def fmt_row(cells: tuple[str, ...]) -> str:
            return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

        output = [fmt_row(headers)]
        output.extend(fmt_row(row) for row in rows)
        return "\n".join(output)

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

    def _cmd_new(self, args: list[str]) -> str:
        if not args:
            raise CommandError("new requires a type argument.")
        type_name = args[0]
        rest = args[1:]
        kwargs = self._parse_kw_pairs(rest)
        positional = [t for t in rest if "=" not in t]

        if not isinstance(self.current, ComplexInstance):
            raise CommandError("new requires a model container as cwd (e.g. cd @main first; not under @libraries).")

        if type_name == "Variable":
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
            obj = Variable(
                name=name,
                type_key=kwargs.get("type_key", "Variable"),
                value=kwargs.get("value"),
                unit=kwargs.get("unit", ""),
                position=pos,
                size=size,
            )
        elif type_name == "BasicOperator":
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
            obj = BasicOperator(
                name=kwargs.get("name", f"op_{symbol}"),
                type_key=kwargs.get("type_key", "BasicOperator"),
                operation=mapping[symbol],
                position=pos_bo,
                size=size_bo,
            )
        elif type_name == "Connector":
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
            obj = Connector(
                name=kwargs.get("name", "connector"),
                source_instance_id=src.id,  # type: ignore[arg-type]
                source_pin=sp,
                target_instance_id=dst.id,  # type: ignore[arg-type]
                target_pin=kwargs.get("target_pin", "in"),
                directed=self._parse_bool(kwargs.get("directed", "true")),
                orthogonal_bends=ob_list,
            )
        else:
            raise CommandError(f"Unsupported new type '{type_name}'.")

        self.model.attach(obj, parent=self.current, reserve_existing=False, remap_ids=False)
        return obj.hash_name

    def _cmd_select(self, args: list[str]) -> str:
        if not args:
            self.selection = []
            return ""
        resolved = [self._resolve_ref(token) for token in args]
        self.selection = resolved
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
        value = self._parse_value(" ".join(args[1:]))
        if "." in target_expr:
            path, attr = target_expr.rsplit(".", 1)
            target = self._resolve_path(path)
            self._set_attr(target, attr, value)
        else:
            self._set_attr(self.current, target_expr, value)
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

            delta_val = self._parse_value(" ".join(tail))
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

        value = self._parse_value(" ".join(tail))
        for item in self.selection:
            self._set_attr(item, attr, value)
        return str(len(self.selection))

    def _apply_scalar_delta(self, obj: Any, attr: str, delta: float) -> None:
        cur = self._get_attr(obj, attr)
        if not isinstance(cur, (int, float)):
            raise CommandError(f"Attribute '{attr}' is not numeric; cannot apply delta.")
        self._set_attr(obj, attr, float(cur) + delta)

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
            return "\n".join(str(self._get_attr(item, attr)) for item in self.selection)

        target_expr = args[0]
        if "." in target_expr:
            path, attr = target_expr.rsplit(".", 1)
            target = self._resolve_path(path)
            return str(self._get_attr(target, attr))
        return str(self._get_attr(self.current, target_expr))

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

    def _delete_one_object(self, obj: Any) -> None:
        if obj.parent is None or obj.id is None:
            return
        if self.model.is_in_trash_subtree(obj):
            self.model.delete(obj.parent, obj.id)  # type: ignore[arg-type]
        else:
            self.model.reparent(obj, self.model.get_trash_folder())

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

        key = lambda o: o.hash_name
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

    def _cmd_load(self, args: list[str]) -> str:
        if not args:
            raise CommandError('load requires "<scriptPath>".')

        script_path = Path(args[0])
        opts = self._parse_kw_pairs(args[1:])
        into = opts.get("into")
        id_policy = opts.get("idPolicy", "remap")
        if id_policy not in {"remap", "keep"}:
            raise CommandError("idPolicy must be remap or keep.")

        cwd_id = self.current.id
        sel_ids = [obj.id for obj in self.selection if obj.id is not None]

        # Transactional semantics: execute on clone, commit on success.
        temp_model = self.model.clone()
        temp_controller = MinimalController(
            temp_model, library_catalog=self.library_catalog, record_undo=False
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

        temp_controller.execute_script(script_path)

        # keep-id policy with script replay is equivalent to replaying commands as-is.
        # remap is modeled by keeping model-local ID creation during command execution.
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

        return ""

    # ------------------------ Parsing / resolution helpers --------------------

    def _parse_kw_pairs(self, tokens: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for token in tokens:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            out[key] = value
        return out

    def _set_attr(self, obj: Any, attr: str, value: Any) -> None:
        try:
            obj.set(attr, value)
            return
        except KeyError:
            pass
        if hasattr(obj, attr):
            setattr(obj, attr, value)
            return
        raise CommandError(f"Attribute '{attr}' not found on target.")

    def _get_attr(self, obj: Any, attr: str) -> Any:
        try:
            return obj.get(attr)
        except KeyError:
            pass
        if hasattr(obj, attr):
            return getattr(obj, attr)
        raise CommandError(f"Attribute '{attr}' not found on target.")

    def _parse_bool(self, value: str) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _parse_value(self, raw: str) -> Any:
        text = raw.strip()
        lower = text.lower()
        if lower in {"true", "false"}:
            return lower == "true"
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    def _try_resolve_global_object_ref(self, ref: str) -> Any | None:
        """Resolve ``name@<uuid>`` anywhere in the model (not only under ``current``)."""
        s = ref.strip()
        if not s or s.startswith(("@", "/", ".")):
            return None
        if "/" in s:
            return None
        if "@" not in s:
            return None
        _, tail = s.rsplit("@", 1)
        try:
            oid = UUID(tail)
        except ValueError:
            return None
        return self.model.find_by_id(oid)

    def _resolve_ref(self, ref: str) -> Any:
        hit = self._try_resolve_global_object_ref(ref)
        if hit is not None:
            return hit
        obj = self._resolve_path(ref)
        if obj is None:
            raise CommandError(f"Could not resolve reference '{ref}'.")
        return obj

    def _resolve_child(self, container: Any, segment: str) -> Any | None:
        if isinstance(container, ComplexInstance):
            direct = container.get_child(segment)
            if direct is not None:
                return direct
            by_name = [child for child in container.children if child.name == segment]
            if len(by_name) == 1:
                return by_name[0]
            if len(by_name) > 1:
                raise CommandError(f"Reference '{segment}' is ambiguous by name.")
            return None

        nav_get = getattr(container, "get_child", None)
        if callable(nav_get):
            hit = nav_get(segment)
            if hit is not None:
                return hit
        return None

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
            child = self._resolve_child(node, segment)
            if child is None:
                raise CommandError(f"Path segment '{segment}' not found.")
            node = child
        return node

