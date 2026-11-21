"""SwC player names that hold a non-word character (issue #865).

Every SwC regex that named a player used ``\\w+``. A seat such as
``alice-b.c`` was therefore never read, its blinds, antes, actions, shows and
collects were dropped, and the hand imported with a wrong pot. Worse,
``re_Uncalled`` was not anchored, so ``returned to alice-b.c`` matched the
name ``alice`` and the whole hand was rejected on an unknown player.

The fixture holds both shapes from the report, anonymised: a blinds hand that
ends on a bet returned to the hyphenated player, and a bomb pot that player
wins at showdown.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.SealsWithClubsToFpdb import (
    ANY_PLAYER,
    SealsWithClubs,
    compile_player_regexes,
    player_name_pattern,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURE = (
    REPO / "regression-test-files/cash/SealsWithClubs/Flop/PLO-8max-mBTC-0.02-0.04-nonword-player-name-20261108.txt"
)
NAME = "alice-b.c"


@pytest.fixture(scope="module")
def hands():
    hhc = SealsWithClubs(config=Config(), in_path=str(FIXTURE), autostart=False)
    hhc.start()
    assert hhc.numErrors == 0, hhc.parsing_issues
    assert hhc.numPartial == 0, hhc.parsing_issues
    return {int(hand.handid): hand for hand in hhc.getProcessedHands()}


def test_every_hand_of_the_fixture_imports(hands) -> None:
    assert sorted(hands) == [305151389, 305151477]
    for hand in hands.values():
        assert NAME in [player[1] for player in hand.players]


@pytest.mark.parametrize("hand_id", [305151389, 305151477])
def test_money_in_equals_money_out(hands, hand_id: int) -> None:
    hand = hands[hand_id]
    paid_in = sum(hand.pot.committed.values(), Decimal(0)) + sum(hand.pot.common.values(), Decimal(0))
    assert paid_in == hand.totalpot
    assert hand.totalpot == hand.totalcollected + hand.rake


def test_uncalled_bet_goes_back_to_the_hyphenated_player(hands) -> None:
    hand = hands[305151477]
    assert ("alice-b.c", "big blind", Decimal("0.04"), False) in hand.actions["BLINDSANTES"]
    assert [a[:2] for a in hand.actions["PREFLOP"]] == [
        ("bob", "calls"),
        ("Hero", "folds"),
        (NAME, "raises"),
        ("bob", "calls"),
    ]
    assert [a[:2] for a in hand.actions["FLOP"]] == [(NAME, "bets"), ("bob", "folds")]
    # The 0.30 flop bet came back: only the 0.14 preflop stays committed.
    assert hand.pot.committed[NAME] == Decimal("0.14")
    assert hand.collectees == {NAME: Decimal("0.30")}


def test_bomb_pot_ante_show_and_collect_are_kept(hands) -> None:
    hand = hands[305151389]
    assert (NAME, "ante", Decimal("0.12"), False) in hand.actions["BLINDSANTES"]
    assert hand.bombPot == 36
    assert (NAME, "bets") in [a[:2] for a in hand.actions["FLOP"]]
    assert hand.holecards["PREFLOP"][NAME][1] == ["Qh", "9c", "5d", "4s"]
    assert hand.collectees == {NAME: Decimal("0.84")}


def test_import_logs_no_pot_mismatch(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        hhc = SealsWithClubs(config=Config(), in_path=str(FIXTURE), autostart=False)
        hhc.start()
    assert hhc.numErrors == 0
    assert "exceeds calculated pot" not in caplog.text
    assert "unknown player" not in caplog.text


# One line per regex family, with the name the regex must capture whole.
LINES = {
    "re_PostSB": "{name}: posts small blind 0.02",
    "re_PostBB": "{name}: posts big blind 0.04",
    "re_PostBoth": "{name}: posts small & big blind 0.06",
    "re_Antes": "{name}: posts the ante 0.12",
    "re_HeroCards": "Dealt to {name} [9s 6d 7s 8s]",
    "re_Action": "{name}: raises 0.10 to 0.14",
    "re_ShowdownAction": "{name}: shows [Qh 9c 5d 4s] (a straight, Queen high)",
    "re_Mucked": "{name}: mucks hand",
    "re_Uncalled": "Uncalled bet (0.30) returned to {name}",
    "re_CollectPot": "Seat 2: {name} (big blind) collected (0.30)",
    "re_ShownCards": "Seat 2: {name} (button) showed [Qh 9c 5d 4s] and won (0.84) with a straight, Queen high",
}
NAMES = ["alice-b.c", "bob x", "c.d+e", "plain"]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("attr", sorted(LINES))
def test_class_default_regexes_capture_the_whole_name(attr: str, name: str) -> None:
    match = getattr(SealsWithClubs, attr).search(LINES[attr].format(name=name))
    assert match is not None
    assert match.group("PNAME") == name


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("attr", sorted(LINES))
def test_seat_name_regexes_capture_the_whole_name(attr: str, name: str) -> None:
    # "alice" is a prefix of "alice-b.c": the seat-built alternation must not
    # stop at it.
    regexes = compile_player_regexes(player_name_pattern([*NAMES, "alice", "bob"]))
    match = regexes[attr].search(LINES[attr].format(name=name))
    assert match is not None
    assert match.group("PNAME") == name


@pytest.mark.parametrize("name", NAMES)
def test_seat_line_reads_the_whole_name(name: str) -> None:
    match = SealsWithClubs.re_PlayerInfo.search(f"Seat 2: {name} (3.58 in chips)")
    assert match is not None
    assert match.group("PNAME") == name
    assert match.group("CASH") == "3.58"


def test_uncalled_bet_is_anchored_at_the_end_of_the_line() -> None:
    regex = compile_player_regexes(ANY_PLAYER)["re_Uncalled"]
    match = regex.search("Uncalled bet (0.30) returned to A-b-c-d\r\nnext line")
    assert match is not None
    assert match.group("PNAME") == "A-b-c-d"


def test_player_name_pattern_escapes_and_orders_longest_first() -> None:
    pattern = player_name_pattern(["a.b", "a.b-c"])
    assert pattern == r"(?P<PNAME>a\.b\-c|a\.b)"
