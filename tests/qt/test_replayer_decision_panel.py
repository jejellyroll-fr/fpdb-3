"""The replayer's painted decision panel: layout, detail toggle and tooltips (#872)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.GuiReplayer import GuiReplayer

pytestmark = pytest.mark.qt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hands" / "pokerstars"


@pytest.fixture
def config(legacy_config, monkeypatch):
    monkeypatch.setattr(legacy_config, "save", lambda *args, **kwargs: None)
    return legacy_config


def replay(qtbot, config, importer, fresh_db, tmp_path, relative: str) -> GuiReplayer:
    source = FIXTURES / relative
    copy = tmp_path / source.name
    copy.write_bytes(source.read_bytes())
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()
    replayer = GuiReplayer(config, fresh_db.sql, MagicMock(), [hand_id], db=fresh_db)
    qtbot.addWidget(replayer)
    replayer.play_hand(0)
    return replayer


def paint_every_step(replayer: GuiReplayer) -> None:
    for index in range(replayer.stateSlider.maximum() + 1):
        replayer.stateSlider.setValue(index)
        replayer.grab()


def test_the_controls_keep_odds_for_all_players_and_add_the_detailed_view(
    qtbot, config, importer, fresh_db, tmp_path
) -> None:
    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")

    assert not replayer.all_decisions.isChecked()
    assert not replayer.detailed_analysis.isChecked()
    for all_players in (False, True):
        for detailed in (False, True):
            replayer.all_decisions.setChecked(all_players)
            replayer.detailed_analysis.setChecked(detailed)
            paint_every_step(replayer)


def test_the_inspector_follows_the_step_and_a_click_seeks(qtbot, config, importer, fresh_db, tmp_path) -> None:
    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")
    replayer.stateSlider.setValue(replayer.stateSlider.maximum() - 3)

    rows = replayer.inspector.timeline_rows
    assert rows and rows[-1].index <= replayer.stateSlider.value()
    assert any(row.kind == "street" for row in rows)
    first_action = next(row for row in rows if row.kind == "action")
    replayer.inspector.seek_requested.emit(first_action.index)
    assert replayer.stateSlider.value() == first_action.index


def test_the_advanced_toggle_and_the_checkbox_stay_in_step(qtbot, config, importer, fresh_db, tmp_path) -> None:
    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")
    for index in range(replayer.stateSlider.maximum() + 1):
        replayer.stateSlider.setValue(index)
        if replayer.inspector.advanced_button is not None:
            break
    assert replayer.inspector.advanced_button is not None

    replayer.inspector.advanced_button.click()
    assert replayer.detailed_analysis.isChecked()
    replayer.detailed_analysis.setChecked(False)
    assert not replayer.inspector.detailed


def test_the_inspector_folds_to_a_strip(qtbot, config, importer, fresh_db, tmp_path) -> None:
    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")
    replayer.inspector.set_collapsed(True)
    assert replayer.inspector.maximumWidth() <= 40
    replayer.grab()
    replayer.inspector.set_collapsed(False)
    assert replayer.inspector.minimumWidth() >= 300
