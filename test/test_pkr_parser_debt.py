"""Blind reconstruction contracts for the PKR converter."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.PkrToFpdb import Pkr

ROOT = Path(__file__).resolve().parents[1]
CASH = ROOT / "regression-test-files" / "cash" / "PKR" / "Flop"
TOUR = ROOT / "regression-test-files" / "tour" / "PKR" / "Flop"


@pytest.fixture(scope="module")
def parser_config() -> Config:
    return Config()


def _hands(config: Config, path: Path) -> list:
    return Pkr(config=config, in_path=str(path), autostart=True).getProcessedHands()


def _blinds(hand) -> list[tuple]:
    return [(name, kind, amount) for name, kind, amount, _allin in hand.actions["BLINDSANTES"]]


def _hand_with_blind(hands: list, kind: str):
    for hand in hands:
        if any(entry[1] == kind for entry in _blinds(hand)):
            return hand
    msg = f"no hand posts a {kind!r} blind"
    raise AssertionError(msg)


@pytest.mark.parametrize(
    ("filename", "currency"),
    [
        # "Money Type: PLAY MONEY", yet the blinds are written "$5 / $10": the
        # symbol alone cannot tell a play money table from a real one.
        (CASH / "NLHE-10max-play-5-10-201108.txt", "play"),
        (CASH / "NLHE-10max-USD-0.02-0.04-201206.txt", "USD"),
        (CASH / "NLHE-6max-EUR-0.25-0.50-201303.txt", "EUR"),
        (TOUR / "NLHE-USD-MTT-201205.txt", "T$"),
    ],
)
def test_money_type_decides_the_currency(filename: Path, currency: str) -> None:
    hand_history = filename.read_text(encoding="utf-8", errors="replace")

    game_type = Pkr.determineGameType(Pkr.__new__(Pkr), hand_history)

    assert game_type["currency"] == currency


def test_hand_histories_state_no_buyin_or_level() -> None:
    # The header stops at the tournament number, so readHandInfo has no buy-in
    # or level to read. Both regexes together define the fields it can see.
    available = set(Pkr.re_GameInfo.groupindex) | set(Pkr.re_HandInfo.groupindex)

    assert "TOURNO" in available
    assert not {"BUYIN", "FEE", "LEVEL"} & available


def test_tournament_buyin_is_recorded_as_unknown(parser_config: Config) -> None:
    hands = _hands(parser_config, TOUR / "NLHE-USD-MTT-201205.txt")

    assert hands
    for hand in hands:
        assert hand.tourNo == "25826986"
        # Unknown, not free: the history simply does not carry the buy-in.
        assert hand.buyinCurrency == "NA"
        assert hand.buyin == 0
        assert hand.fee == 0


def test_calling_a_raise_only_adds_the_difference(parser_config: Config) -> None:
    # Hand 2083044128: "Player1 calls 3,000", then "Player8 raises to 4,600",
    # then "Player1 calls 4,600" -- which puts only 1,600 more in the pot.
    hands = _hands(parser_config, TOUR / "NLHE-USD-MTT-201205.txt")
    hand = next(h for h in hands if h.handid == "2083044128")

    # Raise entries carry extra fields, so index rather than unpack.
    calls = [(entry[0], entry[2]) for entry in hand.actions["PREFLOP"] if entry[1] == "calls"]

    assert ("Player1", Decimal("3000")) in calls
    assert calls.count(("Player1", Decimal("4600"))) == 0
    assert calls[-1] == ("Player1", Decimal("1600"))


def test_lone_post_is_the_big_blind_of_an_entering_player(parser_config: Config) -> None:
    # "Player3 posts $0.04" carries no dead post: it is the big blind, written
    # in the short form instead of "posts big blind ($0.04)".
    hands = _hands(parser_config, CASH / "NLHE-10max-USD-0.02-0.04-201208.multiple.side.pots.txt")

    posted = [entry for hand in hands for entry in _blinds(hand)]
    big_blinds = [entry for entry in posted if entry[1] == "big blind"]

    assert big_blinds
    assert all(amount == Decimal("0.04") for _, _, amount in big_blinds)


def test_second_small_blind_takes_the_dead_amount_from_the_hand(parser_config: Config) -> None:
    # "Player5 posts $0" then "Player5 posts $0.02 dead".
    hands = _hands(parser_config, CASH / "NLHE-10max-USD-0.02-0.04-201208.secondsb.txt")
    hand = _hand_with_blind(hands, "secondsb")

    entry = next(item for item in _blinds(hand) if item[1] == "secondsb")

    assert entry[2] == Decimal("0.02")


def test_posting_both_blinds_sums_the_live_and_dead_amounts(parser_config: Config) -> None:
    # "Player2 posts $2" then "Player2 posts $1 dead" on a $1/$2 table.
    hands = _hands(parser_config, CASH / "NLHE-USD-1.00-2.00-201108.post.both.txt")
    hand = _hand_with_blind(hands, "both")

    entry = next(item for item in _blinds(hand) if item[1] == "both")

    assert entry[2] == Decimal("3")


@pytest.mark.parametrize(
    ("posted", "dead", "kind", "expected"),
    [
        # A 5/15 structure: the dead amount is not half the big blind.
        ("15", "5", "both", Decimal("20")),
        ("0", "5", "secondsb", Decimal("5")),
    ],
)
def test_dead_amount_is_read_rather_than_derived_from_the_big_blind(
    parser_config: Config,
    tmp_path: Path,
    posted: str,
    dead: str,
    kind: str,
    expected: Decimal,
) -> None:
    # Derived from a real hand: the corpus only contains 2:1 structures, where
    # halving the big blind happens to agree with the stated dead amount.
    source = (CASH / "NLHE-USD-1.00-2.00-201108.post.both.txt").read_text(encoding="utf-8")
    skewed = (
        source.replace("Blinds are now $1 / $2", "Blinds are now $5 / $15")
        .replace("Player0 posts small blind ($1)", "Player0 posts small blind ($5)")
        .replace("Player1 posts big blind ($2)", "Player1 posts big blind ($15)")
        .replace("Player2 posts $2\n", f"Player2 posts ${posted}\n")
        .replace("Player2 posts $1 dead", f"Player2 posts ${dead} dead")
    )
    hand_file = tmp_path / "skewed.txt"
    hand_file.write_text(skewed, encoding="utf-8")

    hand = _hand_with_blind(_hands(parser_config, hand_file), kind)
    entry = next(item for item in _blinds(hand) if item[1] == kind)

    assert entry[2] == expected
