from __future__ import annotations

import logging
import tomllib
from pathlib import Path

_log = logging.getLogger(__name__)


class RegistryOverlayStore:
    """Optional non-structural i18n and user-preference overlay store.

    Loads a TOML registry file and applies display-name overlays on top of
    ``GuiHint.display_name`` values at query time.  All errors are logged at
    WARNING level; no exception ever propagates to the caller.

    TOML file format
    ----------------
    Each section is keyed by ``"ObjType.attr_key"`` (or bare ``"attr_key"``
    for type-independent overrides).  Sub-keys are BCP 47 language tags::

        ["SolverBlock.gain"]
        en = "Gain Factor"
        de = "Verstärkungsfaktor"

        ["SolverBlock.enabled"]
        en = "Solver Enabled"

    Validation
    ----------
    :meth:`validate_against` checks every loaded key against a known set of
    ``(obj_type, attr_key)`` pairs and emits a WARNING for each orphan.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}

    def load(self, path: Path) -> None:
        """Load (or reload) the registry from *path*.

        A missing file emits a WARNING and leaves the store empty.
        A malformed TOML emits a WARNING with the parse error details.
        """
        if not path.exists():
            _log.warning("RegistryOverlayStore: registry file not found: %s", path)
            return
        try:
            raw = tomllib.loads(path.read_text("utf-8"))
        except tomllib.TOMLDecodeError as exc:
            _log.warning("RegistryOverlayStore: failed to parse %s: %s", path, exc)
            return
        if not isinstance(raw, dict):
            _log.warning("RegistryOverlayStore: top-level value in %s is not a table", path)
            return
        loaded: dict[str, dict[str, str]] = {}
        for key, val in raw.items():
            if not isinstance(val, dict):
                _log.warning("RegistryOverlayStore: value for key %r is not a table (ignored)", key)
                continue
            loaded[key] = {lang: str(name) for lang, name in val.items()}
        self._data = loaded

    def display_name(
        self,
        obj_type: str,
        attr_key: str,
        lang: str = "en",
    ) -> str | None:
        """Return the overlay display name for ``obj_type.attr_key`` in *lang*.

        Lookup order:

        1. ``"ObjType.attr_key"`` qualified key.
        2. Bare ``"attr_key"`` unqualified key.

        Returns ``None`` when no overlay exists; the caller should fall back to
        ``GuiHint.display_name``.
        """
        qualified = f"{obj_type}.{attr_key}" if obj_type else attr_key
        for lookup_key in (qualified, attr_key):
            entry = self._data.get(lookup_key)
            if entry:
                name = entry.get(lang) or entry.get("en")
                if name:
                    return name
        return None

    def validate_against(self, known_pairs: set[tuple[str, str]]) -> None:
        """Emit a WARNING for each registry key that has no matching attribute.

        *known_pairs* is a set of ``(obj_type, attr_key)`` tuples representing
        all currently registered configurable attributes.
        """
        known_qualified = {f"{ot}.{ak}" for ot, ak in known_pairs}
        known_bare = {ak for _ot, ak in known_pairs}
        for key in self._data:
            if key not in known_qualified and key not in known_bare:
                _log.warning(
                    "RegistryOverlayStore: orphan key %r has no matching attribute", key
                )
