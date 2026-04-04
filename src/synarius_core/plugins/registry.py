"""Discover and load Synarius plugins (pluginDescription.xml + isolated Python entry)."""

from __future__ import annotations

import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _discover_default_plugin_container_dirs() -> list[Path]:
    """Return ``Plugins/`` directories found by walking upward from this package."""
    here = Path(__file__).resolve().parent
    cur = here.parent
    found: list[Path] = []
    for _ in range(14):
        cand = cur / "Plugins"
        if cand.is_dir():
            found.append(cand.resolve())
        if cur.parent == cur:
            break
        cur = cur.parent
    return found


def _src_adjacent_plugins_dir() -> Path | None:
    """``synarius-core/Plugins`` sibling of ``src/`` (editable / source-tree installs).

    Walking upward from ``site-packages`` never reaches the repo ``Plugins`` folder; without this,
    ``runtime:fmu`` is missing and FMU blocks never step (outputs stay at zero).
    """
    here = Path(__file__).resolve()
    try:
        src_dir = here.parents[2]
    except IndexError:
        return None
    cand = (src_dir.parent / "Plugins").resolve()
    return cand if cand.is_dir() else None


def enumerate_plugin_package_dirs(
    *,
    extra_plugin_containers: Iterable[Path] | None = None,
    scan_builtin_plugin_directories: bool = True,
) -> list[Path]:
    """List plugin package roots (each folder contains ``pluginDescription.xml``).

    *extra_plugin_containers* are additional ``Plugins``-style directories whose immediate
    subdirectories are scanned (same layout as the host ``Plugins/`` folder).
    """
    containers: list[Path] = []
    seen_ct: set[Path] = set()
    if scan_builtin_plugin_directories:
        # Wheel / site-packages: bundled plugins live as subdirs of this package (e.g. FmuRuntime/)
        # next to registry.py. ``cur / "Plugins"`` alone misses lowercase ``plugins/`` on Linux.
        reg_pkg = Path(__file__).resolve().parent
        if reg_pkg.is_dir():
            try:
                has_manifest = any(
                    p.is_dir() and (p / "pluginDescription.xml").is_file() for p in reg_pkg.iterdir()
                )
            except OSError:
                has_manifest = False
            if has_manifest:
                r = reg_pkg.resolve()
                if r not in seen_ct:
                    seen_ct.add(r)
                    containers.append(r)
        adj = _src_adjacent_plugins_dir()
        if adj is not None:
            r = adj.resolve()
            if r not in seen_ct:
                seen_ct.add(r)
                containers.append(r)
        for c in _discover_default_plugin_container_dirs():
            r = c.resolve()
            if r not in seen_ct:
                seen_ct.add(r)
                containers.append(r)
    for raw in extra_plugin_containers or ():
        p = Path(raw).resolve()
        if p.is_dir() and p not in seen_ct:
            seen_ct.add(p)
            containers.append(p)

    pkg_seen: set[Path] = set()
    out: list[Path] = []
    for base in containers:
        for child in sorted(base.iterdir(), key=lambda x: x.name.lower()):
            if not child.is_dir():
                continue
            if not (child / "pluginDescription.xml").is_file():
                continue
            cr = child.resolve()
            if cr in pkg_seen:
                continue
            pkg_seen.add(cr)
            out.append(cr)
    return out


@dataclass(frozen=True, slots=True)
class ParsedPluginManifest:
    folder: Path
    name: str
    version: str
    module: str
    class_name: str
    capabilities: tuple[str, ...]


def parse_plugin_manifest(folder: Path) -> ParsedPluginManifest:
    xml_path = folder / "pluginDescription.xml"
    tree = ET.parse(xml_path)
    r = tree.getroot()
    if r.tag != "PluginDescription":
        raise ValueError(f"Expected PluginDescription root in {xml_path}")
    name = ""
    version = ""
    module = ""
    class_name = ""
    caps: list[str] = []
    for child in r:
        if child.tag == "Name":
            name = _text(child)
        elif child.tag == "Version":
            version = _text(child)
        elif child.tag == "Module":
            module = _text(child)
        elif child.tag == "Class":
            class_name = _text(child)
        elif child.tag == "Capabilities":
            for cap_el in child:
                if cap_el.tag != "Capability":
                    continue
                t = _text(cap_el)
                if t:
                    caps.append(t)
    if not name:
        raise ValueError("Missing <Name>")
    if not module:
        raise ValueError("Missing <Module>")
    if not class_name:
        raise ValueError("Missing <Class>")
    py_file = folder / f"{module}.py"
    if not py_file.is_file():
        raise ValueError(f"Module file missing: {py_file.name}")
    return ParsedPluginManifest(
        folder=folder.resolve(),
        name=name,
        version=version,
        module=module,
        class_name=class_name,
        capabilities=tuple(caps),
    )


def load_plugin_instance(folder: Path, manifest: ParsedPluginManifest) -> Any:
    """Import *manifest*'s module from *folder* with an isolated qualified name, then instantiate *class_name*."""
    py_path = folder / f"{manifest.module}.py"
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", manifest.name)
    qual = f"synarius_plugin_{safe}_{hash(py_path) & 0xFFFFFFF:08x}"
    spec = importlib.util.spec_from_file_location(qual, py_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load module spec for {py_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[qual] = mod
    spec.loader.exec_module(mod)
    cls = getattr(mod, manifest.class_name, None)
    if cls is None:
        raise ValueError(f"Class {manifest.class_name!r} not found in {manifest.module}.py")
    return cls()


@dataclass(slots=True)
class LoadedPlugin:
    manifest: ParsedPluginManifest
    instance: Any
    source_folder: Path


class PluginRegistry:
    """Load plugins from host ``Plugins/`` (and optional extra containers); register by capability (first wins)."""

    def __init__(
        self,
        *,
        extra_plugin_containers: Iterable[Path] | None = None,
        scan_builtin_plugin_directories: bool = True,
        defer_initial_load: bool = False,
    ) -> None:
        self._extra = list(Path(p).resolve() for p in (extra_plugin_containers or ()) if Path(p).is_dir())
        self._scan_builtin = bool(scan_builtin_plugin_directories)
        self.load_errors: list[str] = []
        self.capability_warnings: list[str] = []
        self._loaded: list[LoadedPlugin] = []
        self._by_capability: dict[str, LoadedPlugin] = {}
        if not defer_initial_load:
            self.reload()

    def set_extra_plugin_containers(self, paths: Iterable[Path]) -> None:
        """Replace additional ``Plugins/``-style container directories (resolved, existing dirs only)."""
        out: list[Path] = []
        for raw in paths or ():
            p = Path(raw).resolve()
            try:
                if p.is_dir():
                    out.append(p)
            except OSError:
                continue
        self._extra = out

    @classmethod
    def load_default(cls) -> PluginRegistry:
        return cls()

    def reload(self) -> None:
        self.load_errors.clear()
        self.capability_warnings.clear()
        self._loaded.clear()
        self._by_capability.clear()
        folders = enumerate_plugin_package_dirs(
            extra_plugin_containers=self._extra,
            scan_builtin_plugin_directories=self._scan_builtin,
        )
        for folder in folders:
            try:
                manifest = parse_plugin_manifest(folder)
            except Exception as exc:
                self.load_errors.append(f"{folder}: {exc}")
                continue
            try:
                instance = load_plugin_instance(folder, manifest)
            except Exception as exc:
                self.load_errors.append(f"{folder}: {exc}")
                continue
            lp = LoadedPlugin(manifest=manifest, instance=instance, source_folder=folder.resolve())
            self._loaded.append(lp)
            for cap in manifest.capabilities:
                if cap in self._by_capability:
                    prev = self._by_capability[cap].manifest.name
                    self.capability_warnings.append(
                        f"Capability {cap!r} already registered by {prev!r}; ignoring duplicate from {manifest.name!r}."
                    )
                    continue
                self._by_capability[cap] = lp

    @property
    def loaded_plugins(self) -> tuple[LoadedPlugin, ...]:
        return tuple(self._loaded)

    def plugin_for_capability(self, capability: str) -> LoadedPlugin | None:
        return self._by_capability.get(capability)

    def iter_compile_passes(self, stage: str = "compile") -> list[Any]:
        """Return plugin-provided compiler pass objects for *stage*, sorted by ``name``."""
        passes: list[Any] = []
        for lp in self._loaded:
            inst = lp.instance
            collected: list[Any] = []
            fn = getattr(inst, "compile_passes", None)
            if callable(fn):
                raw = fn()
                if raw:
                    collected = list(raw)
            elif all(hasattr(inst, a) for a in ("run", "stage", "name")):
                collected = [inst]
            for p in collected:
                p_stage = getattr(p, "stage", stage)
                if p_stage != stage:
                    continue
                passes.append(p)

        passes.sort(key=lambda p: str(getattr(p, "name", "")))
        return passes


def run_plugin_compile_passes(ctx: Any, registry: PluginRegistry, *, stage: str = "compile") -> Any:
    """Invoke each plugin compile pass for *stage* (sorted by pass ``name``)."""
    for p in registry.iter_compile_passes(stage):
        p.run(ctx)
    return ctx
