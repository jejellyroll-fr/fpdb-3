"""Unibet blinds posted by a player who joins or comes back (issue #866).

Unibet writes two blind lines the parser did not read:

    carol posts missed small blind €0.03
    carol posts new player's blind €0.05

Neither reached the pot. The importer then found more collected than the pot
held, "adjusted" the pot to hide it, and the poster's profit came out too high
by the blind.

The new player's blind is a live big blind: the poster checks preflop when no
one raises. The missed small blind is dead money, like every other parser's
"secondsb".

The fixture holds both hands from the report, anonymised.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.UnibetToFpdb import Unibet

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "regression-test-files/cash/Unibet/Flop/PLO-6max-EUR-0.03-0.05-202611.new.player.and.missed.blinds.txt"

BOTH_BLINDS = 1759126250  # missed small blind + new player's blind
NEW_PLAYER = 1756766696  # new player's blind only


def _parse() -> Unibet:
    hhc = Unibet(config=Config(), in_path=str(FIXTURE), autostart=False)
    hhc.start()
    return hhc


@pytest.fixture(scope="module")
def hands():
    hhc = _parse()
    assert hhc.numErrors == 0, hhc.parsing_issues
    assert hhc.numPartial == 0, hhc.parsing_issues
    return {int(hand.handid): hand for hand in hhc.getProcessedHands()}


def _profits(hand) -> dict[str, int]:
    stats = DerivedStats()
    stats.getStats(hand)
    return {name: hp["totalProfit"] for name, hp in stats.handsplayers.items()}


@pytest.mark.parametrize(
    ("hand_id", "room_total_pot", "room_rake"),
    [(BOTH_BLINDS, "0.99", "0.06"), (NEW_PLAYER, "0.43", "0.03")],
)
def test_the_pot_is_the_rooms_total_pot(hands, hand_id: int, room_total_pot: str, room_rake: str) -> None:
    hand = hands[hand_id]
    assert hand.totalpot == Decimal(room_total_pot)
    assert hand.rake == Decimal(room_rake)
    assert hand.totalpot == hand.totalcollected + hand.rake


def test_new_players_blind_is_a_live_big_blind(hands) -> None:
    hand = hands[NEW_PLAYER]
    assert ("erin", "big blind", Decimal("0.05"), False) in hand.actions["BLINDSANTES"]
    # It counts toward what erin owes preflop: the check costs nothing more.
    assert ("erin", "checks") in [a[:2] for a in hand.actions["PREFLOP"]]
    assert hand.pot.committed["erin"] == Decimal("0.19")


def test_missed_small_blind_is_dead_money(hands) -> None:
    hand = hands[BOTH_BLINDS]
    blinds = hand.actions["BLINDSANTES"]
    assert ("carol", "secondsb", Decimal("0.03"), False) in blinds
    assert ("carol", "big blind", Decimal("0.05"), False) in blinds
    assert hand.pot.common["carol"] == Decimal("0.03")
    # The live 0.05 is part of the 0.18 carol matched preflop, not on top of it.
    assert hand.pot.committed["carol"] == Decimal("0.18") + Decimal("0.16") + Decimal("0.05")


def test_the_posters_profit_includes_the_blind(hands) -> None:
    # The room's "net result" for each player, in cents.
    assert _profits(hands[BOTH_BLINDS]) == {"Hero": 0, "alice": -39, "bob": -18, "carol": 51}
    assert _profits(hands[NEW_PLAYER]) == {"dave": 0, "erin": -19, "Hero": 0, "frank": 21, "grace": -5}


def test_import_logs_no_pot_mismatch(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        hhc = _parse()
    assert hhc.numErrors == 0
    assert "exceeds total pot" not in caplog.text


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("bob posts new player's blind €0.05", ("bob", "0.05")),
        (
            "kokosat[Unibet_0123456789abcdef] posts new player's blind €0.10",
            ("kokosat[Unibet_0123456789abcdef]", "0.10"),
        ),
        # A typographic apostrophe, in case an export or a copy curls it.
        ("bob posts new player’s blind €0.05", ("bob", "0.05")),
    ],
)
def test_new_players_blind_line(line: str, expected: tuple[str, str]) -> None:
    match = Unibet.re_PostNewPlayer.search(line)
    assert match is not None
    assert (match.group("PNAME"), match.group("BB")) == expected


def test_missed_small_blind_line() -> None:
    match = Unibet.re_PostMissedSB.search("bob posts missed small blind €0.03")
    assert match is not None
    assert (match.group("PNAME"), match.group("SB")) == ("bob", "0.03")


@pytest.mark.parametrize(
    "line",
    ["bob posts small blind €0.03", "bob posts big blind €0.05", "bob posts small & big blinds €0.08"],
)
def test_ordinary_blinds_are_not_read_twice(line: str) -> None:
    assert Unibet.re_PostNewPlayer.search(line) is None
    assert Unibet.re_PostMissedSB.search(line) is None


def test_missed_small_blind_is_not_read_as_a_small_blind() -> None:
    assert Unibet.re_PostSB.search("bob posts missed small blind €0.03") is None
