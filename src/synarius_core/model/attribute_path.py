"""Hierarchical attribute path parsing for ``BaseObject.get`` / ``BaseObject.set``.

Path rules:
- Segments are separated by unescaped ``.``.
- Escape sequences:
  - ``\\.`` -> literal dot
  - ``\\\\`` -> literal backslash

Pin naming convention uses valid Python identifiers for segment names where possible; anything
else must use escapes (or be avoided).
"""

from __future__ import annotations

from typing import Any


def split_attribute_path(path: str) -> list[str]:
    """Split *path* into segments respecting ``\\`` escapes."""
    s = path.strip()
    if not s:
        return []

    parts: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in ".\\":
                buf.append(nxt)
                i += 2
                continue
        if ch == ".":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    if any(seg == "" for seg in parts):
        raise ValueError(f"Invalid attribute path (empty segment): {path!r}")
    return parts


def join_attribute_path(segments: list[str]) -> str:
    """Join segments into a dotted path, escaping dots and backslashes as needed."""

    def esc(seg: str) -> str:
        return seg.replace("\\", "\\\\").replace(".", "\\.")

    return ".".join(esc(s) for s in segments)


def deep_copy_mapping_tree(obj: Any) -> Any:
    """Deep-copy nested dicts and lists (e.g. ``fmu.variables``); other leaves are shared as-is."""
    if isinstance(obj, dict):
        return {k: deep_copy_mapping_tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_copy_mapping_tree(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(deep_copy_mapping_tree(v) for v in obj)
    return obj
