"""The replayer's ICM line: shown once the hero is all-in in a priced tournament hand (#446)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from fpdb_3_legacy.GuiReplayer import GuiReplayer  # noqa: E402 - after the Qt availability probe
from fpdb_3_legacy.hand_icm import AllInIcm, HandIcm  # noqa: E402

PRICED = HandIcm(
    AllInIcm(
        street="PREFLOP",
        players=("Hero", "Villain"),
        equity={"Hero": 0.46, "Villain": 0.54},
        chip_ev={"Hero": Decimal("-148"), "Villain": Decimal("348")},
        icm_ev={"Hero": -1.29, "Villain": -2.05},
        icm_result={"Hero": -10.52, "Villain": 9.68},
    )
)


def frame(*players):
    return SimpleNamespace(players=[SimpleNamespace(name=n, allin=a, action=act) for n, a, act in players])


def replayer(priced, hero="Hero"):
    return SimpleNamespace(hand_icm=priced, Heroes=hero)


ALL_IN = frame(("Hero", True, "raises"), ("Villain", True, "calls"), ("Short", False, "folds"))


@pytest.mark.qt
def test_the_hero_s_all_in_shows_icm_ev_result_and_chip_ev(qtbot) -> None:
    text, colour = GuiReplayer._icm_line(replayer(PRICED), ALL_IN)

    assert "ICM $EV -1" in text and "result -10" in text and "chip EV -148" in text
    assert colour == "#ff6b6b"  # a loss of prize equity


@pytest.mark.qt
def test_a_gain_in_prize_equity_is_green(qtbot) -> None:
    gain = HandIcm(PRICED.allin.__class__(**{**PRICED.allin.__dict__, "icm_ev": {"Hero": 0.8, "Villain": -2.0}}))

    assert GuiReplayer._icm_line(replayer(gain), ALL_IN)[1] == "#4ade80"


@pytest.mark.qt
def test_a_field_taken_from_the_table_is_said(qtbot) -> None:
    table_only = HandIcm(PRICED.allin.__class__(**{**PRICED.allin.__dict__, "table_only": True}))

    assert "whole field" in GuiReplayer._icm_line(replayer(table_only), ALL_IN)[0]


@pytest.mark.qt
def test_nothing_is_shown_before_the_all_in_or_for_a_folded_hero(qtbot) -> None:
    before = frame(("Hero", False, "raises"), ("Villain", False, "calls"))
    folded = frame(("Hero", False, "folds"), ("Villain", True, "raises"), ("Short", True, "calls"))

    assert GuiReplayer._icm_line(replayer(PRICED), before) is None
    assert GuiReplayer._icm_line(replayer(PRICED), folded) is None


@pytest.mark.qt
def test_a_hand_that_cannot_be_priced_says_why_but_a_cash_hand_says_nothing(qtbot) -> None:
    unknown = HandIcm(None, "no payout structure known: import the summary, enter one or apply a preset")
    cash = HandIcm(None, "not a tournament hand")

    text, colour = GuiReplayer._icm_line(replayer(unknown), ALL_IN)
    assert text.startswith("ICM: no payout structure known") and colour == "#9aa5ad"
    assert GuiReplayer._icm_line(replayer(cash), ALL_IN) is None
    assert GuiReplayer._icm_line(replayer(None), ALL_IN) is None
