import logging
from pathlib import Path


from synarius_attr_config.projection import RegistryOverlayStore


def _write_registry(path: Path, data: dict) -> Path:
    import tomli_w
    path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
    return path


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestLoad:
    def test_missing_file_emits_warning(self, tmp_path, caplog):
        reg = RegistryOverlayStore()
        with caplog.at_level(logging.WARNING):
            reg.load(tmp_path / "nonexistent.toml")
        assert any("not found" in r.message for r in caplog.records)

    def test_missing_file_leaves_store_empty(self, tmp_path):
        reg = RegistryOverlayStore()
        reg.load(tmp_path / "nonexistent.toml")
        assert reg.display_name("Any", "gain") is None

    def test_malformed_toml_emits_warning(self, tmp_path, caplog):
        bad = tmp_path / "bad.toml"
        bad.write_text("not valid toml [[[", encoding="utf-8")
        reg = RegistryOverlayStore()
        with caplog.at_level(logging.WARNING):
            reg.load(bad)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_valid_file_loads(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "SolverBlock.gain": {"en": "Gain Factor"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        assert reg.display_name("SolverBlock", "gain") == "Gain Factor"


# ---------------------------------------------------------------------------
# Overlay lookup
# ---------------------------------------------------------------------------

class TestDisplayName:
    def test_qualified_key_lookup(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "SolverBlock.gain": {"en": "Gain Factor"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        assert reg.display_name("SolverBlock", "gain", "en") == "Gain Factor"

    def test_bare_key_lookup_when_no_qualified(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "gain": {"en": "Generic Gain"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        assert reg.display_name("AnyType", "gain") == "Generic Gain"

    def test_qualified_takes_precedence_over_bare(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "SolverBlock.gain": {"en": "Solver Gain"},
            "gain": {"en": "Generic Gain"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        assert reg.display_name("SolverBlock", "gain") == "Solver Gain"

    def test_language_fallback_to_en(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "SolverBlock.gain": {"en": "Gain Factor"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        assert reg.display_name("SolverBlock", "gain", "de") == "Gain Factor"

    def test_returns_none_for_unknown_key(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "SolverBlock.gain": {"en": "Gain Factor"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        assert reg.display_name("SolverBlock", "offset") is None

    def test_empty_obj_type_uses_bare_key(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "gain": {"en": "Gain"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        assert reg.display_name("", "gain") == "Gain"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidateAgainst:
    def test_no_warning_when_all_keys_match(self, tmp_path, caplog):
        path = _write_registry(tmp_path / "reg.toml", {
            "Solver.gain": {"en": "Gain"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        with caplog.at_level(logging.WARNING):
            reg.validate_against({("Solver", "gain")})
        assert not any("orphan" in r.message.lower() for r in caplog.records)

    def test_orphan_key_emits_warning(self, tmp_path, caplog):
        path = _write_registry(tmp_path / "reg.toml", {
            "Unknown.foo": {"en": "Unknown"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        with caplog.at_level(logging.WARNING):
            reg.validate_against({("Solver", "gain")})
        assert any("orphan" in r.message.lower() for r in caplog.records)

    def test_validate_does_not_raise(self, tmp_path):
        path = _write_registry(tmp_path / "reg.toml", {
            "Orphan.key": {"en": "Orphan"},
        })
        reg = RegistryOverlayStore()
        reg.load(path)
        reg.validate_against(set())  # must not raise
