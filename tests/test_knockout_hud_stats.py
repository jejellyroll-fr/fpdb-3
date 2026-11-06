"""Knockout HUD statistics: a player's bounty, and who covers whom (#447)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from fpdb_3_legacy import Hand
from fpdb_3_legacy.localized_formats import get_format_locale, set_format_locale
from fpdb_3_legacy.Stats import do_stat
from tests.helpers.icm_hands import parse

STAT_DICT = {1: {"screen_name": "Hero"}, 2: {"screen_name": "Villain"}, 3: {"screen_name": "Short"}}


@pytest.fixture(autouse=True)
def english_numbers():
    previous = get_format_locale()
    set_format_locale("en_US")
    yield
    set_format_locale(previous)


def table(stacks: dict[str, str], bounties: dict[str, str | None], *, hero="Hero", raised=None, currency=None) -> Any:
    return SimpleNamespace(
        players=[[seat, name, stack, None, bounties.get(name)] for seat, (name, stack) in enumerate(stacks.items(), 1)],
        bets={"BLINDSANTES": {}},
        pot=SimpleNamespace(returned={}, stp=0),
        collectees={},
        gametype={"bb": "200", "sb": "100", "currency": "T$", "type": "tour"},
        hero=hero,
        endBounty=raised or {},
        buyinCurrency=currency,
    )


def stat(name: str, hand: Any, player: int) -> tuple:
    return do_stat(STAT_DICT, stat=name, player=player, hand_instance=hand)


# --- bounty ----------------------------------------------------------------------------


def test_the_bounty_is_the_one_the_seat_printed() -> None:
    hand = table({"Hero": "4000", "Villain": "3000"}, {"Hero": "5", "Villain": "7.50"}, currency="USD")

    assert stat("bounty", hand, 2)[1] == "$7.50"


def test_a_bounty_the_hand_raised_is_shown_at_its_new_value() -> None:
    hand = table({"Hero": "4000", "Villain": "3000"}, {"Villain": "7.50"}, raised={"Villain": Decimal(1000)})

    assert stat("bounty", hand, 2)[1] == "10.00"


def test_a_regular_knockout_prints_no_bounty() -> None:
    hand = table({"Hero": "4000", "Villain": "3000"}, {})

    assert stat("bounty", hand, 2)[1] == "-"


# --- covers ----------------------------------------------------------------------------


def test_the_hero_covers_a_shorter_stack_and_is_covered_by_a_deeper_one() -> None:
    hand = table({"Hero": "4000", "Villain": "3000", "Short": "6000"}, {})

    assert stat("covers", hand, 2)[:2] == (1, "you cover")
    assert stat("covers", hand, 3)[:2] == (-1, "covers you")


def test_equal_stacks_are_even_and_the_hero_s_own_label_says_nothing() -> None:
    hand = table({"Hero": "4000", "Villain": "4000"}, {})

    assert stat("covers", hand, 2)[:2] == (0, "even")
    assert stat("covers", hand, 1)[1] == "-"


def test_without_a_hero_nobody_covers_anybody() -> None:
    hand = table({"Hero": "4000", "Villain": "3000"}, {}, hero="")

    assert stat("covers", hand, 2)[1] == "-"


# --- a stored progressive knockout -----------------------------------------------------

# Villain covers Hero and busts them: the elimination raises Villain's bounty to $10.
ELIMINATION = """PokerStars Hand #200000000401: Tournament #3000000401, $4.40+$5.00+$0.60 USD Hold'em No Limit - Level V (100/200) - 2026/10/26 12:00:00 ET
Table '3000000401 1' 9-max Seat #1 is the button
Seat 1: Hero (2000 in chips, $5 bounty)
Seat 3: Villain (3000 in chips, $7.50 bounty)
Seat 5: Short (1000 in chips, $5 bounty)
Villain: posts small blind 100
Short: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [As Ks]
Hero: raises 1800 to 2000 and is all-in
Villain: calls 1900
Short: folds
*** FLOP *** [2c 7d 9h]
*** TURN *** [2c 7d 9h] [Jc]
*** RIVER *** [2c 7d 9h Jc] [3s]
*** SHOW DOWN ***
Hero: shows [As Ks] (high card Ace)
Villain: shows [Qh Qd] (a pair of Queens)
Villain collected 4200 from pot
Villain wins $2.50 for eliminating Hero and their own bounty increases by $2.50 to $10
*** SUMMARY ***
Total pot 4200 | Rake 0
Board [2c 7d 9h Jc 3s]
Seat 1: Hero (button) showed [As Ks] and lost with high card Ace
Seat 3: Villain (small blind) showed [Qh Qd] and won (4200) with a pair of Queens
Seat 5: Short (big blind) folded before Flop



"""


def test_a_hand_rebuilt_from_the_database_keeps_the_raised_bounty(tmp_path, fresh_db, legacy_config) -> None:
    from fpdb_3_legacy.Importer import Importer

    _hand, path = parse(tmp_path, ELIMINATION)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()

    rebuilt = Hand.hand_factory(hand_id, legacy_config, fresh_db)

    assert rebuilt.endBounty == {"Villain": Decimal(1000)}  # in hundredths, as the parser keeps it
    assert stat("bounty", rebuilt, 2)[1] == "10.00"
    assert stat("bounty", rebuilt, 3)[1] == "5.00"  # Short's bounty did not move
    del importer  # kept alive until here: dropping it closes the database
