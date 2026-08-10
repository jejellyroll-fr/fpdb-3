"""The Help ▸ Version tab: what build is running, and on top of what.

Issue #226: the only place fpdb reported its own identity was a modal About box
with a licence notice, so "which version are you on?" turned into a support
round trip on every bug report. This tab answers it in one screen -- version,
packaging, checkout, interpreter and libraries, config path, database -- and
adds a *Copy report* button, because the value of these facts is that they end
up pasted into an issue.

All the collection lives in :mod:`fpdb_3_legacy.version_info`; this module only
lays it out, which keeps the facts testable without a Qt event loop.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import version_info
from fpdb_3_legacy.i18n import gettext as _


def _escape(value: object) -> str:
    """Escape a collected value for the HTML report.

    Paths and platform strings are arbitrary user data -- a Windows config path
    or an OS release string can carry ``&`` or ``<`` -- and unescaped they would
    silently swallow part of the line the reader needs.
    """
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _git_lines(git: version_info.GitCheckout) -> list[tuple[str, str]]:
    """Rows describing the checkout, or a single row saying there is none."""
    if not git.is_repository:
        return [(_("Git checkout"), _("not a git checkout (packaged or exported build)"))]
    state = _("modified (uncommitted changes)") if git.dirty else _("clean")
    return [
        (_("Git commit"), git.commit),
        (_("Git branch"), git.branch),
        (_("Working tree"), state),
    ]


def report_rows(report: version_info.VersionReport) -> list[tuple[str, str]]:
    """Flatten the report into the ordered label/value rows the tab shows.

    Ordering is deliberate: the two facts a maintainer asks for first (version,
    packaging) lead, the checkout details follow, then the environment, and the
    session-specific paths close it out. The same rows feed the rendered table
    and the clipboard text, so the two can never disagree.
    """
    rows: list[tuple[str, str]] = [
        (_("FPDB version"), report.version),
        (_("Packaging"), report.packaging),
    ]
    rows.extend(_git_lines(report.git))
    rows.extend(report.runtime.items())
    rows.append((_("Configuration file"), report.config_file))
    rows.append((_("Database"), report.database))
    return rows


def report_as_text(report: version_info.VersionReport) -> str:
    """The report as plain text, ready to paste into a GitHub issue.

    Markdown fences wrap it so it survives the issue form's formatting instead
    of collapsing into one paragraph.
    """
    rows = report_rows(report)
    width = max(len(label) for label, _value in rows)
    body = "\n".join(f"{label.ljust(width)} : {value}" for label, value in rows)
    return f"```\nFPDB environment report\n{body}\n```"


class GuiVersionInfo(QWidget):
    """Read-only view of the running build's version and environment."""

    def __init__(self, config=None, db=None, version: str = version_info.UNKNOWN, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.db = db
        self.version = version
        self.report = version_info.collect_report(
            version=version,
            config_file=getattr(config, "file", None),
            db=db,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(f"FPDB {self.report.version}")
        title.setObjectName("versionInfoTitle")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        self.browser = QTextBrowser()
        self.browser.setObjectName("versionInfoBrowser")
        # The links are the whole point of the "Links" section, and a QTextBrowser
        # would otherwise try to navigate to them inside itself and blank the view.
        self.browser.setOpenExternalLinks(True)
        self.browser.setHtml(self._build_html())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.browser)
        layout.addWidget(scroll, stretch=1)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton(_("Copy report"))
        self.copy_button.setToolTip(_("Copy these details to the clipboard for a bug report"))
        self.copy_button.clicked.connect(self.copy_report)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        self.status_label = QLabel("")
        buttons.addWidget(self.status_label)
        layout.addLayout(buttons)

    def _build_html(self) -> str:
        rows = "".join(
            "<tr>"
            f'<td style="padding: 4px 18px 4px 0; white-space: nowrap; font-weight: bold;">{_escape(label)}</td>'
            f'<td style="padding: 4px 0;">{_escape(value)}</td>'
            "</tr>"
            for label, value in report_rows(self.report)
        )
        links = "".join(
            f'<li><a href="{url}">{_escape(label)}</a></li>'
            for label, url in (
                (_("GitHub repository"), version_info.REPOSITORY_URL),
                (_("Documentation"), version_info.DOCUMENTATION_URL),
                (_("Report an issue"), version_info.ISSUES_URL),
            )
        )
        return (
            '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">'
            f"<h3>{_escape(_('Version and environment'))}</h3>"
            f'<table style="border-collapse: collapse;">{rows}</table>'
            f"<h3>{_escape(_('Links'))}</h3>"
            f"<ul>{links}</ul>"
            "</div>"
        )

    def copy_report(self) -> None:
        """Put the plain-text report on the clipboard and confirm it happened.

        Without the confirmation the button looks inert -- nothing on screen
        changes -- and users click it repeatedly wondering whether it worked.
        """
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:  # no display / offscreen platform plugin
            self.status_label.setText(_("Clipboard unavailable"))
            return
        clipboard.setText(report_as_text(self.report))
        self.status_label.setText(_("Report copied to clipboard"))
