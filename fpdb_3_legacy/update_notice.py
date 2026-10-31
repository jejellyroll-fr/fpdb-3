"""The update check's Qt side (#445): run it off the GUI thread, show what it found.

``UpdateChecker`` asks GitHub from a worker thread and hands the answer back
through a signal, so startup never waits on the network. ``UpdateNotice`` is the
non-modal status-bar line that says a newer release exists and links to it.
Nothing here downloads or installs anything.
"""

from __future__ import annotations

import html
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QMessageBox, QToolButton, QWidget

from fpdb_3_legacy import update_check
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.update_check import Release

__all__ = ["UpdateChecker", "UpdateNotice", "ask_to_check_for_updates", "present_result", "show_manual_result"]


class UpdateChecker(QObject):
    """Asks GitHub for the latest release in a background thread.

    ``finished(reached, release, manual)``: ``reached`` is False when GitHub
    could not be read; ``release`` is the newer release, or None when the running
    build is current. Emitted from the worker thread; Qt queues it to the
    receiver's thread.
    """

    finished = Signal(bool, object, bool)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        reader: Callable[[str, float], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self._reader = reader

    def start(self, current: str, packaging: str, *, include_prereleases: bool = False, manual: bool = False) -> None:
        threading.Thread(
            target=self._run,
            args=(current, packaging, include_prereleases, manual),
            name="fpdb-update-check",
            daemon=True,
        ).start()

    def _run(self, current: str, packaging: str, include_prereleases: bool, manual: bool) -> None:
        if self._reader is not None:
            data = update_check.fetch_release(include_prereleases=include_prereleases, reader=self._reader)
        else:
            data = update_check.fetch_release(include_prereleases=include_prereleases)
        release = None if data is None else update_check.release_to_announce(data, current, packaging)
        self.finished.emit(data is not None, release, manual)


class UpdateNotice(QWidget):
    """A status-bar line: a newer fpdb is out, with links to it, and a button to hide it."""

    def __init__(self, release: Release, current: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.release = release
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)

        # Labels outside the f-strings: xgettext before 0.22 does not see a call in one.
        notes_label = html.escape(_("Release notes"))
        links = [f'<a href="{html.escape(release.page_url)}">{notes_label}</a>']
        if release.asset_url:
            download_label = html.escape(_("Download %s") % release.asset_name)
            links.append(f'<a href="{html.escape(release.asset_url)}">{download_label}</a>')
        headline = _("fpdb %(new)s is available (you have %(current)s).") % {"new": release.tag, "current": current}
        self.label = QLabel(f"{html.escape(headline)} {' · '.join(links)}")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setOpenExternalLinks(True)
        layout.addWidget(self.label)

        close = QToolButton()
        close.setText("✕")
        close.setToolTip(_("Hide this notice"))
        close.setAutoRaise(True)
        close.clicked.connect(self.hide)
        layout.addWidget(close)


def present_result(window: QMainWindow, reached: bool, release: Release | None, manual: bool, current: str) -> None:
    """Show what a check found: the notice when there is a newer release, a reply when asked by hand.

    An automatic check that finds nothing, or cannot reach GitHub, shows nothing.
    A second notice replaces the first rather than stacking up in the status bar.
    """
    if release is None:
        if manual:
            show_manual_result(window, reached, current)
        return
    previous = getattr(window, "update_notice", None)
    if previous is not None:
        window.statusBar().removeWidget(previous)
        previous.deleteLater()
    notice = UpdateNotice(release, current, window)
    window.update_notice = notice  # type: ignore[attr-defined]
    window.statusBar().addPermanentWidget(notice)
    notice.show()


def ask_to_check_for_updates(parent: QWidget | None) -> bool:
    """The first-run question: may fpdb look for new releases? Says what that involves."""
    answer = QMessageBox.question(
        parent,
        _("Check for updates"),
        _(
            "fpdb can check once a day whether a newer release is available on GitHub, "
            "and tell you in the status bar.\n\n"
            "The check is a single anonymous request to the GitHub releases page: it sends "
            "nothing about you or your hands, and fpdb never downloads or installs anything "
            "by itself.\n\n"
            "You can change this later in File > Preferences (general: check_for_updates), "
            "and check by hand with Help > Check for updates.\n\n"
            "Check for updates automatically?"
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    return answer == QMessageBox.StandardButton.Yes


def show_manual_result(parent: QWidget | None, reached: bool, current: str) -> None:
    """Answer a Help > Check for updates that found nothing newer."""
    if reached:
        QMessageBox.information(parent, _("Check for updates"), _("fpdb %s is the latest release.") % current)
    else:
        QMessageBox.warning(
            parent,
            _("Check for updates"),
            _("GitHub could not be reached. Check your connection and try again later."),
        )
