"""Stateless CCP parsing and light resolution helpers (no controller ``self``)."""

from __future__ import annotations

import ast
from typing import Any, Callable
from uuid import UUID

from synarius_core.model import ComplexInstance
from synarius_core.variable_naming import InvalidVariableNameError

from .errors import CommandError


def parse_kw_pairs(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        out[key] = value
    return out


def set_target_attr(obj: Any, attr: str, value: Any) -> None:
    try:
        obj.set(attr, value)
        return
    except KeyError:
        pass
    except InvalidVariableNameError:
        raise
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    if hasattr(obj, attr):
        setattr(obj, attr, value)
        return
    raise CommandError(f"Attribute '{attr}' not found on target.")


def get_target_attr(obj: Any, attr: str) -> Any:
    try:
        return obj.get(attr)
    except KeyError:
        pass
    if hasattr(obj, attr):
        return getattr(obj, attr)
    raise CommandError(f"Attribute '{attr}' not found on target.")


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_value(raw: str) -> Any:
    text = raw.strip()
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if text.startswith("[") and text.endswith("]"):
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            pass
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def optional_float_kw(kwargs: dict[str, str], key: str) -> float | None:
    if key not in kwargs:
        return None
    raw = kwargs[key]
    if raw is None or str(raw).strip() == "":
        return None
    v = parse_value(str(raw))
    if isinstance(v, bool):
        raise CommandError(f"{key} must be numeric.")
    if isinstance(v, (int, float)):
        return float(v)
    raise CommandError(f"{key} must be numeric.")


def parse_fmu_ports_kw(kwargs: dict[str, str]) -> list[dict[str, Any]] | None:
    if "fmu_ports" not in kwargs:
        return None
    raw = kwargs["fmu_ports"]
    if raw is None or str(raw).strip() == "":
        return None
    try:
        parsed = ast.literal_eval(str(raw))
    except (ValueError, SyntaxError) as exc:
        raise CommandError(f"fmu_ports must be a Python literal list: {exc}") from exc
    if not isinstance(parsed, list):
        raise CommandError("fmu_ports must be a list.")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise CommandError(f"fmu_ports[{i}] must be a dict.")
        out.append(dict(item))
    return out


def parse_fmu_variables_kw(kwargs: dict[str, str]) -> list[dict[str, Any]] | None:
    if "fmu_variables" not in kwargs:
        return None
    raw = kwargs["fmu_variables"]
    if raw is None or str(raw).strip() == "":
        return None
    try:
        parsed = ast.literal_eval(str(raw))
    except (ValueError, SyntaxError) as exc:
        raise CommandError(f"fmu_variables must be a Python literal list: {exc}") from exc
    if not isinstance(parsed, list):
        raise CommandError("fmu_variables must be a list.")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise CommandError(f"fmu_variables[{i}] must be a dict.")
        out.append(dict(item))
    return out


def parse_fmu_extra_meta_kw(kwargs: dict[str, str]) -> dict[str, Any] | None:
    if "fmu_extra_meta" not in kwargs:
        return None
    raw = kwargs["fmu_extra_meta"]
    if raw is None or str(raw).strip() == "":
        return None
    try:
        parsed = ast.literal_eval(str(raw))
    except (ValueError, SyntaxError) as exc:
        raise CommandError(f"fmu_extra_meta must be a Python literal dict: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CommandError("fmu_extra_meta must be a dict.")
    return dict(parsed)


def try_resolve_global_object_ref(ref: str, find_by_id: Callable[[UUID], Any | None]) -> Any | None:
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
    return find_by_id(oid)


def resolve_path_segment(container: Any, segment: str) -> Any | None:
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
