"""synarius_attr_config — options management module for Synarius.

Provides the metadata model, attribute projection, TOML persistence, and Qt
widget classes for local and global attribute configuration dialogs.

Layers
------
meta
    :class:`~synarius_attr_config.meta.OptionMeta` and
    :class:`~synarius_attr_config.meta.GuiHint` dataclasses.
    No Qt, no file I/O dependency.
projection
    :class:`~synarius_attr_config.projection.AttribViewModel` and
    :class:`~synarius_attr_config.projection.RegistryOverlayStore`.
    No Qt dependency.
persistence
    :class:`~synarius_attr_config.persistence.TomlPersistenceLayer`.
    No Qt dependency.
widgets
    :class:`~synarius_attr_config.widgets.AttribTableWidget`,
    :class:`~synarius_attr_config.widgets.AttribFormWidget`,
    :class:`~synarius_attr_config.widgets.OptionsMenuWidget`.
    Requires PySide6.
"""
from synarius_attr_config.meta import GuiHint, OptionMeta
from synarius_attr_config.persistence import TomlPersistenceLayer
from synarius_attr_config.projection import AttribViewModel, RegistryOverlayStore, ValidationResult

__all__ = [
    "OptionMeta",
    "GuiHint",
    "AttribViewModel",
    "ValidationResult",
    "RegistryOverlayStore",
    "TomlPersistenceLayer",
]
