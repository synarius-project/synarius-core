import sys
import tempfile
from pathlib import Path
import unittest


sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import MinimalController  # noqa: E402


class MinimalControllerProtocolTest(unittest.TestCase):
    def test_new_set_get_and_ls(self) -> None:
        ctl = MinimalController()
        created = ctl.execute("new Variable Speed")
        self.assertIsNotNone(created)

        listing = ctl.execute("ls")
        self.assertIn("Speed", listing or "")

        ctl.execute("set Speed.value 3.14")
        got = ctl.execute("get Speed.value")
        self.assertEqual(got, "3.14")

    def test_select_and_set_selection(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("new Variable B")
        ctl.execute("select A B")
        updated = ctl.execute("set @selection value 10")
        self.assertEqual(updated, "2")

    def test_cd_allows_elementary_object_context(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Elem")
        path = ctl.execute("cd Elem") or ""
        self.assertIn("Elem@", path)
        back = ctl.execute("cd ..") or ""
        self.assertIn("main@", back)

    def test_lsattr_shows_values_and_long_flags(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Speed")
        ctl.execute("set Speed.value 3.14")

        short_out = ctl.execute("lsattr") or ""
        self.assertIn("NAME", short_out)
        self.assertIn("updated_at", short_out)
        self.assertNotIn("|", short_out)
        self.assertNotIn("---", short_out)
        self.assertNotIn("=", short_out)
        self.assertIn("created_at", short_out)
        self.assertIn("+00:00", short_out)

        long_out = ctl.execute("lsattr -l") or ""
        self.assertIn("NAME", long_out)
        self.assertIn("VALUE", long_out)
        self.assertIn("VIRTUAL", long_out)
        self.assertIn("WRITABLE", long_out)
        self.assertIn("true", long_out)
        self.assertIn("false", long_out)
        self.assertNotIn("|", long_out)
        self.assertNotIn("---", long_out)
        self.assertNotIn("=", long_out)

    def test_lsattr_accepts_context_argument(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Speed")
        out = ctl.execute("lsattr Speed") or ""
        self.assertIn("NAME", out)
        self.assertIn("name", out)

    def test_load_script(self) -> None:
        ctl = MinimalController()
        script = "\n".join(
            [
                "new Variable V1",
                "set V1.value 1.5",
                "new BasicOperator + name=Op1",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "model.pyp"
            script_path.write_text(script, encoding="utf-8")
            result = ctl.execute(f'load "{script_path}"')
            self.assertTrue((result or "").startswith("loaded:"))
            self.assertIn("V1", ctl.execute("ls") or "")


if __name__ == "__main__":
    unittest.main()
