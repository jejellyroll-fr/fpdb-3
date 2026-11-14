"""How a captured hand's normalized dict becomes an fpdb Hand.

``http_capture_hand_builder`` turns the room-independent hand dict a capture
produces into a :class:`Hand`, renders it as text and imports it. The dicts
under ``data/captured_*.json`` are hands CoinPoker's live capture once built
(player names anonymised), frozen when that capture was removed (#732): they
stay what a database written by it holds, and they still exercise the shared
mapping -- forced straddles, run-it-twice boards, bomb and splash pots, insured
cash-outs, tournaments, All-in or Fold.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    HttpCaptureHandConfig,
    _board_streets,
    build_fpdb_hand,
    import_fpdb_hand,
    render_fpdb_hand,
)
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.SQL import Sql

DATA = Path(__file__).parent / "data"
SITE_IDS = HttpCaptureHandConfig(site_ids={"CoinPoker": 30, "default": 30})


def _captured(name: str) -> dict[str, Any]:
    return json.loads((DATA / f"captured_{name}_hand.json").read_text(encoding="utf-8"))


def _hand_with(**overrides: Any) -> dict[str, Any]:
    hand = _captured("plo")
    hand.update(overrides)
    return hand


def _sqlite() -> Database:
    config = MagicMock()
    config.get_db_parameters.return_value = {
        "db-backend": 4,
        "db-server": "sqlite",
        "db-databaseName": ":memory:",
        "db-user": "",
        "db-password": "",
        "db-host": "",
        "db-port": "",
        "db-path": "",
    }
    config.get_import_parameters.return_value = {
        "saveActions": True,
        "callFpdbHud": False,
        "cacheSessions": False,
        "publicDB": False,
        "fastStoreHudCache": False,
        "sessionTimeout": 30,
    }
    config.get_general_params.return_value = {}
    config.get_site_id.return_value = 30
    return Database(config, Sql(db_server="sqlite"))


def test_complete_hand_maps_to_fpdb_hand() -> None:
    hand = build_fpdb_hand(_captured("plo"))
    assert hand.handid == "91426500343"
    assert hand.gametype["base"] == "hold"
    assert hand.gametype["category"] == "omahahi"
    assert len(hand.players) == 5


def test_complete_hand_renders_expected_narrative() -> None:
    text = render_fpdb_hand(build_fpdb_hand(_captured("plo")))
    assert "Omaha Pot Limit ($0.01/$0.02)" in text
    assert "Dealt to Hero [Js 8s 7s 4d]" in text
    assert "Villain2: raises $0.05 to $0.07" in text
    assert "*** FLOP *** [Qc 9s 6c]" in text
    assert "*** TURN *** [Qc 9s 6c] [5s]" in text
    assert "Villain4 collected $0.2" in text
    assert "Rake $0.01" in text


def test_incomplete_hand_is_rejected() -> None:
    # A capture that stopped before the showdown has nobody collecting: the
    # hand must be refused rather than imported truncated.
    with pytest.raises(CaptureNotImportableError):
        build_fpdb_hand(_hand_with(collections=[]))


def test_tournament_hand_maps_mtt_metadata_and_imports_into_sqlite() -> None:
    normalized = _captured("tournament")
    hand = build_fpdb_hand(normalized, config=SITE_IDS)
    assert hand.gametype["type"] == "tour"
    assert hand.tourNo == "77"
    assert hand.tourneyName == "Sunday MTT"

    db = _sqlite()
    import_fpdb_hand(hand, db, file_id=1, doinsert=True, printtest=False, starting_hand_id=1)
    db.commit()
    cursor = db.get_cursor()
    cursor.execute("select count(*) from Hands")
    assert cursor.fetchone()[0] == 1
    cursor.execute("select count(*) from Tourneys")
    assert cursor.fetchone()[0] == 1


def test_straddle_hand_conserves_pot_rake_and_player_results() -> None:
    hand = build_fpdb_hand(_captured("straddle"))

    hand.totalPot()

    assert hand.pot.committed == {
        "Straddler": Decimal("0.28"),
        "SmallBlind": Decimal("0.01"),
        "BigBlindWinner": Decimal("0.28"),
    }
    assert hand.totalpot == Decimal("0.57")
    assert hand.totalcollected == Decimal("0.54")
    assert hand.rake == Decimal("0.03")

    hand.assembleHand()
    assert hand.handsplayers["Straddler"]["committed"] == 28
    assert hand.handsplayers["Straddler"]["totalProfit"] == -28
    assert hand.handsplayers["Straddler"]["flg_blind_k"] is True
    assert hand.handsplayers["BigBlindWinner"]["committed"] == 28
    assert hand.handsplayers["BigBlindWinner"]["totalProfit"] == 26
    assert sum(player["totalProfit"] for player in hand.handsplayers.values()) == -3

    text = render_fpdb_hand(hand)
    assert "Straddler: posts straddle $0.04" in text
    assert "Total pot $0.57 Main pot $0.03 Side pot $0.54. | Rake $0.03" in text
    assert PokerStars.re_post_straddle.search(text)


def test_board_streets_suffixes_extra_boards() -> None:
    # The first board keeps the base street names; extra boards get numbered
    # streets that DerivedStats encodes into the Boards table.
    hand_data = {
        "boards": [
            {"FLOP": ["3c", "4s", "Qd"], "TURN": ["Qs"], "RIVER": ["6d"]},
            {"FLOP": ["3c", "4s", "Qd"], "TURN": ["9h"], "RIVER": ["5s"]},
        ],
    }
    streets = _board_streets(hand_data)
    assert streets["FLOP"] == ["3c", "4s", "Qd"]
    assert streets["TURN"] == ["Qs"]
    assert streets["TURN2"] == ["9h"]
    assert streets["RIVER2"] == ["5s"]


def test_single_board_uses_plain_street_names() -> None:
    hand_data = {"boards": [{"FLOP": ["3c", "4s", "Qd"]}], "community": {"FLOP": ["3c", "4s", "Qd"]}}
    assert set(_board_streets(hand_data)) == {"FLOP"}


RUN_TWICE = [
    {"FLOP": ["3c", "4s", "Qd"], "TURN": ["Qs"], "RIVER": ["6d"]},
    {"FLOP": ["3c", "4s", "Qd"], "TURN": ["9h"], "RIVER": ["5s"]},
]


def test_run_it_twice_maps_to_hand_boards_and_run_count() -> None:
    hand = build_fpdb_hand(_hand_with(boards=copy.deepcopy(RUN_TWICE), run_it_times=2))
    assert hand.runItTimes == 2
    assert hand.board["FLOP"] == ["3c", "4s", "Qd"]
    assert hand.board["TURN2"] == ["9h"]
    assert hand.board["RIVER2"] == ["5s"]


def test_bomb_pot_and_splash_map_to_hand_fields() -> None:
    hand = build_fpdb_hand(_hand_with(bomb_pot=30, splash_pot=4))
    assert hand.bombPot == 30
    assert hand.splashPot == 4


def test_cashout_maps_to_hand_cashout_fields() -> None:
    hand = build_fpdb_hand(_hand_with(cashout=[{"player": "Hero", "amount": "0.20", "fee": "0.10"}]))
    assert hand.cashedOut is True
    assert hand.isCashOut is True
    assert hand.cashOutAmounts["Hero"] == Decimal("0.20")
    assert hand.cashOutFees["Hero"] == Decimal("0.10")


def test_derived_stats_encode_multiple_boards_and_pot_flags() -> None:
    # End-to-end through DerivedStats: a run-it-twice hand with a bomb/splash pot
    # must yield one encoded board per run plus the scalar pot flags that the
    # Hand Viewer filters query.
    hand = build_fpdb_hand(_hand_with(boards=copy.deepcopy(RUN_TWICE), run_it_times=2, bomb_pot=30, splash_pot=4))
    hand.totalPot()
    hand.assembleHand()
    assert hand.hands["runItTwice"] is True
    assert len(hand.hands["boards"]) == 2
    assert {b[0] for b in hand.hands["boards"]} == {1, 2}
    assert hand.hands["bombPot"] == 30
    assert hand.hands["splashPot"] == 4


def test_replayer_header_marks_bomb_and_splash_pots() -> None:
    from fpdb_3_legacy.GuiReplayer import GuiReplayer

    def _hand(**kw: Any) -> SimpleNamespace:
        data = {"gametype": {"currency": "USD"}, "bombPot": 0, "splashPot": 0}
        data.update(kw)
        return SimpleNamespace(**data)

    assert GuiReplayer._special_pot_suffix(_hand()) == ""
    assert "Bomb pot" in GuiReplayer._special_pot_suffix(_hand(bombPot=30))
    assert "Splash pot: 0.04USD" in GuiReplayer._special_pot_suffix(_hand(splashPot=4))
    both = GuiReplayer._special_pot_suffix(_hand(bombPot=30, splashPot=125))
    assert "Bomb pot" in both and "Splash pot: 1.25USD" in both


def test_an_all_in_or_fold_hand_imports_as_that_game() -> None:
    hand = build_fpdb_hand(_captured("aof_omaha"), config=SITE_IDS)
    assert hand.gametype["category"] == "aof_omaha"

    db = _sqlite()
    import_fpdb_hand(hand, db, file_id=1, doinsert=True, printtest=False, starting_hand_id=1)
    db.commit()
    cursor = db.get_cursor()
    cursor.execute("select category from Gametypes")
    assert cursor.fetchone()[0] == "aof_omaha"
