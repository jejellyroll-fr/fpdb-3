"""The update notice appears when GitHub announces a newer release, and nothing happens offline (#445).

The checker runs against a fake reader -- no network -- and the window is a
plain ``QMainWindow``, which is all the notice needs from fpdb's.
"""

from __future__ import annotations

import urllib.error

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QMainWindow, QMessageBox  # noqa: E402 - after the Qt availability probe

from fpdb_3_legacy import update_notice  # noqa: E402
from fpdb_3_legacy.update_check import LATEST_RELEASE_URL, Release  # noqa: E402
from fpdb_3_legacy.update_notice import UpdateChecker, UpdateNotice, present_result  # noqa: E402

NEWER = {
    "tag_name": "v3.10.0",
    "html_url": "https://github.com/jejellyroll-fr/fpdb-3/releases/tag/v3.10.0",
    "assets": [],
}


def answering(data):
    def reader(url: str, _timeout: float):
        assert url == LATEST_RELEASE_URL
        return data

    return reader


def offline(_url: str, _timeout: float):
    raise urllib.error.URLError("offline")


@pytest.fixture
def window(qtbot):
    win = QMainWindow()
    qtbot.addWidget(win)
    return win


def run_check(qtbot, window, reader, *, manual: bool = False):
    checker = UpdateChecker(window, reader=reader)
    with qtbot.waitSignal(checker.finished, timeout=5000) as blocker:
        checker.start("3.9.1", "Source", manual=manual)
    reached, release, was_manual = blocker.args
    present_result(window, reached, release, was_manual, "3.9.1")
    return reached, release


@pytest.mark.qt
def test_a_newer_release_puts_a_notice_in_the_status_bar(qtbot, window) -> None:
    reached, release = run_check(qtbot, window, answering(NEWER))

    assert reached
    assert release is not None and release.tag == "v3.10.0"
    notice = window.update_notice
    assert notice.parent() is not None
    text = notice.label.text()
    assert "v3.10.0" in text and "3.9.1" in text
    assert NEWER["html_url"] in text


@pytest.mark.qt
def test_offline_nothing_happens(qtbot, window, monkeypatch) -> None:
    asked = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: asked.append(a))

    reached, release = run_check(qtbot, window, offline)

    assert not reached
    assert release is None
    assert getattr(window, "update_notice", None) is None
    assert asked == []  # an automatic check that fails says nothing


@pytest.mark.qt
def test_an_up_to_date_build_shows_nothing_at_startup(qtbot, window) -> None:
    run_check(qtbot, window, answering({**NEWER, "tag_name": "v3.9.1"}))

    assert getattr(window, "update_notice", None) is None


@pytest.mark.qt
@pytest.mark.parametrize(
    ("reader", "box", "expected"),
    [
        (answering({**NEWER, "tag_name": "v3.9.1"}), "information", "latest"),
        (offline, "warning", "could not be reached"),
    ],
)
def test_a_manual_check_always_answers(qtbot, window, monkeypatch, reader, box, expected) -> None:
    shown = []
    monkeypatch.setattr(QMessageBox, box, lambda _parent, _title, text, *a, **k: shown.append(text))

    run_check(qtbot, window, reader, manual=True)

    assert len(shown) == 1 and expected in shown[0]


@pytest.mark.qt
def test_a_second_notice_replaces_the_first(qtbot, window) -> None:
    first = Release(tag="v3.10.0", page_url="https://example.invalid/a")
    second = Release(tag="v3.11.0", page_url="https://example.invalid/b")

    present_result(window, True, first, False, "3.9.1")
    replaced = window.update_notice
    present_result(window, True, second, False, "3.9.1")

    assert window.update_notice is not replaced
    assert "v3.11.0" in window.update_notice.label.text()
    notices = [w for w in window.statusBar().findChildren(UpdateNotice) if w is not replaced]
    assert notices == [window.update_notice]


@pytest.mark.qt
def test_the_notice_links_the_matching_archive_and_can_be_hidden(qtbot) -> None:
    release = Release(
        tag="v3.10.0",
        page_url="https://example.invalid/release",
        asset_name="fpdb-pyoxidizer-macos-arm64.tar.gz",
        asset_url="https://example.invalid/fpdb-pyoxidizer-macos-arm64.tar.gz",
    )
    notice = UpdateNotice(release, "3.9.1")
    qtbot.addWidget(notice)
    notice.show()

    assert "fpdb-pyoxidizer-macos-arm64.tar.gz" in notice.label.text()
    assert notice.label.openExternalLinks()
    notice.findChild(update_notice.QToolButton).click()
    assert not notice.isVisible()
