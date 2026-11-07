"""ACR/WPN cash hands keep the currency their header states.

The current hand-history format writes real-money blinds in dollars
("Hand #... - Holdem(No Limit) - $0.01/$0.02 - ..."). The header regex matched
that "$" without capturing it, so the converter saw no currency and filed every
cash hand of this format as play money. Only the older format, whose play-money
tables are named "PM ...", told the two apart.

Cap tables also limit what a player may put in one hand. Whoever reaches the
limit ("caps") and whoever then calls up to it can no longer bet, as if
all-in, though chips remain behind; those actions are flagged all-in so the
all-in EV covers capped pots.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.WinningToFpdb import Winning

ROOT = Path(__file__).resolve().parents[1]
PLO8_CAP = ROOT / "tests" / "fixtures" / "hands" / "winning" / "plo8_cap_2026.txt"
MODERN_CASH = ROOT / "tests" / "fixtures" / "hands" / "winning" / "modern_cash.txt"
OLD_PLAY_MONEY = (
    ROOT / "regression-test-files" / "cash" / "Winning" / "Flop" / "NLHE-9max-play-5.00-10.00-201608.HH00000000 G0.txt"
)


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _hands(config: Config, path: Path) -> list:
    return Winning(config=config, in_path=str(path), autostart=True).getProcessedHands()


def _hand(config: Config, path: Path):
    hands = _hands(config, path)
    assert len(hands) == 1
    return hands[0]


@pytest.mark.parametrize("path", [PLO8_CAP, MODERN_CASH], ids=["plo8_cap_2026", "modern_cash"])
def test_dollar_blinds_are_real_money(config: Config, path: Path) -> None:
    hands = _hands(config, path)

    assert hands
    assert {(hand.gametype["type"], hand.gametype["currency"]) for hand in hands} == {("ring", "USD")}


def test_blinds_without_a_currency_sign_are_play_money(config: Config, tmp_path: Path) -> None:
    play = tmp_path / "plo8_cap_play.txt"
    play.write_text(PLO8_CAP.read_text(encoding="utf-8").replace("$", ""), encoding="utf-8")

    hand = _hand(config, play)

    assert hand.gametype["currency"] == "play"


def test_old_format_play_money_tables_stay_play_money(config: Config) -> None:
    hands = _hands(config, OLD_PLAY_MONEY)

    assert hands
    assert {hand.gametype["currency"] for hand in hands} == {"play"}


def test_cap_table_settles_rake_and_jackpot_fee(config: Config) -> None:
    hand = _hand(config, PLO8_CAP)

    assert hand.gametype["category"] == "omahahilo"
    assert hand.gametype["limitType"] == "pl"
    assert hand.gametype["buyinType"] == "cap"
    assert hand.totalpot == Decimal("63.50")
    # "Rake $1.51 | JP Fee $0.04": both leave the pot, as the street lines'
    # "Rake $1.55" says.
    assert hand.rake == Decimal("1.55")
    assert hand.collectees == {"dave": Decimal("30.98"), "Hero": Decimal("30.97")}


@pytest.mark.parametrize(
    ("table", "buyin_type"),
    [("Vesta (Cap)", "cap"), ("Vesta (Short)", "shallow"), ("Vesta", "regular")],
)
def test_current_format_table_name_sets_the_buyin_type(
    config: Config, tmp_path: Path, table: str, buyin_type: str
) -> None:
    # The old format names these tables "(CAP)"; the current one "(Cap)",
    # which was never read, so cap and short tables were filed as regular.
    hand_file = tmp_path / "table.txt"
    hand_file.write_text(PLO8_CAP.read_text(encoding="utf-8").replace("Vesta (Cap)", table), encoding="utf-8")

    hand = _hand(config, hand_file)

    assert hand.gametype["buyinType"] == buyin_type


def test_capping_is_a_raise_to_the_cap(config: Config) -> None:
    hand = _hand(config, PLO8_CAP)

    capped = [action for action in hand.actions["PREFLOP"] if action[0] == "dave"][-1]

    assert capped[1] == "raises"
    assert capped[3] == Decimal("30.00")


def test_capping_and_calling_to_the_cap_are_all_in(config: Config) -> None:
    hand = _hand(config, PLO8_CAP)

    flags = [(action[0], action[1], action[-1]) for action in hand.actions["PREFLOP"] if action[1] != "folds"]

    # Only the two actions that reach the $30 cap; the raises and the call
    # below it leave their players free to act again.
    assert flags == [
        ("Hero", "raises", False),
        ("carol", "calls", False),
        ("dave", "raises", False),
        ("Hero", "raises", False),
        ("dave", "raises", True),
        ("Hero", "calls", True),
    ]


def test_a_capped_pot_gets_its_all_in_ev(config: Config) -> None:
    hand = _hand(config, PLO8_CAP)
    # The equity pass runs at import, once players have database ids.
    hand.playerIds = {player[1]: seat for seat, player in enumerate(hand.players, start=1)}

    stats = DerivedStats()
    stats.getStats(hand)

    for player in ("Hero", "dave"):
        row = stats.handsplayers[player]
        assert row["street0AllIn"] is True
        # Hero's A-2-5 low with suited A-K against dave's kings: the all-in
        # EV follows the equity, not the split that happened to run out.
        assert row["allInEV"] != row["totalProfit"]
    assert stats.handsplayers["Hero"]["allInEV"] > 0 > stats.handsplayers["dave"]["allInEV"]
