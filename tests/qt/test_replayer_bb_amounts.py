"""The replayer's "Big blinds" toggle: amounts counted in big blinds (#824).

After thecrawler1's fork (thecrawler1/fpdb-3, "switch replay amounts to big blinds").
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.GuiReplayer import GuiReplayer, format_replay_amount
from fpdb_3_legacy.localized_formats import format_number
from fpdb_3_legacy.replayer_panel import CallFigures, actor_section

pytestmark = pytest.mark.qt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hands" / "pokerstars"


@pytest.fixture
def config(legacy_config, monkeypatch):
    """The test configuration, with saving recorded instead of written over HUD_config.xml."""
    saves: list[None] = []
    monkeypatch.setattr(legacy_config, "save", lambda *args, **kwargs: saves.append(None))
    legacy_config.general.pop("replayer_amounts", None)
    legacy_config.saves = saves
    return legacy_config


def import_hand(importer, fresh_db, tmp_path, relative: str) -> int:
    source = FIXTURES / relative
    copy = tmp_path / source.name
    copy.write_bytes(source.read_bytes())
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()
    return hand_id


def replay(qtbot, config, fresh_db, hand_id: int) -> GuiReplayer:
    replayer = GuiReplayer(config, fresh_db.sql, MagicMock(), [hand_id], db=fresh_db)
    qtbot.addWidget(replayer)
    replayer.play_hand(0)
    return replayer


def final_frame(replayer: GuiReplayer):
    replayer.stateSlider.setValue(replayer.stateSlider.maximum())
    return replayer._frame_from_state(replayer.states[-1])


def test_amounts_are_counted_in_big_blinds_when_asked() -> None:
    assert format_replay_amount(Decimal(100), "USD", blind=Decimal(1)) == "100 BB"
    assert format_replay_amount(Decimal("2.50"), "USD", blind=Decimal(1)) == f"{format_number(Decimal('2.5'), 1)} BB"
    assert format_replay_amount(Decimal(1), "USD", blind=Decimal(3)) == f"{format_number(Decimal('0.33'), 2)} BB"
    assert format_replay_amount(Decimal(1500), "T$", blind=Decimal(20)) == "75 BB"
    # Without a blind, money and chips are formatted as before.
    assert format_replay_amount(Decimal(1500), "T$") == format_number(Decimal(1500))


def test_the_toggle_is_off_by_default(qtbot, config, importer, fresh_db, tmp_path) -> None:
    replayer = replay(qtbot, config, fresh_db, import_hand(importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt"))

    assert replayer.bb_amounts_box.isEnabled()
    assert not replayer.bb_amounts_box.isChecked()
    assert replayer._amount(Decimal(100)) == format_replay_amount(Decimal(100), "USD")


def test_a_cash_hand_shows_stacks_bets_pots_and_actions_in_big_blinds(
    qtbot, config, importer, fresh_db, tmp_path
) -> None:
    replayer = replay(qtbot, config, fresh_db, import_hand(importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt"))

    replayer.bb_amounts_box.setChecked(True)

    assert replayer.replay_blind == Decimal("1.00")
    assert replayer._amount(Decimal(100)) == "100 BB"
    # Player1's open to $3.00 is 3 BB, in the action line and the timeline.
    raise_index = next(
        index
        for index, state in enumerate(replayer.states)
        if any(p.name == "Player1" and p.justacted and p.action == "raises" for p in state.players.values())
    )
    replayer.stateSlider.setValue(raise_index)
    frame = replayer._frame_from_state(replayer.states[raise_index])
    assert replayer._current_action_summary(frame) == "Player1 raises 3 BB"
    assert "Player1: raises 3 BB" in replayer._timeline_entries(max_entries=50)
    # Every amount of the hand follows: no dollar figure is left in the timeline.
    final_frame(replayer)
    assert all("$" not in entry for entry in replayer._timeline_entries(max_entries=50))
    # Rendering the table with the toggle on draws without error.
    replayer.grab()


def test_the_hero_decision_summary_follows_the_toggle(qtbot, config, importer, fresh_db, tmp_path) -> None:
    replayer = replay(qtbot, config, fresh_db, import_hand(importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt"))

    def call_amount() -> str:
        call = CallFigures(call_amount=Decimal("2.50"), pot_odds_pct=Decimal(25))
        section = actor_section("Hero", amount=replayer._amount, call=call)
        return dict((row.label, row.value) for row in section.rows)["Call amount"]

    assert call_amount().startswith("$")
    replayer.bb_amounts_box.setChecked(True)
    assert call_amount() == f"{format_number(Decimal('2.5'), 1)} BB"


def test_a_tournament_hand_counts_chips_in_its_big_blind(qtbot, config, importer, fresh_db, tmp_path) -> None:
    replayer = replay(qtbot, config, fresh_db, import_hand(importer, fresh_db, tmp_path, "holdem/tournament_ko.txt"))
    replayer.bb_amounts_box.setChecked(True)

    assert replayer.replay_blind == Decimal(20)
    start = replayer._frame_from_state(replayer.states[0])
    stacks = {player.name: replayer._amount(player.stack) for player in start.players}
    assert stacks["Player3"] == "75 BB"
    final_frame(replayer)
    assert "Player1: collected 151 BB" in replayer._timeline_entries(max_entries=50)

    replayer.bb_amounts_box.setChecked(False)
    assert "Player1: collected 151 BB" not in replayer._timeline_entries(max_entries=50)


def test_the_toggle_is_remembered_between_sessions(qtbot, config, importer, fresh_db, tmp_path) -> None:
    hand_id = import_hand(importer, fresh_db, tmp_path, "holdem/cash_nl_6max.txt")
    replay(qtbot, config, fresh_db, hand_id).bb_amounts_box.setChecked(True)

    assert config.get_replayer_amounts_in_bb()
    assert config.saves
    assert all(node.getAttribute("replayer_amounts") == "bb" for node in config.doc.getElementsByTagName("general"))
    reopened = replay(qtbot, config, fresh_db, hand_id)
    assert reopened.bb_amounts_box.isChecked()
    assert reopened._amount(Decimal(100)) == "100 BB"

    reopened.bb_amounts_box.setChecked(False)
    assert not config.get_replayer_amounts_in_bb()
    assert not any(node.hasAttribute("replayer_amounts") for node in config.doc.getElementsByTagName("general"))


def test_a_hand_without_a_big_blind_disables_the_toggle(qtbot, config, importer, fresh_db, tmp_path) -> None:
    config.general["replayer_amounts"] = "bb"
    replayer = replay(qtbot, config, fresh_db, import_hand(importer, fresh_db, tmp_path, "stud/7stud.txt"))

    assert not replayer.bb_amounts_box.isEnabled()
    assert "no big blind" in replayer.bb_amounts_box.toolTip()
    # The remembered preference is kept, but the stud hand stays in money.
    assert replayer.bb_amounts_box.isChecked()
    assert replayer._active_big_blind() is None
    assert all(" BB" not in entry for entry in replayer._timeline_entries(max_entries=50))


def test_the_splash_pot_marker_follows_the_toggle() -> None:
    hand = SimpleNamespace(gametype={"currency": "USD"}, bombPot=0, splashPot=200)

    assert GuiReplayer._special_pot_suffix(hand) == "  ·  Splash pot: 2.00USD"
    assert GuiReplayer._special_pot_suffix(hand, Decimal("0.50")) == "  ·  Splash pot: 4 BB"
