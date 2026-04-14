"""Tests for :class:`~synarius_core.plugins.element_type_registry.ElementTypeRegistry`."""

from __future__ import annotations

import unittest

from synarius_core.plugins.element_types import ElementTypeHandler, NewContext
from synarius_core.plugins.element_type_registry import ElementTypeRegistry
from synarius_core.plugins.registry import PluginRegistry


class _DummyHandler(ElementTypeHandler):
    type_key = "test.dummy"

    def new(self, ctx: NewContext, ref: str, args: list, kwargs: dict) -> object:
        return object()


class _DupHandler(ElementTypeHandler):
    type_key = "test.dummy"

    def new(self, ctx: NewContext, ref: str, args: list, kwargs: dict) -> object:
        return object()


class ElementTypeRegistryTest(unittest.TestCase):
    def test_register_and_get(self) -> None:
        r = ElementTypeRegistry()
        h = _DummyHandler()
        r.register(h)
        self.assertIs(r.get("test.dummy"), h)

    def test_duplicate_type_key_raises(self) -> None:
        r = ElementTypeRegistry()
        r.register(_DummyHandler())
        with self.assertRaises(ValueError):
            r.register(_DupHandler())

    def test_bundled_fmu_plugin_registers_std_and_fmuinstance_alias(self) -> None:
        reg = PluginRegistry()
        etr = ElementTypeRegistry()
        reg.register_element_handlers(etr)
        self.assertIn("std.FmuCoSimulation", etr.registered_keys())
        self.assertIn("FmuInstance", etr.registered_keys())
