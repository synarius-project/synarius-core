"""FMU inspection, bind, and controller ``fmu`` subcommands."""

from __future__ import annotations

import io
import json
import shlex
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import CommandError, MinimalController  # noqa: E402
from synarius_core.fmu.bind import bind_fmu_inspection_to_elementary, scalar_variables_to_fmu_ports  # noqa: E402
from synarius_core.fmu.inspection import inspect_fmu_bytes, parse_model_description_xml  # noqa: E402
from synarius_core.model import ElementaryInstance  # noqa: E402

_MINIMAL_MD = b"""<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription
  fmiVersion="2.0"
  guid="{test-guid}"
  modelName="Mini"
  description="desc"
  author="auth"
  version="1"
  generationTool="gt">
  <CoSimulation modelIdentifier="Mini" canHandleVariableCommunicationStepSize="true"/>
  <DefaultExperiment startTime="0" stopTime="1" stepSize="0.01"/>
  <ModelVariables>
    <ScalarVariable name="u" valueReference="1" causality="input" variability="continuous">
      <Real start="0"/>
    </ScalarVariable>
    <ScalarVariable name="y" valueReference="2" causality="output" variability="continuous">
      <Real/>
    </ScalarVariable>
    <ScalarVariable name="internal" valueReference="3" causality="local" variability="continuous">
      <Real/>
    </ScalarVariable>
  </ModelVariables>
</fmiModelDescription>
"""


def _make_fmu_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("modelDescription.xml", _MINIMAL_MD)
    return buf.getvalue()


class FmuInspectBindTest(unittest.TestCase):
    def test_parse_and_inspect_bytes(self) -> None:
        data = inspect_fmu_bytes(_make_fmu_zip_bytes())
        self.assertEqual(data["fmi_version"], "2.0")
        self.assertEqual(data["guid"], "{test-guid}")
        self.assertEqual(data["model_identifier"], "Mini")
        self.assertEqual(data["fmu_type"], "CoSimulation")
        self.assertEqual(data["step_size_hint"], 0.01)
        names = [v["name"] for v in data["scalar_variables"]]
        self.assertEqual(names, ["u", "y", "internal"])

    def test_scalar_variables_to_fmu_ports_skips_non_io(self) -> None:
        data = parse_model_description_xml(_MINIMAL_MD)
        ports = scalar_variables_to_fmu_ports(data["scalar_variables"])
        self.assertEqual({p["name"] for p in ports}, {"u", "y"})

    def test_bind_updates_fmu_and_pins(self) -> None:
        ctl = MinimalController()
        ports = '[{"name":"old","value_reference":99,"causality":"input","data_type":"float"}]'
        hn = (
            ctl.execute(f"new FmuInstance blk fmu_path=/tmp/placeholder.fmu fmu_ports={shlex.quote(ports)}")
            or ""
        ).strip()
        obj = ctl._resolve_ref(hn)
        self.assertIsInstance(obj, ElementaryInstance)
        data = inspect_fmu_bytes(_make_fmu_zip_bytes())
        bind_fmu_inspection_to_elementary(obj, data, library_pin_seed=None, path_override=None)
        self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
        self.assertEqual(len(obj.get("fmu.variables")), 3)
        pmap = obj.get("pin")
        self.assertIn("u", pmap)
        self.assertIn("y", pmap)
        self.assertEqual(pmap["u"].get("direction"), "IN")
        self.assertEqual(pmap["y"].get("direction"), "OUT")


class FmuControllerCommandsTest(unittest.TestCase):
    def test_fmu_inspect_returns_json(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_mini.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = MinimalController()
            out = ctl.execute(f"fmu inspect {shlex.quote(str(p))}")
            self.assertIsNotNone(out)
            payload = json.loads(out or "{}")
            self.assertEqual(payload["model_identifier"], "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_fmu_bind_from_kw_updates_path(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_bind.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = MinimalController()
            hn = (ctl.execute("new FmuInstance bx fmu_path=/tmp/x.fmu") or "").strip()
            ctl.execute(f"fmu bind {shlex.quote(hn)} from={shlex.quote(str(p))}")
            obj = ctl._resolve_ref(hn)
            self.assertTrue(str(obj.get("fmu.path")).replace("\\", "/").endswith("_tmp_bind.fmu"))
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_fmu_reload_with_path_kw(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_reload.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = MinimalController()
            hn = (ctl.execute("new FmuInstance bz fmu_path=/tmp/none.fmu") or "").strip()
            ctl.execute(f"fmu reload {shlex.quote(hn)} path={shlex.quote(str(p))}")
            obj = ctl._resolve_ref(hn)
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_fmu_bind_requires_path_or_from(self) -> None:
        ctl = MinimalController()
        hn = (ctl.execute("new FmuInstance e2 fmu_path=/no/such/file.fmu") or "").strip()
        with self.assertRaises(CommandError):
            ctl.execute(f"fmu bind {shlex.quote(hn)}")


if __name__ == "__main__":
    unittest.main()
