from dataclasses import fields


from synarius_attr_config.meta import GuiHint, OptionMeta


class TestOptionMetaDefaults:
    def test_defaults(self):
        om = OptionMeta()
        assert om.global_ is False
        assert om.global_path == ""
        assert om.local is True
        assert om.order is None
        assert om.exposed_override is None
        assert om.gui_writable_override is None

    def test_explicit_values(self):
        om = OptionMeta(global_=True, global_path="Sim/Solver", order=3)
        assert om.global_ is True
        assert om.global_path == "Sim/Solver"
        assert om.order == 3


class TestGuiHintDefaults:
    def test_defaults(self):
        gh = GuiHint()
        assert gh.display_name == ""
        assert gh.widget_type_override is None
        assert gh.decimal_precision is None

    def test_explicit_values(self):
        gh = GuiHint(display_name="Gain Factor", decimal_precision=4)
        assert gh.display_name == "Gain Factor"
        assert gh.decimal_precision == 4


class TestFieldDisjointness:
    def test_option_meta_and_gui_hint_share_no_fields(self):
        om_fields = {f.name for f in fields(OptionMeta)}
        gh_fields = {f.name for f in fields(GuiHint)}
        assert om_fields.isdisjoint(gh_fields), (
            f"OptionMeta and GuiHint share fields: {om_fields & gh_fields}; "
            "roles must be strictly disjoint"
        )
