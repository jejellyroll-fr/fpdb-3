"""The replayer's bounty line: shown once the hero is all-in in a knockout tournament hand (#447)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from fpdb_3_legacy.GuiReplayer import GuiReplayer  # noqa: E402 - after the Qt availability probe
from fpdb_3_legacy.hand_bounty import AllInBounty, HandBounty  # noqa: E402

PKO = AllInBounty(
    players=("Hero", "Villain"),
    win={"Hero": 0.46, "Villain": 0.54},
    collects={"Hero": Decimal("7.50"), "Villain": Decimal(0)},
    cash={"Hero": Decimal("3.75"), "Villain": Decimal(0)},
    bounty_ev={"Hero": Decimal("1.725"), "Villain": Decimal(0)},
    head_ev={"Hero": Decimal("1.725"), "Villain": Decimal(0)},
    chip_ev={"Hero": Decimal("-148"), "Villain": Decimal("348")},
    currency="USD",
)


def frame(*players):
    return SimpleNamespace(players=[SimpleNamespace(name=n, allin=a, action=act) for n, a, act in players])


def replayer(priced, hero="Hero"):
    return SimpleNamespace(hand_bounty=priced, Heroes=hero)


ALL_IN = frame(("Hero", True, "raises"), ("Villain", True, "calls"), ("Short", False, "folds"))


@pytest.mark.qt
def test_a_progressive_bounty_shows_its_cash_ev_and_what_goes_to_the_hero_s_own(qtbot) -> None:
    text, colour = GuiReplayer._bounty_line(replayer(HandBounty(PKO)), ALL_IN)

    assert text.startswith("Bounty EV +") and "1.7" in text and "to your own bounty" in text
    assert "adjusted" not in text and colour == "#4ade80"


@pytest.mark.qt
def test_a_known_chip_value_adds_the_bounty_adjusted_chip_ev(qtbot) -> None:
    adjusted = replace(PKO, adjusted_chip_ev={"Hero": Decimal("3772"), "Villain": Decimal("348")})

    assert "bounty-adjusted chip EV +3" in GuiReplayer._bounty_line(replayer(HandBounty(adjusted)), ALL_IN)[0]


@pytest.mark.qt
def test_an_all_in_that_busts_nobody_says_so(qtbot) -> None:
    text, colour = GuiReplayer._bounty_line(replayer(HandBounty(PKO), hero="Villain"), ALL_IN)

    assert "does not bust" in text and colour == "#9aa5ad"


@pytest.mark.qt
def test_a_freezeout_says_nothing_and_an_unpriced_knockout_says_why(qtbot) -> None:
    freezeout = HandBounty(None, "not a knockout tournament")
    hidden = HandBounty(None, "the bounty in play is not in the hand history")

    assert GuiReplayer._bounty_line(replayer(freezeout), ALL_IN) is None
    assert GuiReplayer._bounty_line(replayer(None), ALL_IN) is None
    assert GuiReplayer._bounty_line(replayer(hidden), ALL_IN)[0].startswith("Bounty: the bounty in play")
