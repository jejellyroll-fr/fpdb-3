"""Tools ▸ Get packs: browse the pack gallery, install, update and uninstall (#449).

A table of what the gallery's index lists, with what this fpdb has of each:
not installed, installed, an update, or a pack that needs a newer fpdb. The
work is done by :mod:`fpdb_3_legacy.pack_gallery`, which checks every package
before anything is written; this module is only the window over it.

A HUD package goes into the HUD configuration, which is saved; a stat pack
into the user pack directory. Either way the HUD keeps what it started with,
so a change ends with the same restart notice as the stat pack manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import pack_gallery, stat_packs
from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("pack_gallery_dialog")

_COLUMNS = (N_("Pack"), N_("Kind"), N_("Version"), N_("Installed"), N_("Status"))
_KINDS = {"hud": N_("HUD"), "stats": N_("Stat pack")}
_RESTART_NOTICE = N_("Restart fpdb and the HUD to use the change everywhere.")
NOT_INSTALLED, INSTALLED, UPDATE, TOO_NEW = "not_installed", "installed", "update", "too_new"
_STATUS_LABELS = {
    NOT_INSTALLED: N_("Not installed"),
    INSTALLED: N_("Installed"),
    UPDATE: N_("Update available"),
    TOO_NEW: N_("Needs a newer fpdb"),
}
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024


def gallery_source(config: Any) -> str:
    """The gallery to read: ``<general pack_gallery="...">`` when set, else the project's."""
    general = getattr(config, "general", None) or {}
    return str(general.get("pack_gallery") or pack_gallery.DEFAULT_GALLERY)


class PackGalleryDialog(QDialog):
    """List the gallery's packs; install, update or uninstall the selected one."""

    def __init__(
        self,
        config: Any,
        parent: QWidget | None = None,
        *,
        source: str | None = None,
        cache_dir: Path | None = None,
        record: Path | None = None,
        packs_dir: Path | None = None,
        read: pack_gallery.Reader = pack_gallery.read_location,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.source = source or gallery_source(config)
        self.cache_dir = cache_dir or pack_gallery.record_path().parent / "pack-gallery-cache"
        self.record = record or pack_gallery.record_path()
        self.packs_dir = packs_dir
        self.read = read
        self.index = pack_gallery.PackIndex(())
        self.rows: list[tuple[pack_gallery.GalleryEntry, str, str]] = []  # (entry, installed version, status)
        self.setWindowTitle(_("Get packs"))
        self.resize(860, 600)

        self.source_label = QLabel("")
        self.source_label.setWordWrap(True)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([_(title) for title in _COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.screenshot = QLabel("")
        self.screenshot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot.setMaximumHeight(220)
        preview = QHBoxLayout()
        preview.addWidget(self.details, 1)
        preview.addWidget(self.screenshot, 1)

        self.install_button = QPushButton(_("Install"))
        self.uninstall_button = QPushButton(_("Uninstall"))
        self.refresh_button = QPushButton(_("Refresh"))
        self.install_button.clicked.connect(self.install_selected)
        self.uninstall_button.clicked.connect(self.uninstall_selected)
        self.refresh_button.clicked.connect(self.load)
        actions = QHBoxLayout()
        for button in (self.install_button, self.uninstall_button, self.refresh_button):
            actions.addWidget(button)
        actions.addStretch(1)

        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.source_label)
        layout.addWidget(self.table, 1)
        layout.addLayout(preview)
        layout.addLayout(actions)
        layout.addWidget(self.notice)
        layout.addWidget(close)
        self.load()

    # -- state ------------------------------------------------------------------

    def load(self) -> None:
        """Read the gallery's index (or the cached one) and redraw."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.index = pack_gallery.load_index(self.source, self.cache_dir, read=self.read)
            error = ""
        except pack_gallery.GalleryError as exc:
            self.index = pack_gallery.PackIndex(())
            error = "; ".join(exc.messages)
        finally:
            QApplication.restoreOverrideCursor()
        lines = [_("Gallery: %s") % self.source]
        if error:
            lines.append(_("The gallery could not be read: %s") % error)
        elif self.index.stale:
            lines.append(_("The gallery could not be reached; showing the copy from the last visit."))
        if self.index.rejected:
            lines.append(
                _("%d listed pack(s) are not shown because their entry is invalid.") % len(self.index.rejected)
            )
        self.source_label.setText("\n".join(lines))
        self.refresh()

    def refresh(self, select: str | None = None) -> None:
        chosen = self.selected()
        current = select or (chosen[0].id if chosen else None)
        versions = pack_gallery.installed_versions(self.record, self.packs_dir)
        newer = {entry.id for entry, _installed in pack_gallery.updates(self.index, versions)}
        self.rows = []
        for entry in self.index.entries:
            installed = versions.get(entry.id, "")
            if pack_gallery.incompatibility(entry):
                status = TOO_NEW
            elif entry.id in newer:
                status = UPDATE
            else:
                status = INSTALLED if entry.id in versions else NOT_INSTALLED
            self.rows.append((entry, installed, status))
        self.table.setRowCount(len(self.rows))
        for position, (entry, installed, status) in enumerate(self.rows):
            values = (entry.name, _(_KINDS[entry.kind]), entry.version, installed, _(_STATUS_LABELS[status]))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                self.table.setItem(position, column, item)
        target = next((i for i, row in enumerate(self.rows) if row[0].id == current), 0 if self.rows else -1)
        if target >= 0:
            self.table.selectRow(target)
        self._selection_changed()

    def selected(self) -> tuple[pack_gallery.GalleryEntry, str, str] | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        position = rows[0].row()
        return self.rows[position] if 0 <= position < len(self.rows) else None

    def _selection_changed(self) -> None:
        row = self.selected()
        status = row[2] if row else None
        self.install_button.setEnabled(status in (NOT_INSTALLED, UPDATE))
        self.install_button.setText(_("Update") if status == UPDATE else _("Install"))
        recorded = pack_gallery.read_record(self.record)
        self.uninstall_button.setEnabled(row is not None and row[0].id in recorded)
        self.details.setPlainText(self._describe(row[0]) if row else "")
        self._show_screenshot(row[0] if row else None)

    @staticmethod
    def _describe(entry: pack_gallery.GalleryEntry) -> str:
        lines = [entry.description] if entry.description else []
        lines.append(
            _("Author: %(author)s - Licence: %(license)s") % {"author": entry.author, "license": entry.license}
        )
        if entry.stats:
            lines.append(_("Stats:") + " " + ", ".join(entry.stats))
        problem = pack_gallery.incompatibility(entry)
        if problem:
            lines.append(problem)
        return "\n".join(lines)

    def _show_screenshot(self, entry: pack_gallery.GalleryEntry | None) -> None:
        """The entry's screenshot, kept beside the cached packages; nothing when it cannot be read."""
        self.screenshot.clear()
        if entry is None or not entry.screenshot:
            return
        cached = self.cache_dir / "screens" / entry.id / entry.version / Path(entry.screenshot).name
        try:
            if not cached.is_file():
                data = self.read(pack_gallery.location(self.source, entry.screenshot), MAX_SCREENSHOT_BYTES)
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(data)
        except OSError as exc:
            log.info("No screenshot for %s: %s", entry.id, exc)
            return
        image = QPixmap(str(cached))
        if not image.isNull():
            self.screenshot.setPixmap(
                image.scaled(360, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )

    def _changed(self, message: str, select: str | None) -> None:
        # The HUD configuration is already saved: install_entry and uninstall_entry
        # save it before they record the change (Codex, #641).
        self.refresh(select)
        self.notice.setText(f"{message} {_(_RESTART_NOTICE)}")

    # -- actions ----------------------------------------------------------------

    def install_selected(self, *, confirm: bool = True) -> bool:
        """Install the selected pack, or update it; every refusal is reported."""
        row = self.selected()
        if row is None or row[2] not in (NOT_INSTALLED, UPDATE):
            return False
        entry, _installed, status = row
        update = status == UPDATE
        if update and entry.kind == "hud" and confirm:
            answer = QMessageBox.question(
                self,
                _("Update HUD"),
                _(
                    "Updating replaces the profiles and popups this pack installed, with any change you made to them. Continue?"
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            package = pack_gallery.fetch_package(entry, self.source, self.cache_dir, read=self.read)
            pack_gallery.install_entry(
                entry,
                package,
                config_doc=self.config.doc,
                record=self.record,
                packs_dir=self.packs_dir,
                replace=update,
                save=self.config.save,
            )
        except (pack_gallery.GalleryError, stat_packs.PackError) as exc:
            QApplication.restoreOverrideCursor()
            self._refuse(_("This pack cannot be installed:"), exc.messages)
            return False
        except OSError as exc:
            QApplication.restoreOverrideCursor()
            self._refuse(_("This pack cannot be installed:"), [str(exc)])
            return False
        QApplication.restoreOverrideCursor()
        self._changed((_("Updated %s.") if update else _("Installed %s.")) % entry.name, entry.id)
        return True

    def uninstall_selected(self, *, confirm: bool = True) -> bool:
        row = self.selected()
        if row is None:
            return False
        entry = row[0]
        if confirm:
            answer = QMessageBox.question(self, _("Uninstall pack"), _("Uninstall %s?") % entry.name)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        try:
            pack_gallery.uninstall_entry(
                entry.id,
                config_doc=self.config.doc,
                record=self.record,
                packs_dir=self.packs_dir,
                save=self.config.save,
            )
        except (pack_gallery.GalleryError, stat_packs.PackError) as exc:
            self._refuse(_("This pack cannot be uninstalled:"), exc.messages)
            return False
        except OSError as exc:
            self._refuse(_("This pack cannot be uninstalled:"), [str(exc)])
            return False
        self._changed(_("Uninstalled %s.") % entry.name, entry.id)
        return True

    def _refuse(self, heading: str, messages: list[str]) -> None:
        log.info("Pack gallery refused: %s", messages)
        QMessageBox.warning(self, _("Get packs"), heading + "\n\n" + "\n".join(f"- {message}" for message in messages))


def open_pack_gallery(config: Any, parent: Any = None) -> None:
    """Show the gallery modally."""
    PackGalleryDialog(config, parent).exec()
