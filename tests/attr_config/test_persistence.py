import tomllib

import pytest

from synarius_attr_config.persistence import TomlPersistenceLayer


@pytest.fixture()
def tmp_layer(tmp_path):
    import tomli_w

    defaults = {"gain": 1.0, "enabled": True, "method": "RK4", "name": "default"}
    defaults_path = tmp_path / "defaults.toml"
    settings_path = tmp_path / "settings.toml"
    defaults_path.write_bytes(tomli_w.dumps(defaults).encode("utf-8"))
    return TomlPersistenceLayer(defaults_path, settings_path), defaults_path, settings_path


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

class TestLoad:
    def test_load_returns_defaults_when_no_settings(self, tmp_layer):
        layer, _d, _s = tmp_layer
        data = layer.load()
        assert data["gain"] == 1.0
        assert data["enabled"] is True

    def test_load_merges_settings_over_defaults(self, tmp_layer):
        import tomli_w
        layer, _d, settings_path = tmp_layer
        settings_path.write_bytes(tomli_w.dumps({"gain": 5.0}).encode("utf-8"))
        data = layer.load()
        assert data["gain"] == 5.0
        assert data["enabled"] is True  # from defaults

    def test_missing_defaults_file_logs_warning_and_returns_empty(self, tmp_path, caplog):
        import logging
        layer = TomlPersistenceLayer(
            tmp_path / "nonexistent_defaults.toml",
            tmp_path / "settings.toml",
        )
        with caplog.at_level(logging.WARNING):
            data = layer.load()
        assert data == {}
        assert any("not found" in r.message for r in caplog.records)

    def test_missing_settings_file_is_silent(self, tmp_layer):
        layer, _d, _s = tmp_layer
        # No exception; just returns defaults
        data = layer.load()
        assert data is not None


# ---------------------------------------------------------------------------
# has_default / default_value
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_has_default_for_known_key(self, tmp_layer):
        layer, _d, _s = tmp_layer
        assert layer.has_default("gain")

    def test_has_default_false_for_unknown_key(self, tmp_layer):
        layer, _d, _s = tmp_layer
        assert not layer.has_default("nonexistent")

    def test_default_value(self, tmp_layer):
        layer, _d, _s = tmp_layer
        assert layer.default_value("gain") == 1.0

    def test_default_value_unknown_returns_none(self, tmp_layer):
        layer, _d, _s = tmp_layer
        assert layer.default_value("nonexistent") is None


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

class TestWrite:
    def test_write_creates_settings_file(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        assert settings_path.exists()
        data = tomllib.loads(settings_path.read_text("utf-8"))
        assert data["gain"] == 7.0

    def test_write_delta_only(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        data = tomllib.loads(settings_path.read_text("utf-8"))
        assert "enabled" not in data  # not in changes
        assert "method" not in data

    def test_write_preserves_existing_settings(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        layer.write({"method": "Euler"})
        data = tomllib.loads(settings_path.read_text("utf-8"))
        assert data["gain"] == 7.0
        assert data["method"] == "Euler"


# ---------------------------------------------------------------------------
# reset_attribute
# ---------------------------------------------------------------------------

class TestResetAttribute:
    def test_reset_attribute_removes_key(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        layer.reset_attribute("gain")
        if settings_path.exists():
            data = tomllib.loads(settings_path.read_text("utf-8"))
            assert "gain" not in data

    def test_reset_attribute_deletes_file_when_empty(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        layer.reset_attribute("gain")
        assert not settings_path.exists()

    def test_reset_attribute_missing_settings_is_silent(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        # No settings file — should not raise
        layer.reset_attribute("gain")

    def test_reset_attribute_does_not_write_default_value(self, tmp_layer):
        """Key absence = use default; default value must never appear in settings."""
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        layer.reset_attribute("gain")
        if settings_path.exists():
            data = tomllib.loads(settings_path.read_text("utf-8"))
            assert "gain" not in data


# ---------------------------------------------------------------------------
# reset_group
# ---------------------------------------------------------------------------

class TestResetGroup:
    def test_reset_group_removes_all_keys(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0, "method": "Euler"})
        layer.reset_group(["gain", "method"])
        assert not settings_path.exists()

    def test_reset_group_preserves_unrelated_keys(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0, "name": "my_model"})
        layer.reset_group(["gain"])
        data = tomllib.loads(settings_path.read_text("utf-8"))
        assert "gain" not in data
        assert data["name"] == "my_model"

    def test_reset_group_empty_list_is_noop(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        layer.reset_group([])
        assert settings_path.exists()


# ---------------------------------------------------------------------------
# reset_all
# ---------------------------------------------------------------------------

class TestResetAll:
    def test_reset_all_deletes_settings_file(self, tmp_layer):
        layer, _d, settings_path = tmp_layer
        layer.write({"gain": 7.0})
        layer.reset_all()
        assert not settings_path.exists()

    def test_load_after_reset_all_returns_defaults_only(self, tmp_layer):
        layer, _d, _s = tmp_layer
        layer.write({"gain": 99.0})
        layer.reset_all()
        data = layer.load()
        assert data["gain"] == 1.0

    def test_reset_all_missing_file_is_silent(self, tmp_layer):
        layer, _d, _s = tmp_layer
        layer.reset_all()  # no settings file exists yet — should not raise
