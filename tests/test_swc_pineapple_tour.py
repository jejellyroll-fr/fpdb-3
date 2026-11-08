"""Non-regression: SwC "Pineapple Hold'em" tournament hands must parse.

The client labels the game "Pineapple Hold'em" in the hand header, but the
hand text is plain Hold'em (two hole cards, board, ordinary streets, plus
harmless "Discard Cards 0" lines). re_GameInfo's GAME alternation did not
include the "Pineapple " prefix, so determineGameType raised FpdbParseError
on every hand of a Pineapple tournament file and the improved error handler
ended up skipping the whole file as "permanent" -- the MTT never reached
the database at all.
"""

from __future__ import annotations

from pathlib import Path

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs

REPO = Path(__file__).resolve().parent.parent
PINEAPPLE_TOUR_HH = (
    REPO / "regression-test-files/cash/SealsWithClubs/Flop/Pineapple-8max-tour-20261108.txt"
)


def _parse(path: Path):
    hhc = SealsWithClubs(config=Config(), in_path=str(path), autostart=True)
    assert hhc.numErrors == 0, hhc.parsing_issues
    assert hhc.numPartial == 0, hhc.parsing_issues
    hands = hhc.getProcessedHands()
    assert len(hands) == 1
    return hands[0]


def test_pineapple_tournament_hand_parses_as_holdem_tour() -> None:
    """Real SwC tournament file (anonymized): header, tourNo, game, pot."""
    hand = _parse(PINEAPPLE_TOUR_HH)
    assert hand.handid == "305152125"
    assert hand.tourNo == "305147875"
    assert hand.gametype["type"] == "tour"
    assert hand.gametype["base"] == "hold"
    assert hand.gametype["category"] == "holdem"
    assert hand.gametype["limitType"] == "nl"
    assert hand.buyin == 0 and hand.fee == 0
    assert hand.board["FLOP"] == ["9h", "2d", "7s"]
    assert hand.board["TURN"] == ["8h"]
    assert hand.board["RIVER"] == ["Kd"]
    assert str(hand.totalpot) == "576"
    assert hand.collectees["Player3"] == 576
    assert len(hand.players) == 8


def test_plain_holdem_and_omaha_headers_still_parse(tmp_path: Path) -> None:
    """The widened GAME group must not change the existing games."""
    cash = PINEAPPLE_TOUR_HH.read_text(encoding="utf-8")
    cash_holdem = cash.replace(
        "Tournament (Hourly Freeroll - Pineapple NLH [10 Chips])#305147875, 0+0 Pineapple Hold'em No Limit",
        "",
    ).replace("SwCPoker Hand #305152125:  - Level I", "SwCPoker Hand #305152125: ")
    # A cash header is "SwCPoker Hand #id:  <Game> <Limit> (sb/bb) - date";
    # build it from the tournament header by dropping the Tournament block.
    cash_holdem = cash.replace(
        "SwCPoker Hand #305152125: Tournament (Hourly Freeroll - Pineapple NLH [10 Chips])#305147875, 0+0 Pineapple Hold'em No Limit - Level I (10/20)",
        "SwCPoker Hand #305152125:  Hold'em No Limit (10/20)",
    )
    path = tmp_path / "cash.txt"
    path.write_text(cash_holdem, encoding="utf-8")
    hand = _parse(path)
    assert hand.gametype["type"] == "ring"
    assert hand.gametype["category"] == "holdem"
    assert hand.tourNo is None
