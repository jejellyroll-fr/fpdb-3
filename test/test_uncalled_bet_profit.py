"""An uncalled bet must leave pot.committed, not just be recorded as returned.

DerivedStats derives totalProfit from pot.committed and documents that the
uncalled bet has already been taken out of it -- which holds for parsers that
read an "Uncalled bet returned" line and call Hand.addUncalled (-> removeMoney).

Captured hands carry no such line: totalPot() discovers the uncalled bet itself
and used to record it in pot.returned only, leaving committed inflated. Every
hand won without showdown was then stored as a loss: on 2026-07-23 two CoinPoker
hands were saved as -0.11 and -0.02 instead of +0.13 and +0.05, so the graph
showed 0.42 where the hand viewer (and the room) showed 0.73.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.coinpoker_hand_builder import build_hands
from fpdb_3_legacy.coinpoker_live_capture import COINPOKER_SITE_ID
from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig, build_fpdb_hand

FIXTURE = Path(__file__).parent / "data" / "coinpoker_hand_events.json"


@pytest.fixture
def first_captured_hand():
    events = [tuple(e) for e in json.loads(FIXTURE.read_text())]
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    hand_data = next(iter(build_hands(events, "PLO4")))
    hand = build_fpdb_hand(hand_data, config=config)
    hand.totalPot()
    return hand


def test_uncalled_bet_is_removed_from_committed(first_captured_hand) -> None:
    hand = first_captured_hand
    # Villain4 posts 0.01 + calls 0.06, then bets 0.16 on the turn and is folded to.
    assert hand.pot.returned["Villain4"] == Decimal("0.16")
    # 0.23 was put in, but 0.16 came straight back: only 0.07 was ever at risk.
    assert hand.pot.committed["Villain4"] == Decimal("0.07")


def test_hand_won_without_showdown_is_a_profit_not_a_loss(first_captured_hand) -> None:
    hand = first_captured_hand
    collected = sum(Decimal(str(amount)) for player, amount in hand.collected if player == "Villain4")

    profit = collected - hand.pot.committed["Villain4"]

    assert collected == Decimal("0.2")
    assert profit == Decimal("0.13")  # was -0.03 while the uncalled bet stayed committed


def test_players_who_called_are_untouched(first_captured_hand) -> None:
    # Only the player whose bet went uncalled gets money back.
    hand = first_captured_hand
    assert set(hand.pot.returned) == {"Villain4"}
