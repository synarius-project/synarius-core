"""Integration: bundled ``runtime:fmu`` plugin + FMPy loads a real FMI 2 CS FMU and steps."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.dataflow_sim import SimpleRunEngine  # noqa: E402
from synarius_core.model import Connector, Model, Variable, elementary_fmu_block  # noqa: E402
from synarius_core.plugins.registry import PluginRegistry  # noqa: E402


def _fmpy_cs_imports_ok() -> bool:
    try:
        from fmpy import read_model_description  # noqa: F401
        from fmpy.fmi2 import FMU2Slave  # noqa: F401

        try:
            from fmpy.util import extract  # noqa: F401
        except ImportError:
            from fmpy import extract  # noqa: F401
    except ImportError:
        return False
    return True


def _bouncing_ball_fmu_path() -> Path:
    base = Path(__file__).resolve().parent / "fixtures" / "fmu"
    if sys.platform == "win32":
        plat = "win64"
    elif sys.platform.startswith("linux"):
        plat = "linux64"
    elif sys.platform == "darwin":
        plat = "darwin64"
    else:
        return Path()
    p = base / plat / "BouncingBall.fmu"
    if p.is_file():
        return p
    alt = base / "BouncingBall.fmu"
    return alt if alt.is_file() else Path()


def _bundled_plugins_root() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "synarius_core" / "plugins"


def _fmu_runtime_diagnostics(ctx: object) -> list[str]:
    return [d for d in getattr(ctx, "diagnostics", []) if isinstance(d, str) and d.startswith("FMU runtime:")]


class FmuFmpyIntegrationTest(unittest.TestCase):
    def test_bouncing_ball_load_and_step(self) -> None:
        if importlib.util.find_spec("fmpy") is None or not _fmpy_cs_imports_ok():
            self.skipTest("fmpy (FMI 2 CS stack) not available; install optional extra synarius-core[fmu]")
        fmu_path = _bouncing_ball_fmu_path()
        if not fmu_path.is_file():
            self.skipTest(f"No BouncingBall.fmu fixture for this host ({sys.platform})")

        root = _bundled_plugins_root()
        if not (root / "FmuRuntime" / "pluginDescription.xml").is_file():
            self.skipTest("Plugins/FmuRuntime not in tree")

        reg = PluginRegistry(extra_plugin_containers=[root], scan_builtin_plugin_directories=False)
        lp = reg.plugin_for_capability("runtime:fmu")
        self.assertIsNotNone(lp)

        model = Model.new("main")
        out = Variable(name="out", type_key="t", value=0.0)
        bb = elementary_fmu_block(
            name="bb",
            type_key="std.FmuCoSimulation",
            fmu_path=str(fmu_path.resolve()),
            fmi_version="2.0",
            fmu_type="CoSimulation",
            model_identifier="BouncingBall",
            fmu_ports=[
                {"name": "h", "causality": "output", "data_type": "float", "value_reference": 0},
            ],
        )
        model.attach(bb, parent=model.root, reserve_existing=False, remap_ids=False)
        model.attach(out, parent=model.root, reserve_existing=False, remap_ids=False)
        assert bb.id is not None and out.id is not None
        model.attach(
            Connector(
                name="wire_h",
                source_instance_id=bb.id,
                source_pin="h",
                target_instance_id=out.id,
                target_pin="in",
            ),
            parent=model.root,
            reserve_existing=False,
            remap_ids=False,
        )

        eng = SimpleRunEngine(model, dt_s=0.02, plugin_registry=reg)
        try:
            eng.init()
            ctx = eng.context
            self.assertFalse(
                any("not installed" in d.lower() for d in _fmu_runtime_diagnostics(ctx)),
                msg=_fmu_runtime_diagnostics(ctx),
            )
            self.assertFalse(
                any(
                    k in d.lower()
                    for d in _fmu_runtime_diagnostics(ctx)
                    for k in ("failed", "missing", "cannot read", "extract failed", "instantiate/setup")
                ),
                msg=_fmu_runtime_diagnostics(ctx),
            )

            before = float(out.value)
            for _ in range(12):
                eng.step()
            after = float(out.value)
            self.assertFalse(
                any(
                    "step failed" in d.lower()
                    for d in _fmu_runtime_diagnostics(ctx)
                ),
                msg=_fmu_runtime_diagnostics(ctx),
            )
            self.assertNotAlmostEqual(before, after, places=5)
        finally:
            eng.close()


if __name__ == "__main__":
    unittest.main()
