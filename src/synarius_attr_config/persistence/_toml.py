from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


class TomlPersistenceLayer:
    """TOML-based persistence for global application configuration.

    Manages two files:

    * ``defaults.toml`` — ships with the application; read-only at runtime;
      schema reference and reset target.
    * ``settings.toml`` — user-specific overrides; written on *OK* in the
      global config dialog.

    Delta semantics
    ---------------
    ``settings.toml`` stores only keys that differ from ``defaults.toml``.
    An absent key always means "use the default".  A present key always means
    "user override".  Reset operations remove keys rather than writing default
    values — this invariant must not be broken.

    At load time both files are merged; ``settings.toml`` values win.
    A missing ``settings.toml`` is treated as empty (no exception).
    """

    def __init__(self, defaults_path: Path, settings_path: Path) -> None:
        self._defaults_path = defaults_path
        self._settings_path = settings_path
        self._defaults_cache: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _load_defaults(self) -> dict[str, Any]:
        if self._defaults_cache is not None:
            return self._defaults_cache
        if not self._defaults_path.exists():
            _log.warning("TomlPersistenceLayer: defaults file not found: %s", self._defaults_path)
            self._defaults_cache = {}
            return self._defaults_cache
        try:
            self._defaults_cache = tomllib.loads(
                self._defaults_path.read_text("utf-8")
            )
        except tomllib.TOMLDecodeError as exc:
            _log.warning("TomlPersistenceLayer: failed to parse defaults: %s", exc)
            self._defaults_cache = {}
        return self._defaults_cache

    def _load_settings(self) -> dict[str, Any]:
        if not self._settings_path.exists():
            return {}
        try:
            return tomllib.loads(self._settings_path.read_text("utf-8"))
        except tomllib.TOMLDecodeError as exc:
            _log.warning("TomlPersistenceLayer: failed to parse settings: %s", exc)
            return {}

    def load(self) -> dict[str, Any]:
        """Return merged defaults + settings (settings wins on conflict)."""
        merged = dict(self._load_defaults())
        merged.update(self._load_settings())
        return merged

    def default_value(self, key: str) -> Any:
        """Return the defaults.toml value for *key*, or ``None`` if absent."""
        return self._load_defaults().get(key)

    def has_default(self, key: str) -> bool:
        """True if *key* has an entry in defaults.toml."""
        return key in self._load_defaults()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, changes: dict[str, Any]) -> None:
        """Write *changes* as a delta to settings.toml.

        Existing settings not mentioned in *changes* are preserved.
        Only keys whose value differs from the default need to be in *changes*;
        callers are responsible for this invariant.
        """
        import tomli_w  # runtime import — keeps Layer 3 optional at import time

        current = self._load_settings()
        current.update(changes)
        self._settings_path.write_bytes(tomli_w.dumps(current).encode("utf-8"))

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_attribute(self, key: str) -> None:
        """Remove the override for *key* from settings.toml.

        Does NOT write the default value — key absence means "use default".
        """
        if not self._settings_path.exists():
            return
        import tomli_w

        data = self._load_settings()
        if key not in data:
            return
        del data[key]
        if data:
            self._settings_path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
        else:
            self._settings_path.unlink()

    def reset_group(self, keys: list[str]) -> None:
        """Remove override keys for a group from settings.toml in one write.

        Does NOT write default values — preserves delta semantics.
        """
        if not self._settings_path.exists():
            return
        import tomli_w

        data = self._load_settings()
        changed = False
        for key in keys:
            if key in data:
                del data[key]
                changed = True
        if not changed:
            return
        if data:
            self._settings_path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
        else:
            self._settings_path.unlink()

    def reset_all(self) -> None:
        """Delete settings.toml entirely; subsequent load() returns defaults only."""
        if self._settings_path.exists():
            self._settings_path.unlink()
