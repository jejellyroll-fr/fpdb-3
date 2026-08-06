"""Uncalled bets, checked against real hand histories from every supported room.

When the last bet of a street goes uncalled the room hands it back, and the
returned chips must leave the pot with it. Get that wrong in either direction
and the money does not add up: too little returned and the winner is credited
with chips nobody ever paid, too much and the rake looks larger than it was.

So each room is read from its own fixture and the accounting identity is
checked on every hand it yields:

    total pot == what the collectors were credited + rake

with the returned bets already taken out of the total. That identity is what
"no money leaks or phantom rake" actually means, and it is what a regression in
uncalled-bet handling breaks first.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.BovadaToFpdb import Bovada
from fpdb_3_legacy.CakeToFpdb import Cake
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.GGPokerToFpdb import GGPoker
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker
from fpdb_3_legacy.PartyPokerToFpdb import PartyPoker
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.UnibetToFpdb import Unibet
from fpdb_3_legacy.WinamaxToFpdb import Winamax
from fpdb_3_legacy.WinningToFpdb import Winning

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hands"

# One fixture per room, so a room whose uncalled-bet handling regresses is named
# by the failing test rather than hidden in a combined run.
ROOMS = [
    pytest.param(PokerStars, "pokerstars/holdem/cash_nl_6max.txt", id="pokerstars"),
    pytest.param(PartyPoker, "partypoker/stud/7stud.txt", id="partypoker"),
    pytest.param(Winamax, "winamax/nlhe_cash.txt", id="winamax"),
    pytest.param(Unibet, "unibet/banzai.txt", id="unibet"),
    pytest.param(iPoker, "ipoker/twister/twister_sng.txt", id="ipoker"),
    pytest.param(Bovada, "bovada/zone_poker.txt", id="bovada"),
    pytest.param(Winning, "winning/modern_cash.txt", id="winning"),
    pytest.param(Cake, "cake/cash_nlhe.txt", id="cake"),
    pytest.param(PacificPoker, "pacific/jackpot_table.txt", id="pacific"),
    pytest.param(GGPoker, "ggpoker/nlh_cash_6max.txt", id="ggpoker"),
]


@pytest.fixture(scope="module")
def parser_config() -> Config:
    return Config()


def parse_fixture(parser_class, parser_config, relative_path: str):
    file_path = FIXTURES / relative_path
    assert file_path.exists(), f"Fixture file not found: {file_path}"
    parser = parser_class(config=parser_config, in_path=str(file_path), autostart=True)
    hands = parser.getProcessedHands()
    assert len(hands) > 0, f"No hands parsed from {file_path}"
    return hands


@pytest.mark.parametrize(("parser_class", "fixture"), ROOMS)
def test_a_returned_bet_is_given_back_to_one_player(parser_class, fixture, parser_config) -> None:
    for hand in parse_fixture(parser_class, parser_config, fixture):
        for player, amount in hand.pot.returned.items():
            assert amount > 0, f"hand {hand.handid}: uncalled bet returned to {player} is {amount}"


@pytest.mark.parametrize(("parser_class", "fixture"), ROOMS)
def test_the_pot_is_exactly_what_was_collected_plus_rake(parser_class, fixture, parser_config) -> None:
    # The returned chips are already out of totalpot, so anything left over
    # after the collectors and the rake is money the parser invented or lost.
    for hand in parse_fixture(parser_class, parser_config, fixture):
        hand.calculate_net_collected()
        collected = sum(hand.collectees.values())
        rake = Decimal(str(hand.rake))

        assert hand.totalpot == collected + rake, (
            f"hand {hand.handid}: pot {hand.totalpot} != collected {collected} + rake {rake}"
            f" (returned {sum(hand.pot.returned.values())})"
        )
