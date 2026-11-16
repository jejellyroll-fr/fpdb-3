"""Offscreen checks for the replayer's action history window (#825)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox

from fpdb_3_legacy.GuiReplayer import GuiReplayer

pytestmark = pytest.mark.qt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hands" / "pokerstars"


@pytest.fixture
def replayer(qtbot, importer, fresh_db, legacy_config, tmp_path):
    source = FIXTURES / "holdem" / "cash_nl_6max.txt"
    copy = tmp_path / source.name
    copy.write_bytes(source.read_bytes())
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()

    widget = GuiReplayer(legacy_config, fresh_db.sql, MagicMock(), [hand_id], db=fresh_db)
    qtbot.addWidget(widget)
    assert not widget.historyButton.isEnabled()
    widget.play_hand(0)
    return widget


def rows(dialog):
    return [dialog.list.item(row).text() for row in range(dialog.list.count())]


def test_a_opens_the_history_on_the_current_step(qtbot, replayer) -> None:
    assert replayer.historyButton.isEnabled()

    qtbot.keyClick(replayer, Qt.Key.Key_A)

    dialog = replayer.historyDialog
    assert dialog is not None and dialog.isVisible()
    texts = rows(dialog)
    assert texts[0] == "Blinds and antes"
    assert "Player1: raises to $3.00" in texts
    assert "Player2: calls $2.50" in texts
    assert texts[-2:] == ["Hand complete", "Player2: collected $95.00"]
    assert dialog.list.currentRow() == 0


def test_clicking_an_entry_seeks_to_it(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.historyDialog
    row = rows(dialog).index("Flop dealt: As Ks 2d")

    item = dialog.list.item(row)
    qtbot.mouseClick(dialog.list.viewport(), Qt.MouseButton.LeftButton, pos=dialog.list.visualItemRect(item).center())

    assert replayer.stateSlider.value() == dialog.entries[row].index
    assert replayer.states[replayer.stateSlider.value()].street == "FLOP"
    assert dialog.list.currentRow() == row


def test_enter_seeks_to_the_selected_entry(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.historyDialog
    row = rows(dialog).index("Player2: raises to $20.00")
    dialog.list.setCurrentRow(row)
    dialog.list.setFocus()

    qtbot.keyClick(dialog.list, Qt.Key.Key_Return)

    assert replayer.stateSlider.value() == dialog.entries[row].index


def test_the_selection_follows_the_replay(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.historyDialog

    replayer.next_clicked(False)
    assert dialog.current_entry().text == "Player2: posts small blind $0.50"

    # The stepping keys keep working from the history window.
    qtbot.keyClick(dialog.list, Qt.Key.Key_Right)
    assert replayer.stateSlider.value() == 2
    assert dialog.current_entry().text == "Player3: posts big blind $1.00"

    qtbot.keyClick(dialog.list, Qt.Key.Key_End)
    assert dialog.current_entry().text == "Hand complete"

    qtbot.keyClick(dialog.list, Qt.Key.Key_Home)
    assert dialog.list.currentRow() == 0


def test_a_winner_clicked_at_the_end_stays_selected(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.historyDialog
    last = dialog.list.count() - 1

    dialog.list.setCurrentRow(last)
    dialog._item_chosen(dialog.list.item(last))

    assert replayer.stateSlider.value() == replayer.stateSlider.maximum()
    assert dialog.list.currentRow() == last


def test_a_closes_the_history_again(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.historyDialog

    qtbot.keyClick(dialog.list, Qt.Key.Key_A)
    assert not dialog.isVisible()

    qtbot.keyClick(replayer, Qt.Key.Key_A)
    assert dialog.isVisible()
    replayer.history_clicked()
    assert not dialog.isVisible()


def test_seeking_pauses_playback(qtbot, replayer) -> None:
    replayer.history_clicked()
    replayer.play_clicked(False)
    assert replayer.playing

    replayer.history_seek(5)

    assert not replayer.playing
    assert replayer.stateSlider.value() == 5


def test_amounts_follow_the_big_blind_toggle(qtbot, replayer) -> None:
    # The toggle of #824, as the replayer exposes it: a checkbox and the blind in use.
    toggle = QCheckBox()
    replayer.bbAmounts = toggle
    replayer._active_big_blind = lambda: Decimal(1) if toggle.isChecked() else None

    replayer.history_clicked()
    dialog = replayer.historyDialog
    assert "Player1: raises to $3.00" in rows(dialog)

    toggle.setChecked(True)
    assert "Player1: raises to 3 BB" in rows(dialog)
    assert rows(dialog)[-1] == "Player2: collected 95 BB"

    toggle.setChecked(False)
    assert "Player1: raises to $3.00" in rows(dialog)
