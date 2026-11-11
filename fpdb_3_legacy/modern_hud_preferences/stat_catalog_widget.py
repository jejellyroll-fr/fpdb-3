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

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.modern_hud_preferences import stat_edit
from fpdb_3_legacy.modern_hud_preferences.stat_catalog import (
    MIME_TYPE,
    CatalogEntry,
    StatCatalog,
    build_catalog,
    category_label,
    choice_label,
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
        item = QTreeWidgetItem([choice_label(entry), entry.description])
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


class StatChoiceCombo(QComboBox):
    """Pick a stat of the catalogue by typing part of its name (B15).

    The list holds the catalogue only. A name the catalogue lacks can still be
    shown -- the stat a cell already has -- but :meth:`chosen_entry` answers
    None for it, so the caller can keep it rather than write a new unknown name.
    """

    def __init__(self, catalog: StatCatalog, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(20)
        for label, key in catalog.choices():
            entry = catalog.get(key)
            self.addItem(label, key)
            if entry is not None:
                self.setItemData(self.count() - 1, f"{entry.description}\n{entry.category_label}", Qt.ItemDataRole.ToolTipRole)
        completer = QCompleter(self.model(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)
        self.lineEdit().setPlaceholderText(_("Type to search the stats"))

    def show_item(self, item: Mapping[str, Any] | None) -> None:
        """Show the stat of a profile cell, by its catalogue label when it has one."""
        item = item or {}
        entry = self.catalog.entry_for_item(item)
        self.setCurrentText(choice_label(entry) if entry is not None else str(item.get("stat", "") or ""))

    def chosen_entry(self) -> CatalogEntry | None:
        """The catalogue entry the text names, or None."""
        return self.catalog.entry_for_label(self.currentText())


class PopupChoiceCombo(QComboBox):
    """Pick one of the configuration's popups, or none (B15)."""

    def set_options(self, names: Iterable[str], current: str) -> None:
        """List *names*, with *current* selected, even when no popup has that name."""
        self.blockSignals(True)
        try:
            self.clear()
            for label, value in stat_edit.popup_options(names, current):
                self.addItem(label, value)
            self.setCurrentIndex(max(0, self.findData(current)))
        finally:
            self.blockSignals(False)

    def value(self) -> str:
        """The popup name to store; "" for none."""
        data = self.currentData()
        return "" if data is None else str(data)
