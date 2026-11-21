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


def test_a_cash_multiway_all_in_is_priced_in_chips_and_marked_multiway(
    qtbot, config, importer, fresh_db, tmp_path
) -> None:
    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_3way_allin.txt")
    replayer.all_decisions.setChecked(True)

    # The step of the last all-in call: the hero is in a 3-way all-in on one pot.
    replayer.stateSlider.setValue(5)
    qtbot.wait(30)
    frame = replayer._frame_from_state(replayer.states[5])
    panel = replayer._decision_panel(frame, 5)
    titles = [section.title for section in panel.sections]
    assert "Cash — all-in" in titles
    allin = next(section for section in panel.sections if section.title == "Cash — all-in")
    values = {row.label: row.value for row in allin.rows}
    assert values["All-in EV"].startswith("+$")
    assert values["Equity at the all-in"].endswith("%")
    assert any("Multiway all-in on a single pot" in row.label for row in allin.rows)
    # No ICM or bounty section in a cash hand.
    assert not any("ICM" in title or "bounty" in title.lower() for title in titles)
    # The call someone faces in the multiway pot says the odds are against all of them.
    call = next(section for section in panel.sections if "to call" in section.title)
    assert any("Multiway pot: 2 opponents" in row.label for row in call.rows)
    paint_every_step(replayer)


def test_the_timeline_lines_carry_their_action_and_the_selection_follows_the_slider(
    qtbot, config, importer, fresh_db, tmp_path
) -> None:
    from fpdb_3_legacy.replay_history import action_style

    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")

    replayer.stateSlider.setValue(2)
    rows = replayer.inspector.timeline_rows
    action_rows = [row for row in rows if row.kind == "action"]
    assert action_rows and all(row.action for row in action_rows)
    # Each line's colours come from its action verb, not from parsing its text.
    verbs = {row.action for row in action_rows}
    assert "folds" not in verbs or action_style("folds").foreground == "#FF7186"
    selected = replayer.inspector.timeline.currentRow()
    assert 0 <= selected < len(rows)
    assert rows[selected].index == 2

    # Stepping forward moves the selection; the end of the hand selects "Hand complete".
    replayer.stateSlider.setValue(replayer.stateSlider.maximum())
    rows = replayer.inspector.timeline_rows
    selected = replayer.inspector.timeline.currentRow()
    assert rows[selected].index == replayer.stateSlider.maximum()
    assert rows[selected].text == "Hand complete"
    replayer.grab()  # the delegate paints every line, selected included


def test_tiles_are_coloured_by_their_semantic_key(qtbot) -> None:
    from fpdb_3_legacy.replay_inspector import TILE_STYLES, ReplayInspector
    from fpdb_3_legacy.replayer_panel import PanelRow

    inspector = ReplayInspector()
    qtbot.addWidget(inspector)

    for key, (foreground, _background) in TILE_STYLES.items():
        tile = inspector._tile(PanelRow(key, "1", key=key))
        assert foreground in tile.styleSheet()
    # A key figure without a colour of its own keeps the neutral tile.
    assert inspector._tile(PanelRow("SPR", "0.93", key="")).styleSheet() == ""
    # The accent adds a thicker frame on top of the key colour.
    accent = inspector._tile(PanelRow("Required equity", "32.5%", key="required_equity", accent=True))
    assert "2px solid #F7D54A" in accent.styleSheet()
    # The tile's own box only: a QFrame rule would also outline its QLabel children.
    assert "QFrame" not in accent.styleSheet() and "#inspectorTileAccent" in accent.styleSheet()


def test_a_functional_band_colours_the_row_value(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    from fpdb_3_legacy.replay_inspector import TONE_STYLES, ReplayInspector
    from fpdb_3_legacy.replayer_panel import PanelRow

    inspector = ReplayInspector()
    qtbot.addWidget(inspector)

    low = inspector._row(PanelRow("SPR", "2.5", tone="low"))
    foreground, background = TONE_STYLES["low"]
    assert background in low.styleSheet()  # the whole row is the chip
    values = [label for label in low.findChildren(QLabel) if label.text() == "2.5"]
    assert values and foreground in values[0].styleSheet()
    plain = inspector._row(PanelRow("SPR", "5"))
    plain_values = [label for label in plain.findChildren(QLabel) if label.text() == "5"]
    assert plain_values and plain_values[0].styleSheet() == "" and plain.styleSheet() == ""


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
    # Open, the panel sits beside the table, on the right of the splitter.
    assert replayer.main_splitter.widget(1) is replayer.inspector
    assert replayer.inspector.collapse_button.text() == "⟩"

    replayer.inspector.set_collapsed(True)
    assert replayer.inspector.maximumWidth() <= 40
    # Collapsed, the strip stays on the right edge, where the panel lives.
    assert replayer.main_splitter.widget(1) is replayer.inspector
    assert replayer.inspector.collapse_button.text() == "⟨"
    replayer.grab()

    replayer.inspector.set_collapsed(False)
    assert replayer.inspector.minimumWidth() >= 300
    assert replayer.main_splitter.widget(1) is replayer.inspector
    replayer.grab()
