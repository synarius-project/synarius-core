"""Plugin discovery, loading, and host integration (see ``docs/specifications/plugin_api.rst``)."""

from synarius_core.plugins.install import install_distribution_archive, install_plugin_archive
from synarius_core.plugins.registry import (
    LoadedPlugin,
    ParsedPluginManifest,
    PluginRegistry,
    enumerate_plugin_package_dirs,
    load_plugin_instance,
    parse_plugin_manifest,
    run_plugin_compile_passes,
)

__all__ = [
    "LoadedPlugin",
    "ParsedPluginManifest",
    "PluginRegistry",
    "enumerate_plugin_package_dirs",
    "install_distribution_archive",
    "install_plugin_archive",
    "load_plugin_instance",
    "parse_plugin_manifest",
    "run_plugin_compile_passes",
]
