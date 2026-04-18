from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from synarius_core.model.attribute_dict import AttributeEntry
from synarius_attr_config.meta import GuiHint, OptionMeta

if TYPE_CHECKING:
    from synarius_attr_config.projection._registry import RegistryOverlayStore


@runtime_checkable
class _PersistenceProtocol(Protocol):
    """Structural protocol satisfied by :class:`~synarius_attr_config.persistence.TomlPersistenceLayer`.

    Defined here so that Layer 2 (projection) imposes no import dependency on
    Layer 3 (persistence).  Any object with these four methods satisfies the
    protocol at runtime via structural subtyping.
    """

    def default_value(self, key: str) -> Any: ...
    def has_default(self, key: str) -> bool: ...
    def reset_attribute(self, key: str) -> None: ...
    def reset_group(self, keys: list[str]) -> None: ...


@dataclass
class ValidationResult:
    """Result of a single attribute validation check."""

    ok: bool
    message: str = ""


class AttribViewModel:
    """Projected attribute set for one dialog scope.

    Tracks the original value (at construction time), the pending (edited) value,
    and the validation state for each attribute.  Validation logic, change
    detection, and reset operations reside here — not in view classes.

    The *entries* list defines the projection: each element is a 4-tuple
    ``(key, entry, option_meta, gui_hint)`` for one visible attribute slot.
    Pass only the entries that should appear in the dialog (i.e. apply the
    projection criterion — local or global — before constructing the viewmodel).

    Parameters
    ----------
    entries
        Projected attribute slots.
    persistence
        Optional persistence layer.  Required for reset-to-default operations.
        Any object satisfying :class:`_PersistenceProtocol` is accepted.
    registry
        Optional i18n overlay store.  When present, ``display_name()`` first
        checks the registry before falling back to ``GuiHint.display_name``.
    obj_type
        Object-type string used as the registry namespace key.  Ignored when
        *registry* is ``None``.
    """

    def __init__(
        self,
        entries: list[tuple[str, AttributeEntry, OptionMeta | None, GuiHint | None]],
        persistence: _PersistenceProtocol | None = None,
        registry: RegistryOverlayStore | None = None,
        obj_type: str = "",
    ) -> None:
        self._entries: dict[str, tuple[AttributeEntry, OptionMeta | None, GuiHint | None]] = {
            key: (entry, om, gh) for key, entry, om, gh in entries
        }
        self._original: dict[str, Any] = {}
        self._pending: dict[str, Any] = {}
        self._persistence = persistence
        self._registry = registry
        self._obj_type = obj_type

        for key, entry, _om, _gh in entries:
            val = entry.getter() if entry.getter is not None else entry.value
            self._original[key] = val
            self._pending[key] = val

    # ------------------------------------------------------------------
    # Change tracking
    # ------------------------------------------------------------------

    def set_pending(self, key: str, value: Any) -> None:
        """Set the pending (edited) value for *key*."""
        self._pending[key] = value

    def revert_pending(self, key: str) -> None:
        """Discard the pending value for *key*; restore the original."""
        self._pending[key] = self._original[key]

    def revert_all(self) -> None:
        """Discard all pending changes."""
        for key in self._pending:
            self._pending[key] = self._original[key]

    def changed_values(self) -> dict[str, Any]:
        """Return a dict of only the attributes whose pending value differs from original."""
        return {k: v for k, v in self._pending.items() if v != self._original[k]}

    def has_pending_changes(self) -> bool:
        return bool(self.changed_values())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, key: str) -> ValidationResult:
        """Validate the current pending value for *key*.

        Checks in order: bounds, enum membership, value_spec.
        The first failing check determines the result.
        """
        entry, _om, _gh = self._entries[key]
        value = self._pending[key]

        if (
            entry.bounds is not None
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            lo, hi = entry.bounds
            if not (lo <= value <= hi):
                return ValidationResult(False, f"{value} not in [{lo}, {hi}]")

        if entry.enum_values is not None and value not in entry.enum_values:
            return ValidationResult(False, f"{value!r} is not one of {entry.enum_values}")

        if entry.value_spec is not None:
            try:
                entry.value_spec(value)
            except (TypeError, ValueError) as exc:
                return ValidationResult(False, str(exc))

        return ValidationResult(True)

    def has_errors(self) -> bool:
        """True if any pending value fails validation."""
        return any(not self.validate(k).ok for k in self._pending)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_to_default(self, key: str) -> None:
        """Reset *key* to its defaults.toml value.

        Sets the pending value to the default and removes the override key from
        settings.toml via the persistence layer.

        Raises
        ------
        RuntimeError
            When no persistence layer was provided.
        KeyError
            When *key* has no entry in defaults.toml.
        """
        if self._persistence is None:
            raise RuntimeError("reset_to_default requires a persistence layer")
        if not self._persistence.has_default(key):
            raise KeyError(f"No default value defined for {key!r}")
        self._pending[key] = self._persistence.default_value(key)
        self._persistence.reset_attribute(key)

    def reset_group(self, keys: list[str]) -> None:
        """Reset a group of attributes to their defaults.toml values.

        Only keys that have an entry in defaults.toml are affected.  Override
        keys are removed from settings.toml (not replaced with explicit default
        values — key absence means "use default").

        Raises
        ------
        RuntimeError
            When no persistence layer was provided.
        """
        if self._persistence is None:
            raise RuntimeError("reset_group requires a persistence layer")
        keys_with_defaults = [k for k in keys if self._persistence.has_default(k)]
        for k in keys_with_defaults:
            self._pending[k] = self._persistence.default_value(k)
        if keys_with_defaults:
            self._persistence.reset_group(keys_with_defaults)

    def default_value(self, key: str) -> Any:
        """Return the defaults.toml value for *key*, or ``None`` if unavailable."""
        if self._persistence is None:
            return None
        return self._persistence.default_value(key)

    def has_default(self, key: str) -> bool:
        if self._persistence is None:
            return False
        return self._persistence.has_default(key)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def display_name(self, key: str) -> str:
        """Return the display name for *key*.

        Lookup order: registry overlay → GuiHint.display_name → key.
        """
        _, _om, gh = self._entries[key]
        if self._registry is not None:
            overlay = self._registry.display_name(self._obj_type, key)
            if overlay:
                return overlay
        if gh is not None and gh.display_name:
            return gh.display_name
        return key

    def effective_exposed(self, key: str) -> bool:
        """Return the effective exposed flag, respecting OptionMeta.exposed_override."""
        entry, om, _ = self._entries[key]
        if om is not None and om.exposed_override is not None:
            return om.exposed_override
        return entry.exposed

    def effective_writable(self, key: str) -> bool:
        """Return the effective writable flag, respecting OptionMeta.gui_writable_override."""
        entry, om, _ = self._entries[key]
        if om is not None and om.gui_writable_override is not None:
            return om.gui_writable_override
        return entry.writable

    def unit(self, key: str) -> str:
        entry, _om, _gh = self._entries[key]
        return entry.unit

    def pending_value(self, key: str) -> Any:
        return self._pending[key]

    @property
    def keys(self) -> list[str]:
        """All attribute keys in this viewmodel, in insertion order."""
        return list(self._entries)
