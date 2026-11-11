"""The "Available Stats" list of the HUD Preferences editor: search, categories, drag.

The widget shows a :class:`~fpdb_3_legacy.modern_hud_preferences.stat_catalog.StatCatalog`
and never changes a profile itself. It says which stat the user wants in two
ways, both carrying the entry's catalogue key:

* :attr:`StatCatalogWidget.stat_activated`, on double-click or Enter;
* a drag whose MIME data holds the key under
  :data:`~fpdb_3_legacy.modern_hud_preferences.stat_catalog.MIME_TYPE`.

The editor (or its canvas) looks the key up in the same catalogue.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.modern_hud_preferences.stat_catalog import (
    MIME_TYPE,
    ORIGIN_CLASSIC,
    CatalogEntry,
    StatCatalog,
    build_catalog,
    category_label,
)

KEY_ROLE = Qt.ItemDataRole.UserRole


def mime_data_for(keys: Sequence[str]) -> QMimeData:
    """The MIME data of a drag of the given catalogue keys, one per line."""
    mime = QMimeData()
    mime.setData(MIME_TYPE, "\n".join(keys).encode("utf-8"))
    return mime


def keys_from_mime(mime: QMimeData) -> list[str]:
    """The catalogue keys a drop carries; none when it is not a catalogue drag."""
    if not mime.hasFormat(MIME_TYPE):
        return []
    payload = bytes(mime.data(MIME_TYPE).data()).decode("utf-8")
    return [key for key in payload.splitlines() if key]


class _CatalogTree(QTreeWidget):
    """The tree, whose drags carry catalogue keys rather than Qt's item format."""

    def mimeTypes(self) -> list[str]:  # noqa: N802  # pylint: disable=invalid-name  # Qt override
        return [MIME_TYPE]

    def mimeData(self, items: Sequence[QTreeWidgetItem]) -> QMimeData:  # noqa: N802  # pylint: disable=invalid-name  # Qt override
        keys = [str(item.data(0, KEY_ROLE)) for item in items if item.data(0, KEY_ROLE)]
        return mime_data_for(keys)


class StatCatalogWidget(QWidget):
    """A search field, the catalogue grouped by category, and how many stats show."""

    stat_activated = Signal(str)

    def __init__(self, catalog: StatCatalog | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog if catalog is not None else build_catalog()

        self.search = QLineEdit(self)
        self.search.setPlaceholderText(_("Search stats"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh)

        self.tree = _CatalogTree(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([_("Stat"), _("Description")])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.tree.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.tree.itemActivated.connect(self._on_item_activated)

        self.count_label = QLabel(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.count_label)

        self._refresh()

    # --- Public API -----------------------------------------------------------
    def set_catalog(self, catalog: StatCatalog) -> None:
        """Show another catalogue, keeping the search text."""
        self.catalog = catalog
        self._refresh()

    def set_filter(self, text: str) -> None:
        self.search.setText(text)

    def shown_entries(self) -> list[CatalogEntry]:
        """The entries the tree shows, in its order."""
        shown = []
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            for child in range(group.childCount()):
                entry = self.catalog.get(str(group.child(child).data(0, KEY_ROLE)))
                if entry is not None:
                    shown.append(entry)
        return shown

    def current_key(self) -> str | None:
        """The key of the selected stat; None for a category or no selection."""
        item = self.tree.currentItem()
        key = item.data(0, KEY_ROLE) if item is not None else None
        return str(key) if key else None

    def select_key(self, key: str) -> bool:
        """Select the stat of *key* if it is shown."""
        for item in self._stat_items():
            if item.data(0, KEY_ROLE) == key:
                self.tree.setCurrentItem(item)
                return True
        return False

    def activate_current(self) -> None:
        """Ask for the selected stat, as a double-click does."""
        key = self.current_key()
        if key:
            self.stat_activated.emit(key)

    # --- Internals ------------------------------------------------------------
    def _stat_items(self) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            items.extend(group.child(child) for child in range(group.childCount()))
        return items

    def _refresh(self, *_args: object) -> None:
        text = self.search.text()
        entries = self.catalog.filter(text)
        selected = self.current_key()
        self.tree.clear()
        for category, members in self.catalog.grouped(entries):
            group = QTreeWidgetItem([f"{category_label(category)} ({len(members)})", ""])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(group)
            for entry in members:
                group.addChild(self._entry_item(entry))
            # A search shows every match; the full list opens closed.
            group.setExpanded(bool(text.strip()))
        if selected:
            self.select_key(selected)
        self.count_label.setText(
            _("Showing {shown} of {total} stats").format(shown=len(entries), total=len(self.catalog))
        )

    @staticmethod
    def _entry_item(entry: CatalogEntry) -> QTreeWidgetItem:
        name = entry.name if entry.origin == ORIGIN_CLASSIC else f"{entry.name} ({entry.origin_label})"
        item = QTreeWidgetItem([name, entry.description])
        item.setData(0, KEY_ROLE, entry.key)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
        tip = f"{entry.name}\n{entry.description}\n{entry.category_label} · {entry.origin_label}"
        item.setToolTip(0, tip)
        item.setToolTip(1, tip)
        return item

    def _on_item_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        key = item.data(0, KEY_ROLE)
        if key:
            self.stat_activated.emit(str(key))
