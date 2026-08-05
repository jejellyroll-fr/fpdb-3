"""An uncalled bet must leave the pot, whatever the winner ends up collecting.

readAction carried a "walk detection" heuristic: when the player whose bet came
back was also the one who collected, and the returned bet was *larger than or
equal to* what he collected, Hand.addUncalled skipped pot.removeMoney entirely.

That is not the shape of a walk. A real walk returns half of what it wins -- the
big blind gets his own blind back and keeps the small blind (uncalled 30,
collected 60). The shape the heuristic actually caught is the ordinary preflop
shove that everybody folds to: 1790 returned for 150 collected. Those hands were
booked as if the whole stack had been lost.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

HAND_FILE = Path(
    "/Users/jde/Library/Application Support/PokerStarsFR/HandHistory/jeje_sat/"
    "HH20260717 T4016724563 Hold'em No Limit Varié.txt",
)

pytestmark = pytest.mark.skipif(not HAND_FILE.exists(), reason="local PokerStars history not present")


@pytest.fixture(scope="module")
def hands():
    parsed = PokerStars(config=Config(), in_path=str(HAND_FILE), autostart=True).getProcessedHands()
    for hand in parsed:
        hand.totalPot()
    return {str(hand.handid): hand for hand in parsed}


def balance(hand) -> Decimal:
    paid = sum(hand.pot.committed.values()) + sum(hand.pot.common.values())
    return paid - sum(hand.collectees.values()) - Decimal(str(hand.rake or 0))


def test_a_shove_everyone_folds_to_costs_only_the_blinds(hands) -> None:
    # jeje_sat raises 1790 to 1850 all-in, all fold, 1790 comes back, 150 won.
    hand = hands["261462025102"]

    assert hand.pot.committed["jeje_sat"] == Decimal("60")  # was 1850
    assert hand.pot.returned["jeje_sat"] == Decimal("1790")  # was absent
    assert balance(hand) == 0


def test_a_real_walk_still_balances(hands) -> None:
    # MONSAWI35 posts the big blind 50, everyone folds, 25 back, 50 collected.
    hand = hands["261462002611"]

    assert hand.pot.returned["MONSAWI35"] == Decimal("25")
    assert balance(hand) == 0


def test_every_hand_of_the_tournament_balances(hands) -> None:
    unbalanced = {hid: balance(h) for hid, h in hands.items() if balance(h)}

    assert unbalanced == {}  # 5 of the 22 hands were off before the fix
