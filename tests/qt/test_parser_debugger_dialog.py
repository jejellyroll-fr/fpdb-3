"""Tools > Parser Debugger (#903): the window renders the report it is given.

Run offscreen; the file dialogs are the static ``QFileDialog`` calls, patched.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QLabel

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.parser_debugger_dialog import ParserDebuggerDialog, show_parser_debugger

pytestmark = pytest.mark.qt

ROOT = Path(__file__).resolve().parents[2]
SOKO = ROOT / "regression-test-files" / "unsupported-sites" / "soko" / "soko_2005_001_complete_anonymized.txt"
STARS = ROOT / "regression-test-files" / "cash" / "Stars" / "Flop" / "NLHE-6max-USD-0.05-0.10-200912.Allin-pre.txt"


@pytest.fixture(scope="module")
def config(tmp_path_factory) -> Config:
    path = tmp_path_factory.mktemp("config") / "HUD_config.xml"
    shutil.copyfile(ROOT / "HUD_config.xml", path)
    return Config(file=str(path))


@pytest.fixture
def dialog(qtbot, config) -> ParserDebuggerDialog:
    window = ParserDebuggerDialog(config)
    qtbot.addWidget(window)
    return window


def _rows(tree) -> list[list[str]]:
    return [
        [tree.topLevelItem(row).text(column) for column in range(tree.columnCount())]
        for row in range(tree.topLevelItemCount())
    ]


def test_the_site_list_offers_auto_detect_then_every_site(dialog) -> None:
    assert dialog.site_combo.itemData(0) is None
    assert "PokerStars.COM" in [dialog.site_combo.itemText(index) for index in range(dialog.site_combo.count())]


def test_nothing_to_parse_says_so(dialog) -> None:
    dialog.run()

    assert "Nothing to parse" in dialog.verdict_label.text()
    assert dialog.report is None


def test_a_pasted_refused_hand_shows_why(dialog) -> None:
    dialog.input.setPlainText(SOKO.read_text(encoding="utf-8"))
    dialog.run()

    assert "FAILED" in dialog.verdict_label.text()
    assert "UnsupportedGame" in dialog.summary.toPlainText()
    steps = {row[0]: row[1] for row in _rows(dialog.steps_tree)}
    assert steps["determineGameType"] == "raised"
    assert steps["readHandInfo"] == "not reached"
    rows = {dialog.steps_tree.topLevelItem(index).text(0): dialog.steps_tree.topLevelItem(index) for index in range(dialog.steps_tree.topLevelItemCount())}
    assert rows["determineGameType"].foreground(1).color().name() == "#ff9292"
    assert rows["readHandInfo"].foreground(1).color().name() == "#ffd080"
    legend = dialog.findChild(QLabel, "status_legend")
    assert legend is not None
    assert "#78e2a1" in legend.text()
    assert "#ffd080" in legend.text()
    assert "#ff9292" in legend.text()
    # The failing header line is coloured in the input.
    assert [selection.cursor.blockNumber() for selection in dialog.input.extraSelections()] == [0]


def test_an_opened_file_fills_every_tab(dialog, monkeypatch) -> None:
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *args, **kwargs: (str(STARS), "")))
    dialog.open_file()
    dialog.run()

    assert dialog.report is not None
    assert dialog.report.source == str(STARS)
    assert "OK" in dialog.verdict_label.text()
    assert dialog.hand_combo.count() == 1
    assert dialog.detection_tree.topLevelItemCount() > 10
    assert any(row[0] == "readPlayerStacks" and row[1] == "ok" for row in _rows(dialog.steps_tree))
    assert any(row[0] == "chip conservation" and row[1] == "pass" for row in _rows(dialog.contract_tree))
    steps = {dialog.steps_tree.topLevelItem(index).text(0): dialog.steps_tree.topLevelItem(index) for index in range(dialog.steps_tree.topLevelItemCount())}
    assert steps["readPlayerStacks"].foreground(1).color().name() == "#78e2a1"
    passed_check = next(
        dialog.contract_tree.topLevelItem(index)
        for index in range(dialog.contract_tree.topLevelItemCount())
        if dialog.contract_tree.topLevelItem(index).text(0) == "chip conservation"
    )
    assert passed_check.foreground(1).color().name() == "#78e2a1"
    detected = next(
        dialog.detection_tree.topLevelItem(index)
        for index in range(dialog.detection_tree.topLevelItemCount())
        if dialog.detection_tree.topLevelItem(index).text(2) == "yes"
    )
    assert detected.foreground(2).color().name() == "#78e2a1"
    assert dialog.hand_tree.topLevelItemCount() == 1
    assert any("re_player_info" in row[3] for row in _rows(dialog.lines_tree))
    assert dialog.expected_tree.topLevelItemCount() > 0
    assert json.loads(dialog.json_view.toPlainText())["verdict"] == "ok"


def test_editing_an_opened_file_debugs_the_text(dialog, monkeypatch) -> None:
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *args, **kwargs: (str(STARS), "")))
    dialog.open_file()
    dialog.input.setPlainText(dialog.input.toPlainText() + "\n")
    dialog.run()

    assert dialog.report is not None
    assert dialog.report.source == "pasted text"


def test_a_line_of_the_lines_tab_selects_it_in_the_input(dialog) -> None:
    dialog.input.setPlainText(STARS.read_text(encoding="utf-8"))
    dialog.run()
    item = dialog.lines_tree.topLevelItem(2)

    dialog._line_item_activated(item, 0)

    assert dialog.input.textCursor().selectedText() == "Seat 1: Blåveis ($55.10 in chips)"


def test_the_bug_report_is_copied(dialog) -> None:
    dialog.input.setPlainText(STARS.read_text(encoding="utf-8"))
    dialog.run()
    dialog.copy_bug_report()

    copied = QGuiApplication.clipboard().text()
    assert copied.startswith("### Parser Debugger report")
    assert "AAALISAAAA" not in copied


def test_save_then_compare(dialog, monkeypatch, tmp_path) -> None:
    saved = tmp_path / "report.json"
    dialog.input.setPlainText(STARS.read_text(encoding="utf-8"))
    dialog.trace_check.setChecked(False)
    dialog.run()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *args, **kwargs: (str(saved), "")))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *args, **kwargs: (str(saved), "")))

    dialog.save_report()
    dialog.compare_report()

    assert json.loads(saved.read_text(encoding="utf-8"))["verdict"] == "ok"
    assert dialog.changes_view.toPlainText() == "No change."


def test_show_parser_debugger_opens_a_modeless_window(qtbot, config) -> None:
    window = show_parser_debugger(config)
    qtbot.addWidget(window)

    assert window.isVisible()
    assert not window.isModal()
