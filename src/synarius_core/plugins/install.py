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
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise ValueError(f"Archive not found: {archive_path}")
    plugins_container = Path(plugins_container)
    plugins_container.mkdir(parents=True, exist_ok=True)
    if lib_container is not None:
        lib_container = Path(lib_container)
        lib_container.mkdir(parents=True, exist_ok=True)

    out: dict[str, list[Path]] = {"plugins": [], "lib": []}

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(tdp)
        children = [p for p in tdp.iterdir() if p.is_dir() and p.name != "__MACOSX"]
        if len(children) != 1:
            raise ValueError("Archive must contain exactly one top-level directory.")
        root = children[0]

        if (root / "pluginDescription.xml").is_file():
            dest = (plugins_container / root.name).resolve()
            if dest.exists():
                raise ValueError(f"Plugin directory already exists: {dest}")
            shutil.copytree(root, dest)
            out["plugins"].append(dest)
            return out

        plug_src = root / "Plugins"
        lib_src = root / "Lib"
        if plug_src.is_dir():
            for sub in sorted(plug_src.iterdir(), key=lambda p: p.name.lower()):
                if not sub.is_dir():
                    continue
                dest = (plugins_container / sub.name).resolve()
                if dest.exists():
                    raise ValueError(f"Plugin directory already exists: {dest}")
                shutil.copytree(sub, dest)
                out["plugins"].append(dest)
        if lib_container is not None and lib_src.is_dir():
            for sub in sorted(lib_src.iterdir(), key=lambda p: p.name.lower()):
                if not sub.is_dir():
                    continue
                dest = (lib_container / sub.name).resolve()
                if dest.exists():
                    raise ValueError(f"Library directory already exists: {dest}")
                shutil.copytree(sub, dest)
                out["lib"].append(dest)

        if not out["plugins"] and not out["lib"]:
            raise ValueError(
                "Unrecognized bundle layout (expected plugin folder or root with Plugins/ and/or Lib/)."
            )
    return out
