from decimal import Decimal
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel

from fpdb_3_legacy.GuiTourHandViewer import TourHandViewer
from fpdb_3_legacy.localized_formats import format_number


def test_add_hand_row_sorts_using_raw_numeric_values() -> None:
    """No QApplication needed: this only fills a model, it opens no widget.

    Asking for pytest-qt's ``qapp`` made the test error out in CI, which runs
    with ``-p no:pytest-qt`` and so has no such fixture.
    """
    colnum = {
        "Stakes": 0,
        "Players": 1,
        "Pos": 2,
        "Street0": 3,
        "Action0": 4,
        "Street1-4": 5,
        "Action1-4": 6,
        "Won": 7,
        "Bet": 8,
        "Net": 9,
        "Game": 10,
        "HandId": 11,
        "Total Pot": 12,
        "Rake": 13,
        "SiteHandNo": 14,
    }
    viewer = SimpleNamespace(
        colnum=colnum,
        filters=SimpleNamespace(get_hero_for_site=lambda *_args: "Hero"),
        model=QStandardItemModel(),
        render_cards=lambda _cards: None,
    )
    hand = SimpleNamespace(
        hero="Hero",
        sitename="Winamax",
        collectees={"Hero": Decimal("1185.00")},
        pot=SimpleNamespace(committed={"Hero": Decimal("500.00")}),
        players=[(1, "Hero"), (2, "Villain")],
        totalpot=Decimal("1250.00"),
        handid="123456789",
        gametype={"base": "hold", "category": "holdem"},
        board={"FLOP": ["As", "Kd", "2c"], "TURN": ["3h"], "RIVER": ["4s"]},
        get_player_position=lambda _hero: "B",
        get_actions_short=lambda *_args: "R",
        get_actions_short_streets=lambda *_args: "C",
        getStakesAsString=lambda: "10/20",
        join_holecards=lambda _hero: "Ah Kh",
    )

    TourHandViewer.addHandRow(viewer, 42, hand)

    assert viewer.model.rowCount() == 1
    assert viewer.model.item(0, colnum["Won"]).text() == format_number(Decimal("1185.00"))
    assert viewer.model.item(0, colnum["Won"]).data(Qt.ItemDataRole.UserRole) == pytest.approx(1185.0)
    assert viewer.model.item(0, colnum["Total Pot"]).data(Qt.ItemDataRole.UserRole) == pytest.approx(1250.0)


def test_inactive_card_filter_accepts_rows_without_inspecting_cards() -> None:
    viewer = SimpleNamespace(
        filters=SimpleNamespace(getCards=lambda: {}),
        model=QStandardItemModel(),
        colnum={"Street0": 0},
    )

    assert TourHandViewer.is_row_in_card_filter(viewer, 0) is True
