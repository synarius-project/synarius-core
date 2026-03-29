import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.controller import CommandError, MinimalController  # noqa: E402
from synarius_core.model import Variable  # noqa: E402


class UndoRedoMvTrashTest(unittest.TestCase):
    def test_set_undo_redo(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable X")
        ctl.execute("set X.value 7")
        self.assertEqual(ctl.execute("get X.value"), "7")
        ctl.execute("undo")
        self.assertEqual(ctl.execute("get X.value"), "None")
        ctl.execute("redo")
        self.assertEqual(ctl.execute("get X.value"), "7")

    def test_undo_num_steps(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("set A.value 1")
        ctl.execute("set A.value 2")
        ctl.execute("set A.value 3")
        ctl.execute("undo 2")
        self.assertEqual(ctl.execute("get A.value"), "1")

    def test_new_command_undo_moves_to_trash_redo_restores(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Z")
        self.assertEqual(len(ctl._undo_stack), 1)
        ctl.execute("undo")
        z_vars = [n for n in ctl.model.iter_objects() if isinstance(n, Variable) and n.name == "Z"]
        self.assertEqual(len(z_vars), 1)
        self.assertTrue(ctl.model.is_in_trash_subtree(z_vars[0]))
        ctl.execute("redo")
        z2 = [n for n in ctl.model.iter_objects() if isinstance(n, Variable) and n.name == "Z"]
        self.assertEqual(len(z2), 1)
        self.assertFalse(ctl.model.is_in_trash_subtree(z2[0]))

    def test_del_soft_then_undo(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable Q")
        q = next(n for n in ctl.model.iter_objects() if isinstance(n, Variable) and n.name == "Q")
        h = q.hash_name
        ctl.execute(f"del {h}")
        self.assertTrue(ctl.model.is_in_trash_subtree(q))
        ctl.execute("undo")
        self.assertFalse(ctl.model.is_in_trash_subtree(q))

    def test_mv_undo(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable M")
        m = next(n for n in ctl.model.iter_objects() if isinstance(n, Variable) and n.name == "M")
        ctl.execute(f"mv {m.hash_name} @main/trash")
        self.assertTrue(ctl.model.is_in_trash_subtree(m))
        ctl.execute("undo")
        self.assertFalse(ctl.model.is_in_trash_subtree(m))

    def test_load_clears_undo_stack(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable L")
        self.assertEqual(len(ctl._undo_stack), 1)
        script = "new Variable R\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.syn"
            p.write_text(script, encoding="utf-8")
            ctl.execute(f'load "{p}"')
        self.assertEqual(len(ctl._undo_stack), 0)
        self.assertEqual(len(ctl._redo_stack), 0)

    def test_max_undo_depth_drops_oldest(self) -> None:
        ctl = MinimalController(max_undo_depth=2)
        ctl.execute("new Variable U")
        ctl.execute("set U.value 10")
        ctl.execute("set U.value 20")
        ctl.execute("set U.value 30")
        self.assertEqual(len(ctl._undo_stack), 2)
        ctl.execute("undo 2")
        self.assertEqual(ctl.execute("get U.value"), "10")

    def test_select_undo(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable S1")
        ctl.execute("new Variable S2")
        ctl.execute("select S1")
        ctl.execute("select S2")
        self.assertEqual(len(ctl.selection), 1)
        ctl.execute("undo")
        self.assertEqual(len(ctl.selection), 1)
        self.assertEqual(ctl.selection[0].name, "S1")

    def test_del_mixed_trash_and_live_raises(self) -> None:
        ctl = MinimalController()
        ctl.execute("new Variable A")
        ctl.execute("new Variable B")
        a = next(n for n in ctl.model.iter_objects() if isinstance(n, Variable) and n.name == "A")
        ctl.execute(f"del {a.hash_name}")
        ctl.execute("select B")
        ctl.execute(f"select {a.hash_name} B")
        with self.assertRaises(CommandError):
            ctl.execute("del @selected")


if __name__ == "__main__":
    unittest.main()
