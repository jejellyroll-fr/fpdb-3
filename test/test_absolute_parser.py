"""Regression tests for the legacy Absolute/Cereus parser."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.AbsoluteToFpdb import Absolute, FpdbParseError


@pytest.mark.parametrize(
    ("stakes", "expected_currency", "expected_type"),
    [
        ("$0.02", "USD", "ring"),
        ("€0.02", "EUR", "ring"),
        ("0.02", "T$", "tour"),
    ],
)
def test_absolute_header_currency_is_explicit(stakes, expected_currency, expected_type) -> None:
    parser = Absolute.__new__(Absolute)
    hand_text = f"Stage #1571362962: Holdem No Limit {stakes} - 2009-08-05 15:24:06 (ET)"

    game = parser.determineGameType(hand_text)

    assert game["currency"] == expected_currency
    assert game["type"] == expected_type
    assert Decimal(game["sb"]) == Decimal("0.01")
    assert Decimal(game["bb"]) == Decimal("0.02")


def test_absolute_fixed_limit_stake_uses_known_blind_structure() -> None:
    hand_text = "Stage #1571362962: Holdem Normal $2.00 - 2009-08-05 15:24:06 (ET)"

    game = Absolute.__new__(Absolute).determineGameType(hand_text)

    assert game["limitType"] == "fl"
    assert game["sb"] == "0.50"
    assert game["bb"] == "1.00"


@pytest.mark.parametrize("dealer_text", ["Seat #6 is the dealer", "Seat #6 is the dead dealer"])
def test_absolute_button_accepts_live_and_dead_dealer(dealer_text) -> None:
    hand = SimpleNamespace(handText=dealer_text, buttonpos=None)

    Absolute.__new__(Absolute).readButton(hand)

    assert hand.buttonpos == 6


@pytest.mark.parametrize("dealer_text", ["Seat #6 is the d dealer", "Seat #6 is the added dealer"])
def test_absolute_button_rejects_partial_dead_words(dealer_text) -> None:
    hand = SimpleNamespace(handText=dealer_text, buttonpos=None)

    with pytest.raises(FpdbParseError, match="button position"):
        Absolute.__new__(Absolute).readButton(hand)


def test_absolute_incoming_player_post_is_one_big_blind() -> None:
    calls = []
    hand = SimpleNamespace(
        handText="New Player - Posts $0.02\n*** POCKET CARDS ***",
        handid="123",
        players=[(3, "New Player", "1.00")],
        addBlind=lambda *args: calls.append(args),
        setUncalledBets=lambda _value: None,
    )
    parser = Absolute.__new__(Absolute)
    parser.compiledPlayers = set()
    parser.compilePlayerRegexs(hand)

    parser.readBlinds(hand)

    assert calls == [(None, None, None), ("New Player", "big blind", "0.02")]


def test_absolute_heads_up_header_sets_two_max_seats() -> None:
    hand_text = (
        "Stage #1571362962: Tourney ID 99 Holdem (1 on 1) No Limit 10 "
        "- 2009-08-05 15:24:06 (ET)"
    )
    parser = Absolute.__new__(Absolute)
    parser.HORSEHand = False
    hand = SimpleNamespace(handText=hand_text, gametype=parser.determineGameType(hand_text))

    parser.readHandInfo(hand)

    assert hand.maxseats == 2
    assert hand.tourNo == "99"


@pytest.mark.parametrize(
    ("seat_lines", "expected_maxseats"),
    [
        ("Seat 1 - Alice ($1.00 in chips)\nSeat 2 - Bob ($1.00 in chips)", 6),
        ("Seat 1 - Alice ($1.00 in chips)\nSeat 7 - Bob ($1.00 in chips)", 9),
    ],
)
def test_absolute_observed_seats_only_promote_proven_nine_max(seat_lines, expected_maxseats) -> None:
    players = []
    hand = SimpleNamespace(
        handText=seat_lines,
        maxseats=6,
        addPlayer=lambda *args: players.append(args),
    )

    Absolute.__new__(Absolute).readPlayerStacks(hand)

    assert len(players) == 2
    assert hand.maxseats == expected_maxseats
