"""Offscreen checks for the hand share menu and dialog (#400)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QMenu

from fpdb_3_legacy.GuiReplayer import GuiReplayer
from fpdb_3_legacy.hand_share_dialog import HandShareDialog, add_share_actions
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

pytestmark = pytest.mark.qt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hands" / "pokerstars"


def parse(config, relative: str):
    return PokerStars(config=config, in_path=str(FIXTURES / relative), autostart=True).getProcessedHands()[0]


def menu_actions(menu: QMenu) -> dict[str, object]:
    return {action.text(): action for action in menu.actions() if action.text()}


def test_the_menu_copies_markdown_to_the_clipboard(qtbot, legacy_config) -> None:
    menu = QMenu()
    add_share_actions(menu, parse(legacy_config, "holdem/cash_nl_6max.txt"))

    actions = menu_actions(menu)
    assert list(actions) == ["Copy as text", "Copy as Markdown", "Copy as Markdown in BB", "Share..."]

    actions["Copy as Markdown in BB"].trigger()
    text = QApplication.clipboard().text()
    assert text.startswith("**NL Hold'em 6-max - $0.50/$1.00 (amounts in BB)**")
    assert "Player1" not in text


def test_the_bb_copy_is_disabled_for_stud(qtbot, legacy_config) -> None:
    menu = QMenu()
    add_share_actions(menu, parse(legacy_config, "stud/7stud.txt"))

    assert not menu_actions(menu)["Copy as Markdown in BB"].isEnabled()


def test_the_dialog_previews_what_it_copies(qtbot, legacy_config) -> None:
    dialog = HandShareDialog(parse(legacy_config, "holdem/cash_nl_6max.txt"))
    qtbot.addWidget(dialog)

    assert dialog.preview.toPlainText().startswith("NL Hold'em 6-max - $0.50/$1.00\n")

    dialog.format_combo.setCurrentIndex(dialog.format_combo.findData("bbcode"))
    dialog.anonymize_combo.setCurrentIndex(dialog.anonymize_combo.findData("none"))
    dialog.checks["hand_id"].setChecked(True)

    preview = dialog.preview.toPlainText()
    assert preview.startswith("[b]NL Hold'em")
    assert "Hand #1234567890" in preview
    assert "Player2 wins $95.00" in preview

    dialog.copy()
    assert QApplication.clipboard().text() == preview


def test_the_dialog_saves_to_a_file(qtbot, legacy_config, tmp_path, monkeypatch) -> None:
    dialog = HandShareDialog(parse(legacy_config, "holdem/cash_nl_6max.txt"))
    qtbot.addWidget(dialog)
    target = tmp_path / "hand.md"
    monkeypatch.setattr(
        "fpdb_3_legacy.hand_share_dialog.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(target), ""),
    )

    dialog.save()

    assert target.read_text(encoding="utf-8") == dialog.preview.toPlainText()


def test_stud_cannot_pick_big_blinds_in_the_dialog(qtbot, legacy_config) -> None:
    dialog = HandShareDialog(parse(legacy_config, "stud/7stud.txt"))
    qtbot.addWidget(dialog)

    bb_index = dialog.amounts_combo.findData("bb")
    assert not dialog.amounts_combo.model().item(bb_index).isEnabled()


def test_the_replayer_shares_the_hand_it_plays(qtbot, importer, fresh_db, legacy_config, tmp_path) -> None:
    source = FIXTURES / "holdem" / "cash_nl_6max.txt"
    copy = tmp_path / source.name
    copy.write_bytes(source.read_bytes())
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()

    replayer = GuiReplayer(legacy_config, fresh_db.sql, MagicMock(), [hand_id], db=fresh_db)
    qtbot.addWidget(replayer)
    assert not replayer.shareButton.isEnabled()

    replayer.play_hand(0)

    assert replayer.shareButton.isEnabled()
    assert str(replayer.shared_hand.handid) == "1234567890"
