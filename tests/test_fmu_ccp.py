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

from synarius_core.controller import CommandError, SynariusController  # noqa: E402
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


# Suppresses ``new FmuInstance`` auto-fill when tests need a placeholder ``fmu_path`` without a file.
_DUMMY_FMU_PORT_KW = (
    '[{"name":"u","value_reference":1,'
    '"causality":"input","variability":"continuous","data_type":"float"}]'
)


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
        ctl = SynariusController()
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
            ctl = SynariusController()
            out = ctl.execute(f"fmu inspect {shlex.quote(str(p))}")
            self.assertIsNotNone(out)
            payload = json.loads(out or "{}")
            self.assertEqual(payload["model_identifier"], "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_sync_from_kw_updates_path_like_legacy_bind(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_bind.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = SynariusController()
            hn = (
                ctl.execute(
                    "new FmuInstance bx fmu_path=/tmp/x.fmu "
                    f"fmu_ports={shlex.quote(_DUMMY_FMU_PORT_KW)}"
                )
                or ""
            ).strip()
            ctl.execute(f"sync {shlex.quote(hn)} from={shlex.quote(str(p))}")
            obj = ctl._resolve_ref(hn)
            self.assertTrue(str(obj.get("fmu.path")).replace("\\", "/").endswith("_tmp_bind.fmu"))
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_sync_path_kw_matches_legacy_reload(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_reload.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = SynariusController()
            hn = (
                ctl.execute(
                    "new FmuInstance bz fmu_path=/tmp/none.fmu "
                    f"fmu_ports={shlex.quote(_DUMMY_FMU_PORT_KW)}"
                )
                or ""
            ).strip()
            ctl.execute(f"sync {shlex.quote(hn)} path={shlex.quote(str(p))}")
            obj = ctl._resolve_ref(hn)
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_fmu_bind_subcommand_removed(self) -> None:
        ctl = SynariusController()
        with self.assertRaises(CommandError) as ctx:
            ctl.execute("fmu bind @main")
        self.assertIn("removed", str(ctx.exception).lower())

    def test_inspect_ref_uses_fmu_path(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_inspect_ref.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = SynariusController()
            hn = (ctl.execute(f"new FmuInstance ir fmu_path={shlex.quote(str(p))}") or "").strip()
            out = ctl.execute(f"inspect {shlex.quote(hn)}")
            payload = json.loads(out or "{}")
            self.assertEqual(payload["model_identifier"], "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_sync_from_kw_matches_fmu_bind(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_sync.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = SynariusController()
            hn = (
                ctl.execute(
                    "new FmuInstance sy fmu_path=/tmp/x.fmu "
                    f"fmu_ports={shlex.quote(_DUMMY_FMU_PORT_KW)}"
                )
                or ""
            ).strip()
            ctl.execute(f"sync {shlex.quote(hn)} from={shlex.quote(str(p))}")
            obj = ctl._resolve_ref(hn)
            self.assertTrue(str(obj.get("fmu.path")).replace("\\", "/").endswith("_tmp_sync.fmu"))
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_sync_path_kw_matches_fmu_reload(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_sync_path.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = SynariusController()
            hn = (
                ctl.execute(
                    "new FmuInstance sz fmu_path=/tmp/none.fmu "
                    f"fmu_ports={shlex.quote(_DUMMY_FMU_PORT_KW)}"
                )
                or ""
            ).strip()
            ctl.execute(f"sync {shlex.quote(hn)} path={shlex.quote(str(p))}")
            obj = ctl._resolve_ref(hn)
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
        finally:
            p.unlink(missing_ok=True)

    def test_inspect_rejects_non_fmu_target(self) -> None:
        ctl = SynariusController()
        ctl.execute("new Variable v_only")
        with self.assertRaises(CommandError) as ctx:
            ctl.execute("inspect v_only")
        self.assertIn("not available", str(ctx.exception).lower())

    def test_sync_rejects_conflicting_from_and_path(self) -> None:
        ctl = SynariusController()
        hn = (
            ctl.execute(
                "new FmuInstance cf fmu_path=/tmp/a.fmu "
                f"fmu_ports={shlex.quote(_DUMMY_FMU_PORT_KW)}"
            )
            or ""
        ).strip()
        with self.assertRaises(CommandError) as ctx:
            ctl.execute(f"sync {shlex.quote(hn)} from=/tmp/a.fmu path=/tmp/b.fmu")
        self.assertIn("different", str(ctx.exception).lower())

    def test_new_fmu_instance_autofills_when_ports_and_variables_omitted(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_autofill.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = SynariusController()
            hn = (ctl.execute(f"new FmuInstance af fmu_path={shlex.quote(str(p))}") or "").strip()
            obj = ctl._resolve_ref(hn)
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
            self.assertEqual(obj.get("fmu.path"), str(p))
            pmap = obj.get("pin")
            self.assertIn("u", pmap)
            self.assertIn("y", pmap)
            vars_ = obj.get("fmu.variables")
            self.assertEqual(len(vars_), 3)
            self.assertEqual({v["name"] for v in vars_}, {"u", "y", "internal"})
        finally:
            p.unlink(missing_ok=True)

    def test_new_fmu_autofill_matches_post_hoc_bind(self) -> None:
        """Minimal ``new`` uses the same bind merge as ``sync``/inspect (no ``fmu_ports`` / ``fmu_variables``)."""
        p = Path(__file__).resolve().parent / "_tmp_autofill_eq.fmu"
        p.write_bytes(_make_fmu_zip_bytes())
        try:
            ctl = SynariusController()
            hn_new = (ctl.execute(f"new FmuInstance n0 fmu_path={shlex.quote(str(p))}") or "").strip()
            hn_seed = (
                ctl.execute(
                    f"new FmuInstance n1 fmu_path={shlex.quote(str(p))} "
                    f"fmu_ports={shlex.quote(_DUMMY_FMU_PORT_KW)}"
                )
                or ""
            ).strip()
            ctl.execute(f"sync {shlex.quote(hn_seed)}")
            a = ctl._resolve_ref(hn_new)
            b = ctl._resolve_ref(hn_seed)
            self.assertEqual(a.get("pin"), b.get("pin"))
            self.assertEqual(a.get("fmu.variables"), b.get("fmu.variables"))
        finally:
            p.unlink(missing_ok=True)

    def test_execute_script_resolves_relative_fmu_path_for_autofill(self) -> None:
        d = Path(__file__).resolve().parent / "_tmp_syn_fmu_dir"
        d.mkdir(exist_ok=True)
        fmu = d / "mini.fmu"
        script = d / "load.syn"
        try:
            fmu.write_bytes(_make_fmu_zip_bytes())
            script.write_text(
                "new FmuInstance rel0 fmu_path=mini.fmu\n",
                encoding="utf-8",
            )
            ctl = SynariusController()
            ctl.execute_script(script)
            obj = ctl._resolve_ref("rel0")
            self.assertEqual(obj.get("fmu.model_identifier"), "Mini")
            self.assertEqual(obj.get("fmu.path"), "mini.fmu")
        finally:
            try:
                fmu.unlink(missing_ok=True)
                script.unlink(missing_ok=True)
                d.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
