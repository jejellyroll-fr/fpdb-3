"""Tools ▸ Share a HUD or pack: write one ready to submit to the pack gallery (#449).

Pick a HUD profile of the configuration or an installed stat pack, say what
the gallery lists it as, and choose a folder: :mod:`fpdb_3_legacy.pack_share`
writes the package and its index entry there, laid out as the packs repository
is, after the checks an install runs. This module is only the window over it.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import pack_share, stat_packs
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.pack_gallery import GalleryError

log = get_logger("pack_share_dialog")

HUD, STATS = "hud", "stats"
PACKS_REPOSITORY = "https://github.com/jejellyroll-fr/fpdb-3-packs"


def suggested_id(author: str, name: str) -> str:
    """A gallery id from an author and a profile name: ``author.profile``, lower case."""

    def part(text: str) -> str:
        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", "_", plain.casefold()).strip("_")

    return f"{part(author) or 'yourname'}.{part(name) or 'hud'}"


class SharePackDialog(QDialog):
    """Choose a HUD profile or a stat pack, describe it, and write it for the gallery."""

    def __init__(self, config: Any, parent: QWidget | None = None, *, packs_dir: Path | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.packs_dir = packs_dir
        self.written: Path | None = None
        self._suggested = ""  # the id last suggested for a HUD, replaced only while it is untouched
        self.setWindowTitle(_("Share a HUD or pack"))
        self.resize(560, 440)

        self.kind = QComboBox()
        self.kind.addItem(_("HUD profile"), HUD)
        self.kind.addItem(_("Stat pack"), STATS)
        self.source = QComboBox()
        self.pack_id = QLineEdit()
        self.name = QLineEdit()
        self.version = QLineEdit("1.0.0")
        self.author = QLineEdit()
        self.license = QLineEdit()
        self.license.setPlaceholderText(_("For example CC-BY-4.0 or AGPL-3.0-or-later"))
        self.license.setToolTip(_("An SPDX licence identifier; the gallery requires one."))
        self.description = QPlainTextEdit()
        self.description.setMaximumHeight(90)

        form = QFormLayout()
        form.addRow(_("Share"), self.kind)
        form.addRow(_("Which"), self.source)
        form.addRow(_("Id"), self.pack_id)
        form.addRow(_("Name"), self.name)
        form.addRow(_("Version"), self.version)
        form.addRow(_("Author"), self.author)
        form.addRow(_("Licence"), self.license)
        form.addRow(_("Description"), self.description)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.write_button = buttons.addButton(_("Write package…"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.choose_folder)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.source.currentIndexChanged.connect(self._source_changed)
        self.author.textEdited.connect(self._suggest_id)
        self._kind_changed()

    # -- state ------------------------------------------------------------------

    def _stat_packs(self) -> list[stat_packs.PackStatus]:
        rows = stat_packs.list_packs(self.packs_dir, include_builtin=False, recover=False)
        return [row for row in rows if row.status in (stat_packs.ENABLED, stat_packs.DISABLED)]

    def _kind_changed(self) -> None:
        self.source.blockSignals(True)
        self.source.clear()
        if self.kind.currentData() == HUD:
            for profile in pack_share.profile_names(self.config.doc):
                self.source.addItem(profile, profile)
        else:
            for row in self._stat_packs():
                self.source.addItem(f"{row.name} ({row.id})", row)
        self.source.blockSignals(False)
        stats = self.kind.currentData() == STATS
        self.pack_id.clear()
        # A stat pack is listed under its own id and version, as the gallery requires.
        self.pack_id.setReadOnly(stats)
        self.version.setReadOnly(stats)
        self.write_button.setEnabled(self.source.count() > 0)
        self._source_changed()

    def _source_changed(self) -> None:
        chosen = self.source.currentData()
        if chosen is None:
            return
        if isinstance(chosen, stat_packs.PackStatus):
            self.pack_id.setText(chosen.id)
            self.version.setText(chosen.pack_version)
            self.name.setText(chosen.name)
            self.description.setPlainText(chosen.description)
            if chosen.author and not self.author.text():
                self.author.setText(chosen.author)
            return
        self.name.setText(chosen)
        # The previous suggestion stays known, so an id fpdb suggested still follows the profile (Codex, #643).
        self._suggest_id()

    def _suggest_id(self) -> None:
        """For a HUD, an id from the author and the profile, unless one was typed."""
        chosen = self.source.currentData()
        if not isinstance(chosen, str) or self.pack_id.text() not in ("", self._suggested):
            return
        self._suggested = suggested_id(self.author.text(), chosen)
        self.pack_id.setText(self._suggested)

    # -- actions ----------------------------------------------------------------

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, _("Write the package in"), str(Path.home()))
        if folder and self.share(Path(folder)):
            self.accept()

    def share(self, destination: Path) -> bool:
        """Write the chosen HUD or pack in *destination*; every refusal is reported."""
        fields = {
            "name": self.name.text().strip(),
            "author": self.author.text().strip(),
            "license": self.license.text().strip(),
            "description": self.description.toPlainText().strip(),
        }
        chosen = self.source.currentData()
        try:
            if isinstance(chosen, stat_packs.PackStatus):
                self.written = pack_share.share_stat_pack(chosen.id, destination, packs_dir=self.packs_dir, **fields)
            else:
                self.written = pack_share.share_hud(
                    self.config.doc,
                    str(chosen),
                    destination,
                    pack_id=self.pack_id.text().strip(),
                    version=self.version.text().strip(),
                    **fields,
                )
        except (GalleryError, stat_packs.PackError) as exc:
            self._refuse(exc.messages)
            return False
        except OSError as exc:
            self._refuse([str(exc)])
            return False
        QMessageBox.information(
            self,
            _("Share a HUD or pack"),
            _(
                "Written to %(folder)s.\n\nTo submit it, copy the folder's content into your copy of the "
                "packs repository (%(repository)s), add the entry in %(entry)s to index.json, and open a pull request."
            )
            % {"folder": self.written, "repository": PACKS_REPOSITORY, "entry": pack_share.ENTRY_NAME},
        )
        return True

    def _refuse(self, messages: list[str]) -> None:
        log.info("Pack share refused: %s", messages)
        QMessageBox.warning(
            self,
            _("Share a HUD or pack"),
            _("This cannot be shared:") + "\n\n" + "\n".join(f"- {message}" for message in messages),
        )


def open_share_pack(config: Any, parent: Any = None) -> None:
    """Show the share window modally."""
    SharePackDialog(config, parent).exec()
