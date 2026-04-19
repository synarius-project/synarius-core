from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from synarius_core.model.attribute_dict import AttributeEntry
from synarius_attr_config.meta import GuiHint, OptionMeta
from synarius_attr_config.persistence import TomlPersistenceLayer
from synarius_attr_config.projection import AttribViewModel
from synarius_attr_config.widgets._form_widget import AttribFormWidget
from synarius_attr_config.widgets._layout_templates import (
    DEFAULT_OPTIONS_MENU_SHELL,
    OptionsMenuShellTemplate,
    apply_options_scroll_layout,
    apply_options_splitter_template,
    format_options_group_title,
)
from synarius_attr_config.widgets._table_widget import AttribTableWidget, _FORM_TEXT


class OptionsMenuWidget(QWidget):
    """Global application-configuration dialog widget.

    A top-level ``QTabWidget`` (*Tabelle* / *Raster*) switches the **entire**
    widget at once.  Each tab is a self-contained ``QSplitter``:

    * **left pane** — narrow ``QTreeWidget`` built from
      ``OptionMeta.global_path`` components.  Every node stores its
      accumulated path in ``UserRole`` so clicking an intermediate node
      shows all descendant groups; clicking a leaf shows exactly that group.
    * **right pane** — ``QScrollArea`` with all (visible) groups stacked
      vertically.

    The two trees are kept in sync: switching tabs preserves the active
    selection.

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
    shell_template
        Tab titles, splitter sizes, scroll padding, and path formatting for the
        global-options chrome. Defaults to :data:`DEFAULT_OPTIONS_MENU_SHELL`.
    """

    def __init__(
        self,
        global_entries: list[tuple[str, AttributeEntry, OptionMeta, GuiHint]],
        persistence: TomlPersistenceLayer,
        obj_type: str = "",
        shell_template: OptionsMenuShellTemplate | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._persistence = persistence
        self._shell = shell_template or DEFAULT_OPTIONS_MENU_SHELL
        self._group_vms: dict[str, AttribViewModel] = {}

        # ------------------------------------------------------------------
        # Group and sort entries
        # ------------------------------------------------------------------
        groups: dict[str, list[tuple[str, AttributeEntry, OptionMeta, GuiHint]]] = {}
        for key, entry, om, gh in global_entries:
            path = om.global_path.strip("/") if om.global_path else "(global)"
            groups.setdefault(path, []).append((key, entry, om, gh))

        def _group_sort_key(p: str) -> tuple[int, str]:
            first_om = groups[p][0][2]
            return (first_om.order if first_om.order is not None else 9999, p)

        sorted_paths = sorted(groups, key=_group_sort_key)

        for path in sorted_paths:
            sorted_entries = sorted(
                groups[path],
                key=lambda t: (t[2].order if t[2].order is not None else 9999, t[0]),
            )
            self._group_vms[path] = AttribViewModel(
                sorted_entries, persistence=persistence, obj_type=obj_type
            )

        # ------------------------------------------------------------------
        # Top-level tab widget (wraps the entire widget)
        # ------------------------------------------------------------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._tabs = QTabWidget()
        outer.addWidget(self._tabs)

        # Tab "Tabelle"
        self._table_tree_nodes: dict[str, QTreeWidgetItem] = {}
        self._table_tree = self._build_tree(sorted_paths, self._table_tree_nodes)
        self._table_scroll, self._table_path_to_panel = self._build_table_scroll(sorted_paths)
        sh = self._shell
        self._tabs.addTab(
            self._make_splitter(self._table_tree, self._table_scroll), sh.tab_label_table
        )

        # Tab "Raster"
        self._form_tree_nodes: dict[str, QTreeWidgetItem] = {}
        self._form_tree = self._build_tree(sorted_paths, self._form_tree_nodes)
        self._form_scroll, self._form_path_to_panel = self._build_form_scroll(sorted_paths)
        self._tabs.addTab(
            self._make_splitter(self._form_tree, self._form_scroll), sh.tab_label_form
        )

        # Connect both trees — selection change filters ALL panels and syncs the peer tree
        self._table_tree.currentItemChanged.connect(
            lambda cur, _: self._on_tree_changed(cur, self._form_tree, self._form_tree_nodes)
        )
        self._form_tree.currentItemChanged.connect(
            lambda cur, _: self._on_tree_changed(cur, self._table_tree, self._table_tree_nodes)
        )

        if self._table_tree.topLevelItemCount() > 0:
            self._table_tree.setCurrentItem(self._table_tree.topLevelItem(0))

    # ------------------------------------------------------------------
    # Tree / splitter builders
    # ------------------------------------------------------------------

    def _build_tree(
        self, sorted_paths: list[str], nodes: dict[str, QTreeWidgetItem]
    ) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(self._shell.tree_header_hidden)
        tree.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        for path in sorted_paths:
            self._build_tree_path(tree, path, nodes)
        tree.expandAll()
        return tree

    def _build_tree_path(
        self,
        tree: QTreeWidget,
        path: str,
        nodes: dict[str, QTreeWidgetItem],
    ) -> QTreeWidgetItem | None:
        """Build tree nodes for *path*; every node stores its accumulated path
        in UserRole so intermediate nodes filter by prefix."""
        parts = path.split("/")
        parent: QTreeWidgetItem | None = None
        accumulated = ""
        for part in parts:
            accumulated = f"{accumulated}/{part}" if accumulated else part
            if accumulated not in nodes:
                item = QTreeWidgetItem([part])
                item.setData(0, Qt.ItemDataRole.UserRole, accumulated)
                if parent is None:
                    tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                nodes[accumulated] = item
            parent = nodes[accumulated]
        return parent

    def _make_splitter(self, tree: QTreeWidget, scroll: QScrollArea) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(tree)
        splitter.addWidget(scroll)
        apply_options_splitter_template(splitter, self._shell)
        return splitter

    # ------------------------------------------------------------------
    # Scroll-area builders
    # ------------------------------------------------------------------

    def _build_table_scroll(
        self, sorted_paths: list[str]
    ) -> tuple[QScrollArea, dict[str, QWidget]]:
        container = QWidget()
        layout = QVBoxLayout(container)
        apply_options_scroll_layout(layout, self._shell)
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        path_to_panel: dict[str, QWidget] = {}
        for path in sorted_paths:
            panel = self._make_table_panel(path, self._group_vms[path])
            path_to_panel[path] = panel
            layout.addWidget(panel)
        layout.addStretch()
        return scroll, path_to_panel

    def _build_form_scroll(
        self, sorted_paths: list[str]
    ) -> tuple[QScrollArea, dict[str, QWidget]]:
        container = QWidget()
        layout = QVBoxLayout(container)
        apply_options_scroll_layout(layout, self._shell)
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        path_to_panel: dict[str, QWidget] = {}
        for path in sorted_paths:
            panel = self._make_form_panel(path, self._group_vms[path])
            path_to_panel[path] = panel
            layout.addWidget(panel)
        layout.addStretch()
        return scroll, path_to_panel

    # ------------------------------------------------------------------
    # Panel helpers
    # ------------------------------------------------------------------

    def _make_table_panel(self, path: str, vm: AttribViewModel) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        table = AttribTableWidget(
            vm, title=format_options_group_title(path, self._shell)
        )
        table.compact()
        layout.addWidget(table)
        return panel

    def _make_form_panel(self, path: str, vm: AttribViewModel) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        sh = self._shell
        layout.setSpacing(sh.form_panel_title_spacing)
        title = QLabel(f"<b>{format_options_group_title(path, sh)}</b>")
        title.setStyleSheet(f"color: {_FORM_TEXT};")
        title.setSizePolicy(sh.form_title_size_policy_h, sh.form_title_size_policy_v)
        layout.addWidget(title)
        form = AttribFormWidget(vm, dark=True)
        form.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(form)
        return panel

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _apply_filter(self, selected: str) -> None:
        """Show only panels whose path equals or starts with *selected* — in both tabs."""
        for path_to_panel, scroll in (
            (self._table_path_to_panel, self._table_scroll),
            (self._form_path_to_panel, self._form_scroll),
        ):
            first_visible: QWidget | None = None
            for path, panel in path_to_panel.items():
                visible = path == selected or path.startswith(selected + "/")
                panel.setVisible(visible)
                if visible and first_visible is None:
                    first_visible = panel
            if first_visible:
                scroll.ensureWidgetVisible(first_visible)

    def _on_tree_changed(
        self,
        current: QTreeWidgetItem | None,
        peer_tree: QTreeWidget,
        peer_nodes: dict[str, QTreeWidgetItem],
    ) -> None:
        if current is None:
            return
        selected = current.data(0, Qt.ItemDataRole.UserRole)
        if selected is None:
            return

        self._apply_filter(selected)

        # Keep peer tree in sync without triggering its signal
        peer_item = peer_nodes.get(selected)
        if peer_item and peer_tree.currentItem() is not peer_item:
            peer_tree.blockSignals(True)
            peer_tree.setCurrentItem(peer_item)
            peer_tree.blockSignals(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def all_view_models(self) -> list[AttribViewModel]:
        """Return all :class:`AttribViewModel` instances (one per group)."""
        return list(self._group_vms.values())

    def current_view_model(self) -> AttribViewModel | None:
        """Return the :class:`AttribViewModel` for the currently selected group.

        Returns ``None`` when the selected tree node is an intermediate node
        with no direct attribute group.
        """
        tree = self._table_tree if self._tabs.currentIndex() == 0 else self._form_tree
        item = tree.currentItem()
        if item is not None:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                return self._group_vms.get(path)
        return None
