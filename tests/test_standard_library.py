"""Bundled FMF Standard Library layout (Add, Sub, Mul, Div)."""

from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.standard_library import STANDARD_LIBRARY_VERSION, standard_library_root  # noqa: E402


class StandardLibraryTest(unittest.TestCase):
    def test_root_and_manifest(self) -> None:
        root = standard_library_root()
        self.assertTrue(root.is_dir())
        manifest = root / "libraryDescription.xml"
        self.assertTrue(manifest.is_file())
        tree = ET.parse(manifest)
        el = tree.getroot()
        self.assertEqual(el.tag, "LibraryDescription")
        self.assertEqual(el.attrib.get("fmfVersion"), "0.1")
        self.assertEqual(el.attrib.get("name"), "std")
        self.assertEqual(el.attrib.get("version"), STANDARD_LIBRARY_VERSION)

    def test_four_arithmetic_elements(self) -> None:
        root = standard_library_root()
        manifest = ET.parse(root / "libraryDescription.xml")
        ns_hint = ".//"  # no namespaces in v0.1 sample
        elements = manifest.findall(f"{ns_hint}Element")
        ids = {e.attrib.get("id") for e in elements}
        self.assertEqual(ids, {"Add", "Sub", "Mul", "Div"})

        for eid in ("Add", "Sub", "Mul", "Div"):
            ed = root / "components" / eid / "elementDescription.xml"
            self.assertTrue(ed.is_file(), msg=str(ed))
            elem = ET.parse(ed).getroot()
            self.assertEqual(elem.attrib.get("id"), eid)
            fmfl_el = next((n for n in elem.iter() if n.tag == "FMFL"), None)
            self.assertIsNotNone(fmfl_el)
            fmfl_name = eid.lower()
            self.assertIn(fmfl_name, (fmfl_el.attrib.get("file") or ""))

            beh = root / "components" / eid / "behavior" / f"{fmfl_name}.fmfl"
            self.assertTrue(beh.is_file(), msg=str(beh))
            text = beh.read_text(encoding="utf-8")
            self.assertIn("fmfl 0.1", text)
            self.assertIn("equations:", text)
            self.assertIn("out = in0", text)

            for size in (16, 32, 64):
                icon = root / "components" / eid / "resources" / "icons" / f"{fmfl_name}_{size}.svg"
                self.assertTrue(icon.is_file(), msg=str(icon))


if __name__ == "__main__":
    unittest.main()
