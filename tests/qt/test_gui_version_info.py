"""The Version tab renders every collected fact, and can hand it to the user.

Issue #226: the point of the tab is that a user can read their build's identity
off one screen and paste it into an issue. These tests hold that end of it --
the rows actually reach the view, arbitrary paths cannot break the HTML, and the
copy button produces text worth pasting.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import version_info

pytest.importorskip("PySide6.QtWidgets")

from fpdb_3_legacy import GuiVersionInfo  # noqa: E402 - after the Qt availability probe


class _Config:
    def __init__(self, file="/tmp/HUD_config.xml") -> None:
        self.file = file


class _Db:
    def get_backend_name(self):
        return "SQLite"

    def is_connected(self):
        return True


@pytest.fixture
def version_tab(qtbot):
    widget = GuiVersionInfo.GuiVersionInfo(config=_Config(), db=_Db(), version="3.6.4")
    qtbot.addWidget(widget)
    return widget


@pytest.mark.qt
def test_the_tab_shows_the_version_packaging_and_environment(version_tab) -> None:
    rendered = version_tab.browser.toPlainText()

    assert "3.6.4" in rendered
    for label in ("FPDB version", "Packaging", "Python", "PySide6", "SQLite", "Configuration file", "Database"):
        assert label in rendered, f"missing row: {label}"


@pytest.mark.qt
def test_the_tab_links_to_the_repository_and_the_issue_tracker(version_tab) -> None:
    html = version_tab.browser.toHtml()

    assert version_info.REPOSITORY_URL in html
    assert version_info.ISSUES_URL in html


@pytest.mark.qt
def test_links_open_in_a_browser_instead_of_blanking_the_view(version_tab) -> None:
    """A QTextBrowser navigates internally by default, which would replace the
    report with a failed page load."""
    assert version_tab.browser.openExternalLinks()


@pytest.mark.qt
def test_the_tab_shows_the_active_configuration_file_and_database(version_tab) -> None:
    rendered = version_tab.browser.toPlainText()

    assert "/tmp/HUD_config.xml" in rendered
    assert "SQLite" in rendered


@pytest.mark.qt
def test_a_config_path_with_markup_characters_is_not_swallowed_by_the_html(qtbot) -> None:
    """Windows paths and profile names carry & and <; unescaped they would eat
    the rest of the line the reader needs."""
    widget = GuiVersionInfo.GuiVersionInfo(config=_Config(file="C:/A&B/<hero>/HUD_config.xml"), version="3.6.4")
    qtbot.addWidget(widget)

    assert "C:/A&B/<hero>/HUD_config.xml" in widget.browser.toPlainText()


@pytest.mark.qt
def test_copying_the_report_puts_the_same_facts_on_the_clipboard(version_tab) -> None:
    from PySide6.QtGui import QGuiApplication

    version_tab.copy_report()
    copied = QGuiApplication.clipboard().text()

    assert "3.6.4" in copied
    assert "Python" in copied
    assert version_tab.status_label.text()


@pytest.mark.qt
def test_the_tab_opens_before_a_database_exists(qtbot) -> None:
    """The Help menu is reachable at startup, before load_profile builds a Database."""
    widget = GuiVersionInfo.GuiVersionInfo(config=_Config(), db=None, version="3.6.4")
    qtbot.addWidget(widget)

    assert "not connected" in widget.browser.toPlainText()


def test_the_plain_text_report_is_fenced_for_pasting_into_an_issue() -> None:
    report = version_info.collect_report(version="3.6.4", config_file="/tmp/HUD_config.xml")

    text = GuiVersionInfo.report_as_text(report)

    assert text.startswith("```")
    assert text.rstrip().endswith("```")
    assert "3.6.4" in text


def test_the_rendered_rows_and_the_copied_text_come_from_the_same_source() -> None:
    """Two renderings of the same facts must not be able to disagree."""
    report = version_info.collect_report(version="3.6.4")

    text = GuiVersionInfo.report_as_text(report)

    for label, value in GuiVersionInfo.report_rows(report):
        assert label in text
        assert str(value) in text


def test_a_packaged_build_says_so_instead_of_showing_an_empty_git_row() -> None:
    report = version_info.VersionReport(
        version="3.6.4",
        packaging="PyInstaller",
        git=version_info.GitCheckout(is_repository=False),
    )

    rows = dict(GuiVersionInfo.report_rows(report))

    assert "Git checkout" in rows
    assert "Git commit" not in rows
