from __future__ import annotations

from synarius_core.controller import SynariusController
from synarius_core.model.syn_script_export import export_root_diagram_syn_text


def test_export_reload_roundtrip_minimal(tmp_path) -> None:
    a = SynariusController()
    a.execute("new Variable vx 10 20 1")
    a.execute("new Variable vy 10 40 1")
    a.execute("new BasicOperator + 50 30 name=op1")
    a.execute("new Connector vx op1 source_pin=out target_pin=in1")
    a.execute("new Connector vy op1 source_pin=out target_pin=in2")
    text = export_root_diagram_syn_text(a.model)
    p = tmp_path / "out.syn"
    p.write_text(text, encoding="utf-8")
    b = SynariusController()
    b.execute_script(p)
    names = {c.name for c in b.model.root.children if getattr(c, "name", None)}
    assert "vx" in names and "vy" in names and "op1" in names


def test_has_undoable_changes(tmp_path) -> None:
    c = SynariusController()
    assert not c.has_undoable_changes()
    c.execute("new Variable z 0 0 1")
    assert c.has_undoable_changes()
    empty = tmp_path / "empty.syn"
    empty.write_text("#\n", encoding="utf-8")
    c.execute(f'load "{empty}"')
    assert not c.has_undoable_changes()


def test_load_additive_script_replaces_diagram_not_merge(tmp_path) -> None:
    """Loading a script that only adds blocks must not keep the previous diagram on the cloned model."""
    from synarius_core.model import Variable

    ctl = SynariusController()
    ctl.execute("new Variable stale 1 2 1")
    p = tmp_path / "only_new.syn"
    p.write_text("new Variable fresh 3 4 1\n", encoding="utf-8")
    ctl.execute(f'load "{p}"')
    root_names = {c.name for c in ctl.model.root.children if isinstance(c, Variable)}
    assert "fresh" in root_names
    assert "stale" not in root_names
