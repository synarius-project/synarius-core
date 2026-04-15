import sys
import unittest
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import CommandError, SynariusController  # noqa: E402
from synarius_core.library import LibraryCatalog  # noqa: E402


class LibraryCatalogTest(unittest.TestCase):
    def test_loads_std_arithmetic_and_lookup_elements(self) -> None:
        cat = LibraryCatalog.load_default()
        self.assertGreaterEqual(len(cat.libraries), 1)
        std = next(lib for lib in cat.libraries if lib.name == "std")
        ids = {e.element_id for e in std.elements}
        self.assertGreaterEqual(ids, {"Add", "Sub", "Mul", "Div"})
        self.assertGreaterEqual(ids, {"Kennwert", "Kennlinie", "Kennfeld"})

    def test_console_tree_navigation(self) -> None:
        ctl = SynariusController()
        self.assertEqual((ctl.execute("cd @libraries") or "").strip(), "@libraries")

        listing = ctl.execute("ls") or ""
        self.assertIn("std", listing)

        self.assertTrue((ctl.execute("cd std") or "").startswith("@libraries/std"))
        elist = ctl.execute("ls") or ""
        for eid in ("Add", "Sub", "Mul", "Div"):
            self.assertIn(eid, elist)

        path = ctl.execute("cd Add") or ""
        self.assertIn("Add", path)
        self.assertIn("@libraries/std", path)

        attrs = ctl.execute("lsattr") or ""
        self.assertIn("element_id", attrs)
        self.assertIn("Add", attrs)
        self.assertIn("LIB.ELEMENT", attrs)

    def test_new_rejected_under_libraries(self) -> None:
        ctl = SynariusController()
        ctl.execute("cd @libraries/std")
        with self.assertRaises(CommandError):
            ctl.execute("new Variable X")


if __name__ == "__main__":
    unittest.main()
