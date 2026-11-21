"""Offscreen checks for the replayer's action history window (#825)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox

from fpdb_3_legacy.GuiReplayer import GuiReplayer
from fpdb_3_legacy.replay_history import ReplayHistoryEntry
from fpdb_3_legacy.replay_history_dialog import ReplayHistoryDialog

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
    assert not widget.history_button.isEnabled()
    widget.play_hand(0)
    return widget


def rows(dialog):
    return [dialog.list.item(row).text() for row in range(dialog.list.count())]


def test_a_opens_the_history_on_the_current_step(qtbot, replayer) -> None:
    assert replayer.history_button.isEnabled()

    qtbot.keyClick(replayer, Qt.Key.Key_A)

    dialog = replayer.history_dialog
    assert dialog is not None and dialog.isVisible()
    texts = rows(dialog)
    assert texts[0] == "Blinds and antes"
    assert "Player1: raises [Ah Kh]" in texts
    # "Hide Cards" is on by default: the villain's hand stays hidden in the history too.
    assert "Player2: calls $2.50" in texts
    assert not any("[2s 2c]" in text for text in texts)
    assert texts[-2:] == ["Hand complete", "Player2: collected $95.00"]
    assert dialog.list.currentRow() == 0


def test_clicking_an_entry_seeks_to_it(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.history_dialog
    row = rows(dialog).index("Flop dealt: As Ks 2d")

    item = dialog.list.item(row)
    qtbot.mouseClick(dialog.list.viewport(), Qt.MouseButton.LeftButton, pos=dialog.list.visualItemRect(item).center())

    assert replayer.stateSlider.value() == dialog.entries[row].index
    assert replayer.states[replayer.stateSlider.value()].street == "FLOP"
    assert dialog.list.currentRow() == row


def test_unhiding_the_cards_shows_the_villain_s_hand_in_the_history(qtbot, replayer) -> None:
    replayer.history_clicked()
    replayer.showCards.setChecked(False)

    assert "Player2: calls [2s 2c]" in rows(replayer.history_dialog)


def test_enter_seeks_to_the_selected_entry(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.history_dialog
    row = rows(dialog).index("Player2: raises to $20.00")
    dialog.list.setCurrentRow(row)
    dialog.list.setFocus()

    qtbot.keyClick(dialog.list, Qt.Key.Key_Return)

    assert replayer.stateSlider.value() == dialog.entries[row].index


def test_keypad_enter_seeks_too(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.history_dialog
    row = rows(dialog).index("Flop dealt: As Ks 2d")
    dialog.list.setCurrentRow(row)
    dialog.list.setFocus()

    qtbot.keyClick(dialog.list, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)

    assert replayer.stateSlider.value() == dialog.entries[row].index


def test_enter_seeks_once_on_every_platform(qtbot) -> None:
    # Enter is handled by the dialog, not left to itemActivated: on macOS the
    # list does not emit it for Enter, and elsewhere it would seek a second time.
    seeks: list[int] = []
    dialog = ReplayHistoryDialog(None, seeks.append)
    qtbot.addWidget(dialog)
    dialog.set_entries([ReplayHistoryEntry(index=i, kind="action", text=f"step {i}") for i in (3, 7)], 3)
    dialog.show()
    dialog.list.setCurrentRow(1)
    dialog.list.setFocus()

    qtbot.keyClick(dialog.list, Qt.Key.Key_Return)

    assert seeks == [7]


def test_the_selection_follows_the_replay(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.history_dialog

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


def test_a_winner_clicked_at_the_end_stays_selected(replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.history_dialog
    last = dialog.list.count() - 1

    dialog.list.setCurrentRow(last)
    dialog._item_chosen(dialog.list.item(last))

    assert replayer.stateSlider.value() == replayer.stateSlider.maximum()
    assert dialog.list.currentRow() == last


def test_a_closes_the_history_again(qtbot, replayer) -> None:
    replayer.history_clicked()
    dialog = replayer.history_dialog

    qtbot.keyClick(dialog.list, Qt.Key.Key_A)
    assert not dialog.isVisible()

    qtbot.keyClick(replayer, Qt.Key.Key_A)
    assert dialog.isVisible()
    replayer.history_clicked()
    assert not dialog.isVisible()


def test_seeking_pauses_playback(replayer) -> None:
    replayer.history_clicked()
    replayer.play_clicked(False)
    assert replayer.playing

    replayer.history_seek(5)

    assert not replayer.playing
    assert replayer.stateSlider.value() == 5


def test_amounts_follow_the_big_blind_toggle(replayer) -> None:
    # The toggle of #824, as the replayer exposes it: a checkbox and the blind in use.
    toggle = QCheckBox()
    replayer.bbAmounts = toggle
    replayer._active_big_blind = lambda: Decimal(1) if toggle.isChecked() else None

    replayer.history_clicked()
    dialog = replayer.history_dialog
    assert "Player1: raises [Ah Kh]" in rows(dialog)

    toggle.setChecked(True)
    assert "Player1: raises [Ah Kh]" in rows(dialog)  # amount kept on the entry
    assert rows(dialog)[-1] == "Player2: collected 95 BB"

    toggle.setChecked(False)
    assert "Player1: raises [Ah Kh]" in rows(dialog)
