from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from synarius_core.model.attribute_dict import AttributeEntry
from synarius_attr_config.meta import GuiHint, OptionMeta
from synarius_attr_config.persistence import TomlPersistenceLayer
from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets._table_widget import AttribTableWidget


class OptionsMenuWidget(QWidget):
    """Global application-configuration dialog widget.

    Layout: a ``QSplitter`` with

    * **left pane** — ``QTreeWidget`` whose nodes are built from the
      ``OptionMeta.global_path`` components of the supplied entries.
    * **right pane** — a ``QScrollArea`` with one :class:`AttribTableWidget`
      per leaf node.  Selecting a tree node reveals the corresponding panel.

    All entries must have ``OptionMeta.global_ == True``.  Entries without an
    ``OptionMeta`` or with an empty ``global_path`` are collected under the
    root ``"(global)"`` node.

    Parameters
    ----------
    global_entries
        Pre-filtered list of ``(key, entry, option_meta, gui_hint)`` tuples
        for all globally configurable attributes.
    persistence
        Persistence layer used for reset operations and default values.
    obj_type
        Object-type string forwarded to each :class:`AttribViewModel` for
        registry lookups.
    """

    def __init__(
        self,
        global_entries: list[tuple[str, AttributeEntry, OptionMeta, GuiHint]],
        persistence: TomlPersistenceLayer,
        obj_type: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._persistence = persistence
        self._group_vms: dict[str, AttribViewModel] = {}
        self._path_to_panel: dict[str, QWidget] = {}

        # ------------------------------------------------------------------
        # Group entries by normalized global_path
        # ------------------------------------------------------------------
        groups: dict[str, list[tuple[str, AttributeEntry, OptionMeta, GuiHint]]] = {}
        for key, entry, om, gh in global_entries:
            path = om.global_path.strip("/") if om.global_path else "(global)"
            groups.setdefault(path, []).append((key, entry, om, gh))

        # Sort groups by order of their first attribute's OptionMeta.order, then path
        def _group_sort_key(path: str) -> tuple[int, str]:
            first_om = groups[path][0][2]
            return (first_om.order if first_om.order is not None else 9999, path)

        sorted_paths = sorted(groups, key=_group_sort_key)

        for path in sorted_paths:
            entries_for_path = groups[path]
            sorted_entries = sorted(
                entries_for_path,
                key=lambda t: (t[2].order if t[2].order is not None else 9999, t[0]),
            )
            vm = AttribViewModel(
                sorted_entries,
                persistence=persistence,
                obj_type=obj_type,
            )
            self._group_vms[path] = vm

        # ------------------------------------------------------------------
        # Build layout
        # ------------------------------------------------------------------
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # Left: tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self._tree)

        tree_nodes: dict[str, QTreeWidgetItem] = {}
        for path in sorted_paths:
            self._build_tree_path(path, tree_nodes)
        self._tree.expandAll()

        # Right: scroll area with stacked panels
        self._right_container = QWidget()
        self._right_layout = QVBoxLayout(self._right_container)
        self._right_layout.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidget(self._right_container)
        scroll.setWidgetResizable(True)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        for path, vm in self._group_vms.items():
            panel = self._make_panel(path, vm)
            self._path_to_panel[path] = panel
            self._right_layout.addWidget(panel)
            panel.hide()

        # Show first group
        if self._path_to_panel:
            first_path = sorted_paths[0]
            self._path_to_panel[first_path].show()
            self._current_path = first_path
        else:
            self._current_path = ""

        self._tree.currentItemChanged.connect(self._on_selection_changed)

        # Select first item in tree
        if self._tree.topLevelItemCount() > 0:
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------

    def _build_tree_path(
        self,
        path: str,
        nodes: dict[str, QTreeWidgetItem],
    ) -> QTreeWidgetItem | None:
        parts = path.split("/")
        parent: QTreeWidgetItem | None = None
        accumulated = ""
        for depth, part in enumerate(parts):
            accumulated = f"{accumulated}/{part}" if accumulated else part
            if accumulated not in nodes:
                item = QTreeWidgetItem([part])
                item.setData(0, Qt.ItemDataRole.UserRole, None)
                if parent is None:
                    self._tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                nodes[accumulated] = item
            parent = nodes[accumulated]
        # Tag the leaf node with the full path
        if parent is not None:
            parent.setData(0, Qt.ItemDataRole.UserRole, path)
        return parent

    def _make_panel(self, path: str, vm: AttribViewModel) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(f"<b>{path.split('/')[-1]}</b>")
        layout.addWidget(title)
        table = AttribTableWidget(vm)
        layout.addWidget(table)
        layout.addStretch()
        return panel

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            return
        path = current.data(0, Qt.ItemDataRole.UserRole)
        if path is None or path not in self._path_to_panel:
            return
        if self._current_path and self._current_path in self._path_to_panel:
            self._path_to_panel[self._current_path].hide()
        self._path_to_panel[path].show()
        self._current_path = path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def all_view_models(self) -> list[AttribViewModel]:
        """Return all :class:`AttribViewModel` instances (one per group)."""
        return list(self._group_vms.values())

    def current_view_model(self) -> AttribViewModel | None:
        """Return the :class:`AttribViewModel` for the currently selected group."""
        return self._group_vms.get(self._current_path)
