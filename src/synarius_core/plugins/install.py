"""Install a packaged plugin from a .zip archive into a ``Plugins`` container directory."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path


def install_plugin_archive(archive_path: Path, plugins_container: Path) -> Path:
    """Extract *archive_path* into *plugins_container*.

    The archive **must** contain exactly one top-level directory (the plugin package root
    with ``pluginDescription.xml`` inside after extraction). Returns the resolved path to
    that directory.

    Raises ``ValueError`` if the layout is ambiguous or ``archive_path`` is not a zip file.
    """
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise ValueError(f"Archive not found: {archive_path}")
    plugins_container = Path(plugins_container)
    plugins_container.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as zf:
        names = [n for n in zf.namelist() if n.strip("/")]
        if not names:
            raise ValueError("Empty archive")
        tops = {n.split("/")[0].rstrip("/") for n in names if n.strip("/")}
        tops.discard("")
        if len(tops) != 1:
            raise ValueError("Archive must contain exactly one top-level directory (one plugin package).")
        top = tops.pop()
        target_dir = (plugins_container / top).resolve()
        if target_dir.exists() and any(target_dir.iterdir()):
            raise ValueError(f"Refusing to extract: target directory already exists and is not empty: {target_dir}")
        zf.extractall(plugins_container)

    out = (plugins_container / top).resolve()
    if not (out / "pluginDescription.xml").is_file():
        raise ValueError(f"Extracted folder missing pluginDescription.xml: {out}")
    return out


def _resolve_distribution_paths(
    archive_path: Path,
    plugins_container: Path,
    lib_container: Path | None,
) -> tuple[Path, Path, Path | None]:
    ap = Path(archive_path)
    if not ap.is_file():
        raise ValueError(f"Archive not found: {ap}")
    pc = Path(plugins_container)
    pc.mkdir(parents=True, exist_ok=True)
    lc: Path | None = None
    if lib_container is not None:
        lc = Path(lib_container)
        lc.mkdir(parents=True, exist_ok=True)
    return ap, pc, lc


def _extract_zip_to_dir(archive_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(dest_dir)


def _single_top_level_extracted_dir(extract_root: Path) -> Path:
    children = [p for p in extract_root.iterdir() if p.is_dir() and p.name != "__MACOSX"]
    if len(children) != 1:
        raise ValueError("Archive must contain exactly one top-level directory.")
    return children[0]


def _is_standalone_plugin_package(root: Path) -> bool:
    return (root / "pluginDescription.xml").is_file()


def _copy_tree_as_named_sibling(src: Path, container: Path, *, kind: str) -> Path:
    dest = (container / src.name).resolve()
    if dest.exists():
        label = "Plugin" if kind == "plugin" else "Library"
        raise ValueError(f"{label} directory already exists: {dest}")
    shutil.copytree(src, dest)
    return dest


def _install_subdirs_from_folder(
    src_folder: Path,
    dest_container: Path,
    out_list: list[Path],
    *,
    kind: str,
) -> None:
    if not src_folder.is_dir():
        return
    for sub in sorted(src_folder.iterdir(), key=lambda p: p.name.lower()):
        if not sub.is_dir():
            continue
        out_list.append(_copy_tree_as_named_sibling(sub, dest_container, kind=kind))


def _require_bundle_produced_paths(out: dict[str, list[Path]]) -> None:
    if not out["plugins"] and not out["lib"]:
        raise ValueError(
            "Unrecognized bundle layout (expected plugin folder or root with Plugins/ and/or Lib/)."
        )


def install_distribution_archive(
    archive_path: Path,
    *,
    plugins_container: Path,
    lib_container: Path | None = None,
) -> dict[str, list[Path]]:
    """Install a host “bundle” zip (Studio / manual layout).

    The archive **must** contain exactly one top-level directory. That directory may be:

    * **Single plugin package** (contains ``pluginDescription.xml``) → copied into *plugins_container*.
    * **Distribution root** with ``Plugins/`` and/or ``Lib/`` subfolders → each immediate
      subdirectory of those folders is copied into *plugins_container* / *lib_container*
      respectively (same layout as a development tree).

    *lib_container* is optional; omit or pass ``None`` to skip installing libraries.

    Returns ``{"plugins": [...], "lib": [...]}`` with created destination paths.

    Raises ``ValueError`` if the layout is unknown or a destination folder already exists.
    """
    ap, pc, lc = _resolve_distribution_paths(archive_path, plugins_container, lib_container)
    out: dict[str, list[Path]] = {"plugins": [], "lib": []}

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _extract_zip_to_dir(ap, tdp)
        root = _single_top_level_extracted_dir(tdp)

        if _is_standalone_plugin_package(root):
            out["plugins"].append(_copy_tree_as_named_sibling(root, pc, kind="plugin"))
            return out

        _install_subdirs_from_folder(root / "Plugins", pc, out["plugins"], kind="plugin")
        if lc is not None:
            _install_subdirs_from_folder(root / "Lib", lc, out["lib"], kind="library")
        _require_bundle_produced_paths(out)

    return out
