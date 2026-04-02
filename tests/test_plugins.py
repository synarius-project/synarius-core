"""Plugin registry, compile pipeline hooks, and zip install."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim import DataflowCompilePass, SimpleRunEngine, SimulationContext  # noqa: E402
from synarius_core.model import Model  # noqa: E402
from synarius_core.plugins import (  # noqa: E402
    PluginRegistry,
    install_distribution_archive,
    install_plugin_archive,
    run_plugin_compile_passes,
)


def _write_stub_plugin(pkg: Path) -> None:
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "pluginDescription.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<PluginDescription>
  <Name>StubCompile</Name>
  <Version>0.1</Version>
  <Module>entry</Module>
  <Class>StubPlugin</Class>
  <Capabilities>
    <Capability>backend:python</Capability>
  </Capabilities>
</PluginDescription>
""",
        encoding="utf-8",
    )
    (pkg / "entry.py").write_text(
        '''class _Pass:
    name = "stub_pass"
    stage = "compile"
    def run(self, ctx):
        ctx.diagnostics.append("stub_compile_ran")
        return ctx

class StubPlugin:
    def compile_passes(self):
        return [_Pass()]
''',
        encoding="utf-8",
    )


class PluginRegistryTest(unittest.TestCase):
    def test_loads_plugin_and_skips_duplicate_capability(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plug_container = Path(td) / "Plugins"
            plug_container.mkdir(parents=True, exist_ok=True)
            first = plug_container / "a_first"
            second = plug_container / "b_second"
            _write_stub_plugin(first)
            second.mkdir(parents=True, exist_ok=True)
            (second / "pluginDescription.xml").write_text(
                (first / "pluginDescription.xml").read_text(encoding="utf-8").replace("StubCompile", "StubTwo"),
                encoding="utf-8",
            )
            (second / "entry.py").write_text((first / "entry.py").read_text(encoding="utf-8"), encoding="utf-8")

            reg = PluginRegistry(
                extra_plugin_containers=[plug_container],
                scan_builtin_plugin_directories=False,
            )
        self.assertEqual(len(reg.loaded_plugins), 2)
        self.assertIsNotNone(reg.plugin_for_capability("backend:python"))
        self.assertTrue(any("duplicate" in w.lower() for w in reg.capability_warnings))

    def test_compile_pass_runs_via_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plug_container = Path(td) / "Plugins"
            plug_container.mkdir(parents=True, exist_ok=True)
            _write_stub_plugin(plug_container / "only")

            reg = PluginRegistry(
                extra_plugin_containers=[plug_container],
                scan_builtin_plugin_directories=False,
            )
            model = Model.new("main")
            ctx = SimulationContext(model=model)
            DataflowCompilePass().run(ctx)
            run_plugin_compile_passes(ctx, reg)
            self.assertTrue(any("stub_compile_ran" in m for m in ctx.diagnostics))


def _bundled_plugins_root() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "synarius_core" / "plugins"


class FmuRuntimeBundledPluginTest(unittest.TestCase):
    def test_bundled_fmu_runtime_registers_runtime_fmu(self) -> None:
        root = _bundled_plugins_root()
        if not (root / "FmuRuntime" / "pluginDescription.xml").is_file():
            self.skipTest("Plugins/FmuRuntime not in tree")
        reg = PluginRegistry(
            extra_plugin_containers=[root],
            scan_builtin_plugin_directories=False,
        )
        lp = reg.plugin_for_capability("runtime:fmu")
        self.assertIsNotNone(lp)
        assert lp is not None
        self.assertEqual(lp.manifest.name, "FmuRuntime")

    def test_fmu_runtime_init_fmu_reports_missing_fmpy(self) -> None:
        if importlib.util.find_spec("fmpy") is not None:
            self.skipTest("fmpy is installed; skipping missing-dependency diagnostic test")
        root = _bundled_plugins_root()
        if not (root / "FmuRuntime" / "pluginDescription.xml").is_file():
            self.skipTest("Plugins/FmuRuntime not in tree")
        reg = PluginRegistry(
            extra_plugin_containers=[root],
            scan_builtin_plugin_directories=False,
        )
        lp = reg.plugin_for_capability("runtime:fmu")
        self.assertIsNotNone(lp)
        assert lp is not None
        ctx = SimulationContext(model=Model.new("main"))
        lp.instance.init_fmu(ctx)
        self.assertTrue(any("fmpy" in m.lower() for m in ctx.diagnostics))


class SimpleRunEnginePluginTest(unittest.TestCase):
    def test_init_invokes_plugin_compile_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            plug_container = Path(td) / "Plugins"
            plug_container.mkdir(parents=True, exist_ok=True)
            _write_stub_plugin(plug_container / "eng")

            reg = PluginRegistry(
                extra_plugin_containers=[plug_container],
                scan_builtin_plugin_directories=False,
            )
            eng = SimpleRunEngine(Model.new("main"), plugin_registry=reg)
            eng.init()
            self.assertTrue(any("stub_compile_ran" in m for m in eng.context.diagnostics))


class InstallDistributionZipTest(unittest.TestCase):
    def test_bundle_with_plugins_and_lib_subfolders(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            bundle = work / "bundle_root"
            plug_pkg = bundle / "Plugins" / "pack_a"
            _write_stub_plugin(plug_pkg)
            lib_root = bundle / "Lib" / "mylib"
            lib_root.mkdir(parents=True, exist_ok=True)
            (lib_root / "libraryDescription.xml").write_text(
                '''<?xml version="1.0" encoding="UTF-8"?>
<LibraryDescription fmfVersion="0.1" name="mylib" version="1.0">
  <Description>test</Description>
  <Vendor>X</Vendor>
  <elements/>
</LibraryDescription>
''',
                encoding="utf-8",
            )
            zip_path = work / "dist.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                for f in bundle.rglob("*"):
                    if f.is_file():
                        arc = f.relative_to(bundle.parent)
                        zf.write(f, arc.as_posix())

            dest_plug = work / "out" / "Plugins"
            dest_lib = work / "out" / "Lib"
            summary = install_distribution_archive(
                zip_path, plugins_container=dest_plug, lib_container=dest_lib
            )
            self.assertEqual(len(summary["plugins"]), 1)
            self.assertEqual(len(summary["lib"]), 1)
            self.assertTrue((summary["plugins"][0] / "pluginDescription.xml").is_file())
            self.assertTrue((summary["lib"][0] / "libraryDescription.xml").is_file())


class InstallPluginZipTest(unittest.TestCase):
    def test_install_single_top_level_folder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            pkg = work / "bundle" / "zipped_plugin"
            _write_stub_plugin(pkg)
            zip_path = work / "plugin.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.write(pkg / "pluginDescription.xml", "zipped_plugin/pluginDescription.xml")
                zf.write(pkg / "entry.py", "zipped_plugin/entry.py")

            dest = work / "Plugins"
            dest.mkdir(parents=True, exist_ok=True)
            out = install_plugin_archive(zip_path, dest)
            self.assertTrue((out / "pluginDescription.xml").is_file())


if __name__ == "__main__":
    unittest.main()
