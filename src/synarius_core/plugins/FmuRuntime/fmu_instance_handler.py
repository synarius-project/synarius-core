"""Element-type handler for FMU-backed elementaries (``new`` / ``inspect`` / ``sync``)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

from synarius_core.controller.errors import CommandError
from synarius_core.fmu.inspection import FmuInspectError, inspect_fmu_path
from synarius_core.library.fmu_descriptor import default_fmu_library_type_key
from synarius_core.model import ElementaryInstance
from synarius_core.plugins.element_types import (
    NEW_CONTEXT_OPTION_EXPLICIT_ID,
    ElementTypeHandler,
    InspectContext,
    InspectResult,
    NewContext,
    SyncContext,
)

if TYPE_CHECKING:
    from synarius_core.controller.synarius_controller import SynariusController


def _require_synarius_controller(ctrl: object) -> SynariusController:
    from synarius_core.controller.synarius_controller import SynariusController as SC

    if not isinstance(ctrl, SC):
        raise TypeError("FmuInstanceHandler requires SynariusController")
    return ctrl


class FmuInstanceHandler(ElementTypeHandler):
    """Handles ``std.FmuCoSimulation`` / legacy ``new FmuInstance`` (alias)."""

    handler_aliases = ("FmuInstance",)

    def __init__(self, *, type_key: str | None = None) -> None:
        self.type_key = type_key or default_fmu_library_type_key()

    def new(self, ctx: NewContext, ref: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        ctrl = _require_synarius_controller(ctx.controller)
        skw = {str(k): (str(v) if v is not None else "") for k, v in kwargs.items()}
        positional = [str(a) for a in args]
        if not positional and ref.strip():
            positional = [ref.strip()]
        elif ref.strip() and positional and positional[0] != ref.strip():
            raise CommandError(
                f"new placement name mismatch: ref token {ref!r} vs first positional {positional[0]!r}."
            )
        raw_eid = ctx.options.get(NEW_CONTEXT_OPTION_EXPLICIT_ID)
        explicit_id: UUID | None = raw_eid if isinstance(raw_eid, UUID) else None
        return ctrl._cmd_new_fmu_instance(positional, skw, explicit_id)

    def inspect(self, ctx: InspectContext, ref: str) -> InspectResult:
        ctrl = _require_synarius_controller(ctx.controller)
        obj = ctrl._resolve_ref(ref)
        el = ctrl._require_fmu_elementary(obj, command="inspect")
        try:
            cur = el.get("fmu.path")
        except KeyError:
            cur = None
        if cur is None or str(cur).strip() == "":
            raise CommandError(
                "inspect needs a non-empty fmu.path on the target "
                "(deprecated alternative: fmu inspect <pathTo.fmu>)."
            )
        path = str(cur).strip()
        try:
            data = inspect_fmu_path(path)
        except FmuInspectError as exc:
            raise CommandError(str(exc)) from exc
        if not isinstance(data, dict):
            data = {"value": data}
        tk = el.type_key if isinstance(el, ElementaryInstance) else str(getattr(el, "type_key", ""))
        return InspectResult(type_key=tk, ref=ref, raw=dict(data))

    def sync(self, ctx: SyncContext, ref: str) -> None:
        ctrl = _require_synarius_controller(ctx.controller)
        obj = ctrl._resolve_ref(ref)
        el = ctrl._require_fmu_elementary(obj, command="sync")
        opt = ctx.options
        skw: dict[str, str] = {}
        fr = opt.get("fmu_sync_from") or opt.get("from")
        pr = opt.get("fmu_sync_path") or opt.get("path")
        if fr is not None and str(fr).strip():
            skw["from"] = str(fr).strip()
        if pr is not None and str(pr).strip():
            skw["path"] = str(pr).strip()
        alt = ctrl._parse_optional_fmu_file_kw(skw)
        ctrl._fmu_sync_elementary_from_path(el, alternate_fmu_file=alt)


def inspect_result_to_json(res: InspectResult) -> str:
    """Serialize inspection result like legacy ``_fmu_inspect_path_json``."""
    return json.dumps(res.raw, indent=2, sort_keys=True, default=str)
