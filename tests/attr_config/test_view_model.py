import pytest

from synarius_core.model.attribute_dict import AttributeEntry
from synarius_attr_config.meta import GuiHint, OptionMeta
from synarius_attr_config.projection import AttribViewModel, ValidationResult


def _entry(value, *, exposed=True, writable=True, bounds=None, enum_values=None, unit=""):
    return AttributeEntry.stored(
        value, exposed=exposed, writable=writable, bounds=bounds,
        enum_values=enum_values, unit=unit,
    )


def _om(**kw):
    return OptionMeta(**kw)


def _gh(display_name=""):
    return GuiHint(display_name=display_name)


def _vm(*entries, persistence=None):
    return AttribViewModel(list(entries), persistence=persistence)


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_keys_in_order(self):
        vm = _vm(
            ("gain", _entry(1.0), _om(), _gh("Gain")),
            ("offset", _entry(0.0), _om(), _gh("Offset")),
        )
        assert vm.keys == ["gain", "offset"]

    def test_initial_pending_equals_original(self):
        vm = _vm(("gain", _entry(2.0), _om(), _gh()))
        assert vm.pending_value("gain") == 2.0
        assert vm.changed_values() == {}
        assert not vm.has_pending_changes()

    def test_virtual_entry_reads_getter(self):
        backing = [42]
        entry = AttributeEntry.virtual(lambda: backing[0], exposed=True, writable=False)
        vm = AttribViewModel([("v", entry, _om(), _gh())])
        assert vm.pending_value("v") == 42


# ---------------------------------------------------------------------------
# Change tracking
# ---------------------------------------------------------------------------

class TestChangeTracking:
    def test_set_pending_marks_change(self):
        vm = _vm(("gain", _entry(1.0), _om(), _gh()))
        vm.set_pending("gain", 5.0)
        assert vm.changed_values() == {"gain": 5.0}
        assert vm.has_pending_changes()

    def test_unchanged_key_not_in_changed_values(self):
        vm = _vm(
            ("gain", _entry(1.0), _om(), _gh()),
            ("offset", _entry(0.0), _om(), _gh()),
        )
        vm.set_pending("gain", 3.0)
        assert "offset" not in vm.changed_values()

    def test_revert_pending(self):
        vm = _vm(("gain", _entry(1.0), _om(), _gh()))
        vm.set_pending("gain", 99.0)
        vm.revert_pending("gain")
        assert vm.changed_values() == {}

    def test_revert_all(self):
        vm = _vm(
            ("gain", _entry(1.0), _om(), _gh()),
            ("offset", _entry(0.0), _om(), _gh()),
        )
        vm.set_pending("gain", 5.0)
        vm.set_pending("offset", -1.0)
        vm.revert_all()
        assert vm.changed_values() == {}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_value_in_bounds_is_valid(self):
        vm = _vm(("gain", _entry(1.0, bounds=(0.0, 10.0)), _om(), _gh()))
        vm.set_pending("gain", 5.0)
        assert vm.validate("gain").ok

    def test_value_below_bounds_is_invalid(self):
        vm = _vm(("gain", _entry(1.0, bounds=(0.0, 10.0)), _om(), _gh()))
        vm.set_pending("gain", -1.0)
        result = vm.validate("gain")
        assert not result.ok
        assert "-1.0" in result.message

    def test_value_above_bounds_is_invalid(self):
        vm = _vm(("gain", _entry(1.0, bounds=(0.0, 10.0)), _om(), _gh()))
        vm.set_pending("gain", 11.0)
        assert not vm.validate("gain").ok

    def test_valid_enum_value(self):
        vm = _vm(("method", _entry("RK4", enum_values=["Euler", "RK4"]), _om(), _gh()))
        assert vm.validate("method").ok

    def test_invalid_enum_value(self):
        vm = _vm(("method", _entry("RK4", enum_values=["Euler", "RK4"]), _om(), _gh()))
        vm.set_pending("method", "INVALID")
        assert not vm.validate("method").ok

    def test_value_spec_runs(self):
        def must_be_positive(v):
            if v <= 0:
                raise ValueError("must be positive")
            return v
        entry = AttributeEntry.stored(1.0, writable=True, value_spec=must_be_positive)
        vm = AttribViewModel([("x", entry, _om(), _gh())])
        vm.set_pending("x", -5.0)
        assert not vm.validate("x").ok

    def test_has_errors_false_when_all_valid(self):
        vm = _vm(("gain", _entry(1.0, bounds=(0.0, 10.0)), _om(), _gh()))
        assert not vm.has_errors()

    def test_has_errors_true_when_any_invalid(self):
        vm = _vm(
            ("gain", _entry(1.0, bounds=(0.0, 10.0)), _om(), _gh()),
            ("offset", _entry(0.0, bounds=(-5.0, 5.0)), _om(), _gh()),
        )
        vm.set_pending("gain", 100.0)
        assert vm.has_errors()

    def test_bool_not_caught_by_numeric_bounds_check(self):
        vm = _vm(("flag", _entry(True, bounds=(0.0, 1.0)), _om(), _gh()))
        # bool values bypass the bounds check (bool is int subclass, but excluded)
        assert vm.validate("flag").ok


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

class TestDisplayHelpers:
    def test_display_name_from_gui_hint(self):
        vm = _vm(("gain", _entry(1.0), _om(), _gh("Gain Factor")))
        assert vm.display_name("gain") == "Gain Factor"

    def test_display_name_falls_back_to_key(self):
        vm = _vm(("gain", _entry(1.0), _om(), _gh("")))
        assert vm.display_name("gain") == "gain"

    def test_display_name_none_gui_hint_falls_back_to_key(self):
        vm = AttribViewModel([("gain", _entry(1.0), _om(), None)])
        assert vm.display_name("gain") == "gain"

    def test_effective_exposed_from_entry(self):
        vm = _vm(("x", _entry(1.0, exposed=True), OptionMeta(exposed_override=None), _gh()))
        assert vm.effective_exposed("x") is True

    def test_effective_exposed_override(self):
        vm = _vm(("x", _entry(1.0, exposed=True), OptionMeta(exposed_override=False), _gh()))
        assert vm.effective_exposed("x") is False

    def test_effective_writable_override(self):
        vm = _vm(("x", _entry(1.0, writable=False), OptionMeta(gui_writable_override=True), _gh()))
        assert vm.effective_writable("x") is True

    def test_unit_from_entry(self):
        vm = _vm(("x", _entry(1.0, unit="m/s"), _om(), _gh()))
        assert vm.unit("x") == "m/s"


# ---------------------------------------------------------------------------
# Reset (with stub persistence)
# ---------------------------------------------------------------------------

class _StubPersistence:
    def __init__(self, defaults):
        self._defaults = dict(defaults)
        self.removed_keys: list[str] = []
        self.removed_groups: list[list[str]] = []

    def default_value(self, key):
        return self._defaults.get(key)

    def has_default(self, key):
        return key in self._defaults

    def reset_attribute(self, key):
        self.removed_keys.append(key)

    def reset_group(self, keys):
        self.removed_groups.append(list(keys))


class TestReset:
    def test_reset_to_default_sets_pending_and_removes_key(self):
        pers = _StubPersistence({"gain": 1.0})
        vm = _vm(("gain", _entry(5.0), _om(), _gh()), persistence=pers)
        vm.set_pending("gain", 9.0)
        vm.reset_to_default("gain")
        assert vm.pending_value("gain") == 1.0
        assert "gain" in pers.removed_keys

    def test_reset_to_default_no_persistence_raises(self):
        vm = _vm(("gain", _entry(1.0), _om(), _gh()))
        with pytest.raises(RuntimeError):
            vm.reset_to_default("gain")

    def test_reset_to_default_missing_key_raises(self):
        pers = _StubPersistence({})
        vm = _vm(("gain", _entry(1.0), _om(), _gh()), persistence=pers)
        with pytest.raises(KeyError):
            vm.reset_to_default("gain")

    def test_reset_group_affects_only_keys_with_defaults(self):
        pers = _StubPersistence({"gain": 1.0})
        vm = _vm(
            ("gain", _entry(5.0), _om(), _gh()),
            ("offset", _entry(9.0), _om(), _gh()),
            persistence=pers,
        )
        vm.reset_group(["gain", "offset"])
        assert vm.pending_value("gain") == 1.0
        assert vm.pending_value("offset") == 9.0  # no default → unchanged
        assert pers.removed_groups == [["gain"]]

    def test_has_default_without_persistence(self):
        vm = _vm(("gain", _entry(1.0), _om(), _gh()))
        assert not vm.has_default("gain")
