"""Manage user-installed stat packs (#403).

A table of the built-in library and every installed pack, with what can be
done to each: import a new pack, enable or disable one, uninstall it, export it
to share, and read why an invalid one is refused. The work is done by
:mod:`fpdb_3_legacy.stat_packs`; this module is only the window over it.

The registries read packs when they are built, so a change reaches what is
opened next. The HUD keeps the registry it started with, which is why every
change ends with a restart notice rather than a half-refreshed application.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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

from fpdb_3_legacy import stat_packs
from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("stat_packs_dialog")

_STATUS_LABELS = {
    stat_packs.BUILTIN: N_("Built-in"),
    stat_packs.ENABLED: N_("User installed"),
    stat_packs.DISABLED: N_("Disabled"),
    stat_packs.INVALID: N_("Invalid"),
}
_COLUMNS = (N_("Pack"), N_("Status"), N_("Stats"), N_("Version"), N_("Author"))
_RESTART_NOTICE = N_("Restart fpdb and the HUD to use the change everywhere.")


class StatPacksDialog(QDialog):
    """Import, enable, disable, uninstall and export stat packs."""

    def __init__(self, parent: QWidget | None = None, packs_dir: str | Path | None = None) -> None:
        super().__init__(parent)
        self.packs_dir = packs_dir
        self.rows: list[stat_packs.PackStatus] = []
        self.setWindowTitle(_("Stat packs"))
        self.resize(820, 520)

        intro = QLabel(
            _(
                "A stat pack adds declarative stats, and optionally Research presets, "
                "without changing fpdb. Packs are data only: no Python, no SQL."
            ),
        )
        intro.setWordWrap(True)

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
        self.details.setMaximumHeight(150)

        self.import_button = QPushButton(_("Import pack..."))
        self.toggle_button = QPushButton(_("Disable"))
        self.uninstall_button = QPushButton(_("Uninstall"))
        self.export_button = QPushButton(_("Export..."))
        self.import_button.clicked.connect(self.import_pack)
        self.toggle_button.clicked.connect(self.toggle_selected)
        self.uninstall_button.clicked.connect(self.uninstall_selected)
        self.export_button.clicked.connect(self.export_selected)
        actions = QHBoxLayout()
        for button in (self.import_button, self.toggle_button, self.uninstall_button, self.export_button):
            actions.addWidget(button)
        actions.addStretch(1)

        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.details)
        layout.addLayout(actions)
        layout.addWidget(self.notice)
        layout.addWidget(close)
        self.refresh()

    # -- state ------------------------------------------------------------------

    def refresh(self, select: str | None = None) -> None:
        """Re-read the pack directory and redraw the table."""
        current = select or (self.selected().id if self.selected() else None)
        self.rows = stat_packs.list_packs(self.packs_dir)
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            values = (
                row.name if row.name == row.id else f"{row.name} ({row.id})",
                _(_STATUS_LABELS.get(row.status, row.status)),
                str(len(row.definitions)),
                row.pack_version,
                row.author,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(index, column, item)
        target = next((i for i, row in enumerate(self.rows) if row.id == current), 0 if self.rows else -1)
        if target >= 0:
            self.table.selectRow(target)
        self._selection_changed()

    def selected(self) -> stat_packs.PackStatus | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        index = rows[0].row()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def _selection_changed(self) -> None:
        row = self.selected()
        user_pack = row is not None and row.status != stat_packs.BUILTIN
        self.toggle_button.setEnabled(user_pack and row.status != stat_packs.INVALID)
        self.uninstall_button.setEnabled(user_pack)
        self.export_button.setEnabled(user_pack and row.status != stat_packs.INVALID)
        if row is not None:
            self.toggle_button.setText(_("Enable") if row.status == stat_packs.DISABLED else _("Disable"))
        self.details.setPlainText(self._describe(row) if row else "")

    @staticmethod
    def _describe(row: stat_packs.PackStatus) -> str:
        lines = [row.description] if row.description else []
        if row.errors:
            lines.append(_("This pack is not loaded:"))
            lines.extend(f"- {error}" for error in row.errors)
        if row.definitions:
            lines.append(_("Stats:") + " " + ", ".join(row.definitions))
        if row.path:
            lines.append(_("Location:") + f" {row.path}")
        return "\n".join(lines)

    def _changed(self, message: str, select: str | None = None) -> None:
        self.refresh(select)
        self.notice.setText(f"{message} {_(_RESTART_NOTICE)}")

    # -- actions ----------------------------------------------------------------

    def import_pack(self, path: str | None = None) -> bool:
        """Install a pack chosen by the user (or ``path``); report every problem."""
        if not path:
            path, _selected = QFileDialog.getOpenFileName(
                self,
                _("Import stat pack"),
                "",
                _("Stat pack") + f" (*{stat_packs.PACK_SUFFIX} {stat_packs.MANIFEST_NAME});;" + _("All files") + " (*)",
            )
        if not path:
            return False
        try:
            pack = stat_packs.install_pack(path, self.packs_dir)
        except stat_packs.PackError as exc:
            if not any("already installed" in message for message in exc.messages):
                self._refuse(exc)
                return False
            answer = QMessageBox.question(
                self,
                _("Import stat pack"),
                _("This pack is already installed. Replace it with this version?"),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            try:
                pack = stat_packs.install_pack(path, self.packs_dir, replace=True)
            except stat_packs.PackError as replace_exc:
                self._refuse(replace_exc)
                return False
            except OSError as replace_exc:
                QMessageBox.warning(self, _("Import stat pack"), _("Could not read the pack:\n%s") % replace_exc)
                return False
        except OSError as exc:
            QMessageBox.warning(self, _("Import stat pack"), _("Could not read the pack:\n%s") % exc)
            return False
        self._changed(_("Installed %s.") % pack.name, pack.id)
        return True

    def _refuse(self, error: stat_packs.PackError) -> None:
        log.info("Stat pack refused: %s", error)
        QMessageBox.warning(
            self,
            _("Import stat pack"),
            _("This pack cannot be installed:") + "\n\n" + "\n".join(f"- {message}" for message in error.messages),
        )

    def toggle_selected(self) -> None:
        row = self.selected()
        if row is None or row.status in (stat_packs.BUILTIN, stat_packs.INVALID):
            return
        enable = row.status == stat_packs.DISABLED
        try:
            stat_packs.set_enabled(row.id, enable, self.packs_dir)
        except (stat_packs.PackError, OSError) as exc:
            QMessageBox.warning(self, _("Stat packs"), _("The pack state was not changed:\n%s") % exc)
            return
        self._changed((_("Enabled %s.") if enable else _("Disabled %s.")) % row.name, row.id)

    def uninstall_selected(self, *, confirm: bool = True) -> None:
        row = self.selected()
        if row is None or row.status == stat_packs.BUILTIN:
            return
        if confirm:
            answer = QMessageBox.question(self, _("Uninstall stat pack"), _("Uninstall %s?") % row.name)
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            stat_packs.uninstall_pack(row.id, self.packs_dir)
        except (stat_packs.PackError, OSError) as exc:
            QMessageBox.warning(self, _("Uninstall stat pack"), str(exc))
            return
        self._changed(_("Uninstalled %s.") % row.name)

    def export_selected(self, path: str | None = None) -> Path | None:
        row = self.selected()
        if row is None or row.status in (stat_packs.BUILTIN, stat_packs.INVALID):
            return None
        if not path:
            path, _selected = QFileDialog.getSaveFileName(
                self,
                _("Export stat pack"),
                f"{row.id}{stat_packs.PACK_SUFFIX}",
                _("Stat pack") + f" (*{stat_packs.PACK_SUFFIX})",
            )
        if not path:
            return None
        try:
            target = stat_packs.export_pack(row.id, path, self.packs_dir)
        except (stat_packs.PackError, OSError) as exc:
            QMessageBox.warning(self, _("Export stat pack"), str(exc))
            return None
        self.notice.setText(_("Exported to %s.") % target)
        return target


def open_stat_packs(parent: Any = None, packs_dir: str | Path | None = None) -> None:
    """Show the manager modally (``packs_dir`` defaults to the user's data)."""
    StatPacksDialog(parent, packs_dir=packs_dir).exec()
