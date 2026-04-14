"""Lightweight CCP navigation trees for ``@plugins`` and ``@types`` (``ls``, ``cd``, ``get``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from synarius_core.model.attribute_dict import AttributeDict

if TYPE_CHECKING:
    from synarius_core.plugins.element_type_registry import ElementTypeRegistry


class CcpAliasNode:
    """Tree node with ``children``, ``name``, ``attribute_dict``, and ``get_child`` (CCP-compatible)."""

    __slots__ = ("_name", "parent", "children", "attribute_dict", "_node_type")

    def __init__(self, *, name: str, parent: CcpAliasNode | None, node_type: str) -> None:
        self._name = name
        self.parent = parent
        self.children: list[CcpAliasNode] = []
        self.attribute_dict = AttributeDict()
        self._node_type = node_type
        self.attribute_dict["type"] = node_type
        self.attribute_dict.set_virtual(
            "name",
            getter=lambda: self._name,
            setter=None,
            writable=False,
        )

    @property
    def name(self) -> str:
        return self._name

    def get_child(self, segment: str) -> CcpAliasNode | None:
        for ch in self.children:
            if ch.name == segment:
                return ch
        return None


def build_plugins_nav_root(loaded: tuple[Any, ...]) -> CcpAliasNode:
    """Build ``@plugins`` from :attr:`~synarius_core.plugins.registry.PluginRegistry.loaded_plugins`."""
    root = CcpAliasNode(name="plugins", parent=None, node_type="CCP.PLUGIN_ROOT")
    for lp in loaded:
        m = lp.manifest
        node = CcpAliasNode(name=m.name, parent=root, node_type="CCP.PLUGIN_PACKAGE")
        node.attribute_dict["version"] = m.version
        node.attribute_dict["module"] = m.module
        node.attribute_dict["capabilities"] = ", ".join(m.capabilities)
        node.attribute_dict["state"] = "loaded"
        root.children.append(node)
    return root


def build_types_nav_root(registry: ElementTypeRegistry) -> CcpAliasNode:
    """Build hierarchical ``@types`` from ``type_key`` strings (``a.b.c`` → ``a`` / ``b`` / ``c``)."""
    root = CcpAliasNode(name="types", parent=None, node_type="CCP.TYPE_ROOT")
    keys = sorted(registry.registered_keys())
    for key in keys:
        handler = registry.get(key)
        if handler is None:
            continue
        parts = tuple(key.split(".")) if "." in key else (key,)
        parent = root
        for i, seg in enumerate(parts):
            is_last = i == len(parts) - 1
            if is_last:
                leaf = CcpAliasNode(name=seg, parent=parent, node_type="CCP.TYPE_HANDLER")
                leaf.attribute_dict["type_key"] = key
                leaf.attribute_dict["handler_class"] = type(handler).__name__
                parent.children.append(leaf)
            else:
                found = parent.get_child(seg)
                if found is None:
                    found = CcpAliasNode(name=seg, parent=parent, node_type="CCP.TYPE_NAMESPACE")
                    parent.children.append(found)
                parent = found
    return root
