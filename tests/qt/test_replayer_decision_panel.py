"""The replayer's painted decision panel: layout, detail toggle and tooltips (#872)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QHelpEvent

from fpdb_3_legacy import replayer_panel
from fpdb_3_legacy.GuiReplayer import GuiReplayer, build_replay_layout, order_players_clockwise

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


def panel_box(replayer: GuiReplayer) -> tuple[float, float, float]:
    """The panel's left edge, right edge, and the timeline's left edge (or the window's right margin)."""
    state = replayer.states[replayer.stateSlider.value()]
    frame = replayer._frame_from_state(state)
    frame.players = order_players_clockwise(frame.players, replayer.Heroes)
    category = replayer.replay_model.hand.gametype.get("category", "")
    layout = build_replay_layout(
        replayer.width(), replayer.height(), [p.name for p in frame.players], replayer.Heroes, category
    )
    x, width = replayer._summary_rect_x_width(layout)
    limit = replayer.width() - 28 if layout.timeline_rect.isNull() else layout.timeline_rect.x() - 16
    return x, x + width, limit


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


@pytest.mark.parametrize("size", [(800, 600), (1000, 700), (1600, 1000)])
def test_the_panel_stays_beside_the_timeline_with_long_translations(
    qtbot, config, importer, fresh_db, tmp_path, monkeypatch, size
) -> None:
    long = " ".join(["much longer translated wording"] * 3)
    monkeypatch.setattr(replayer_panel, "_", lambda message: f"{message} {long}")
    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")
    replayer.resize(*size)
    replayer.all_decisions.setChecked(True)
    replayer.detailed_analysis.setChecked(True)

    for index in range(replayer.stateSlider.maximum() + 1):
        replayer.stateSlider.setValue(index)
        replayer.grab()
        left, right, limit = panel_box(replayer)
        assert left >= 28
        assert right <= limit + 0.5
        for area, _text in replayer._panel_tips:
            assert area.right() <= right
            assert area.bottom() <= replayer.height()


def test_hovering_a_figure_explains_it(qtbot, config, importer, fresh_db, tmp_path) -> None:
    replayer = replay(qtbot, config, importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")
    replayer.all_decisions.setChecked(True)
    replayer.detailed_analysis.setChecked(True)

    tips = []
    for index in range(replayer.stateSlider.maximum() + 1):
        replayer.stateSlider.setValue(index)
        replayer.grab()
        if replayer._panel_tips:
            tips = list(replayer._panel_tips)
            break
    assert tips, "no step of the hand showed a decision figure"

    area, text = tips[0]
    center = area.center().toPoint()
    assert text
    assert replayer.event(QHelpEvent(QEvent.Type.ToolTip, center, replayer.mapToGlobal(center)))
    # Outside every figure, no tooltip: the event is still handled.
    assert replayer.event(QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), replayer.mapToGlobal(QPoint(1, 1))))
