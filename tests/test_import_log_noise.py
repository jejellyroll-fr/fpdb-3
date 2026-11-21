"""Import log noise: each WARNING an import prints must point at a real problem (#869).

A bulk import used to print about 400 WARNING lines, most of them for normal
data or repeated several times, so the few real errors were hard to find. Some of
those warnings hid real parser bugs (Bovada stud streets, Bovada all-in blinds,
Full Tilt short antes), fixed here as well.
"""

from __future__ import annotations

import ast
import logging
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import gui_empty_state
from fpdb_3_legacy.BovadaToFpdb import Bovada
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.FulltiltToFpdb import Fulltilt
from fpdb_3_legacy.WinningToFpdb import Winning

ROOT = Path(__file__).resolve().parents[1]
BOVADA = ROOT / "regression-test-files" / "cash" / "Bovada"
STUD_FILE = BOVADA / "Stud" / "7-Stud-USD-2.00-4.00-201205.txt"
ZONE_FILE = BOVADA / "Flop" / "NLHE-6max-USD - $0.10-$0.25 - 202104.ZonePoker.txt"
ALL_IN_BB_FILE = BOVADA / "Flop" / "LHE-2max-USD - $30-$60 - 201301.HU.all.in.big.txt"
FTP_WALK_FILE = ROOT / "regression-test-files" / "tour" / "FTP" / "Flop" / "NLHE-6max-Matrix-USD-26-201211.match4.txt"
FTP_SHORT_ANTE_FILE = (
    ROOT / "regression-test-files" / "tour" / "FTP" / "Stud" / "Razz-USD-HUSNG-200-201211.all.in.ante.txt"
)


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]


def _parse(parser_class, config: Config, path: Path):
    return parser_class(config=config, in_path=str(path), autostart=True)


def _hand(parser, hand_id: int):
    return next(hand for hand in parser.getProcessedHands() if int(hand.handid) == hand_id)


# 1. Winning/ACR: readSTP ran for every hand and warned every time.


def test_winning_read_stp_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    converter = Winning.__new__(Winning)

    with caplog.at_level(logging.DEBUG):
        converter.readSTP(SimpleNamespace(handid=2780587577))

    assert not _warnings(caplog)


# 2. Bovada Zone Poker: every hand ends with an empty summary.


def test_bovada_zone_poker_empty_summary_is_not_a_warning(config: Config, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        parser = _parse(Bovada, config, ZONE_FILE)

    assert parser.getProcessedHands()
    assert not [message for message in _warnings(caplog) if "Summary section" in message]


# 3. Bovada stud: the street splitter opened a street at every dealt card.


@pytest.fixture(scope="module")
def bovada_stud(config: Config):
    return _parse(Bovada, config, STUD_FILE)


def test_bovada_stud_actions_land_on_their_street(bovada_stud) -> None:
    hand = _hand(bovada_stud, 2604291510)

    assert [act[:2] for act in hand.actions["THIRD"]] == [
        ("Seat 5", "bringin"),
        ("Seat 1", "calls"),
        ("Hero", "calls"),
    ]
    assert [act[:2] for act in hand.actions["FOURTH"]] == [
        ("Seat 1", "checks"),
        ("Hero", "checks"),
        ("Seat 5", "checks"),
    ]
    assert [act[:2] for act in hand.actions["FIFTH"]] == [
        ("Hero", "bets"),
        ("Seat 5", "folds"),
        ("Seat 1", "folds"),
    ]
    assert not hand.actions["SIXTH"]
    assert not hand.actions["SEVENTH"]


def test_bovada_stud_cards_land_on_their_street(bovada_stud) -> None:
    hand = _hand(bovada_stud, 2604291510)

    assert hand.holecards["THIRD"]["Hero"] == [["Th"], ["Jh", "Qh"]]
    assert hand.holecards["FOURTH"]["Seat 1"] == [["9c"], []]
    assert hand.holecards["FIFTH"]["Seat 1"] == [["4d"], []]


def test_a_villain_with_known_down_cards_folding_on_fifth_is_not_padded(
    bovada_stud,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Bodog prints every player's cards: Seat 1 folds on 5th street holding five known cards.
    hand = _hand(bovada_stud, 2604291510)

    with caplog.at_level(logging.WARNING):
        cards = hand.join_holecards("Seat 1", asList=True)

    assert cards == ["7h", "8c", "Jc", "9c", "4d"]
    assert not _warnings(caplog)


def test_a_villain_with_known_down_cards_folding_on_fourth_keeps_their_slots(bovada_stud) -> None:
    # Was ["0x", "0x", "5d", "3h", "Qd", "2c"]: the down cards shifted into the up-card slots.
    hand = _hand(bovada_stud, 2604291787)

    assert hand.join_holecards("Seat 1", asList=True) == ["5d", "3h", "Qd", "2c"]


def test_a_sitting_out_hero_is_not_reported_as_undealt(bovada_stud) -> None:
    hand = _hand(bovada_stud, 2604291787)

    assert "Hero" not in [player[1] for player in hand.players]


def test_an_unexplained_card_count_warns_once_per_player(bovada_stud, caplog: pytest.LogCaptureFixture) -> None:
    hand = _hand(bovada_stud, 2604291577)
    # Seat 5 reaches 6th street. With only the up card known on third street and
    # a seventh-street card on top, five cards and no down card cannot be laid out.
    third_street = hand.holecards["THIRD"]["Seat 5"]
    hand.holecards["THIRD"]["Seat 5"] = [["9d"], []]
    hand.holecards["SEVENTH"]["Seat 5"] = [[], ["2h"]]
    hand.__dict__.pop("_holecard_warnings", None)
    try:
        with caplog.at_level(logging.WARNING):
            for _ in range(4):  # derived stats, starting hands, stove, auto-notes
                hand.join_holecards("Seat 5", asList=True)
    finally:
        hand.holecards["THIRD"]["Seat 5"] = third_street
        del hand.holecards["SEVENTH"]["Seat 5"]
        hand.__dict__.pop("_holecard_warnings", None)

    messages = _warnings(caplog)
    assert len(messages) == 1
    assert "2604291577" in messages[0]
    assert "Seat 5" in messages[0]


def test_bovada_stud_imports_without_warnings(config: Config, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        parser = _parse(Bovada, config, STUD_FILE)
        for hand in parser.getProcessedHands():
            DerivedStats().getStats(hand)

    assert not _warnings(caplog)


# 4. Hands that really hold no betting action.


def test_bovada_all_in_big_blind_is_recorded(config: Config) -> None:
    parser = _parse(Bovada, config, ALL_IN_BB_FILE)
    hand = _hand(parser, 2667379227)

    # "Big Blind : All-in $15" was dropped: a blind posted all-in in a hand without antes.
    assert hand.actions["BLINDSANTES"][1] == ("Seat 6", "big blind", Decimal("15"), True)
    assert not parser.parsing_issues


def test_full_tilt_walk_is_not_missing_betting_actions(config: Config) -> None:
    parser = _parse(Fulltilt, config, FTP_WALK_FILE)

    assert _hand(parser, 31493031208)
    assert not [issue for issue in parser.parsing_issues if "31493031208" in issue]


# 5. Smaller items.


def test_full_tilt_short_all_in_ante_returns_the_uncovered_part(
    config: Config,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Hero antes 7, Player0 antes 6 all in: 1 comes back to Hero, the pot is 12.
    with caplog.at_level(logging.WARNING):
        parser = _parse(Fulltilt, config, FTP_SHORT_ANTE_FILE)
        hand = _hand(parser, 31349767778)
    stats = DerivedStats()
    stats.getStats(hand)
    players = stats.getHandsPlayers()

    assert hand.totalpot == 12
    assert players["Hero"]["totalProfit"] == -600
    assert players["Player0"]["totalProfit"] == 600
    assert not [message for message in _warnings(caplog) if "Auto-balancing" in message]


def test_an_empty_filter_result_is_logged_at_info(caplog: pytest.LogCaptureFixture, monkeypatch) -> None:
    monkeypatch.setattr(gui_empty_state.QApplication, "instance", staticmethod(lambda: None))

    with caplog.at_level(logging.DEBUG):
        gui_empty_state.show_no_data(None, context="Tournament stats")

    records = [record for record in caplog.records if "no data" in record.getMessage()]
    assert records
    assert all(record.levelno == logging.INFO for record in records)


def test_no_library_module_configures_the_root_logger_on_import() -> None:
    """Spawned import workers re-import fpdb; a module-level basicConfig gave them a bare INFO handler."""
    offenders = []
    for path in sorted((ROOT / "fpdb_3_legacy").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            call = node.value if isinstance(node, ast.Expr) else None
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "basicConfig":
                offenders.append(path.name)
    assert not offenders
