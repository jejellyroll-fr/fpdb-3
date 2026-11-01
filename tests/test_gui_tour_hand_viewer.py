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


# Hero's turn bet is not called: 300 comes back, and Hero collects the 200 pot
# both players built with 100 each.
STARS_TOURNEY_UNCALLED = """PokerStars Hand #262000000001: Tournament #3000000001, $1.00+$0.10 USD Hold'em No Limit - Level I (10/20) - 2026/06/07 18:00:00 CET
Table '3000000001 1' 9-max Seat #1 is the button
Seat 1: Villain (1500 in chips)
Seat 2: Hero (1500 in chips)
Villain: posts small blind 10
Hero: posts big blind 20
*** HOLE CARDS ***
Dealt to Hero [As Kd]
Villain: raises 20 to 40
Hero: calls 20
*** FLOP *** [9h Kd 2c]
Hero: bets 60
Villain: calls 60
*** TURN *** [9h Kd 2c] [3s]
Hero: bets 300
Villain: folds
Uncalled bet (300) returned to Hero
Hero collected 200 from pot
*** SUMMARY ***
Total pot 200 | Rake 0
Board [9h Kd 2c 3s]
Seat 1: Villain (button) (small blind) folded on the Turn
Seat 2: Hero (big blind) collected (200)
"""


def _parsed_tourney_hand(hand_text: str):
    import tempfile

    from fpdb_3_legacy import Configuration, Hand
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    config = Configuration.Config()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(hand_text)
    converter = PokerStars(config, tmp.name)
    gametype = converter.determineGameType(hand_text)
    return Hand.HoldemOmahaHand(config, converter, "PokerStars", gametype, hand_text, builtFrom="HHC")


def _row_for(player: str, hand) -> dict:
    colnum = {
        name: index
        for index, name in enumerate(
            ("Stakes", "Players", "Pos", "Street0", "Action0", "Street1-4", "Action1-4", "Won", "Bet", "Net",
             "Game", "HandId", "Total Pot", "Rake", "SiteHandNo")
        )
    }
    viewer = SimpleNamespace(
        colnum=colnum,
        filters=SimpleNamespace(get_hero_for_site=lambda *_args: player),
        model=QStandardItemModel(),
        render_cards=lambda _cards: None,
    )
    hand.hero = player
    TourHandViewer.addHandRow(viewer, 7, hand)
    return {name: viewer.model.item(0, index).data(Qt.ItemDataRole.UserRole) for name, index in colnum.items()}


def test_net_of_a_won_hand_takes_off_what_the_hero_put_in() -> None:
    """#653: Net was the gross amount collected."""
    row = _row_for("Hero", _parsed_tourney_hand(STARS_TOURNEY_UNCALLED))

    assert row["Won"] == pytest.approx(200.0)
    assert row["Bet"] == pytest.approx(100.0)  # the uncalled 300 is not part of it
    assert row["Net"] == pytest.approx(100.0)
    assert row["Rake"] == pytest.approx(0.0)


def test_net_of_a_lost_hand_is_what_the_player_put_in() -> None:
    row = _row_for("Villain", _parsed_tourney_hand(STARS_TOURNEY_UNCALLED))

    assert row["Won"] == pytest.approx(0.0)
    assert row["Net"] == pytest.approx(-100.0)


def test_net_matches_the_profit_the_import_stores() -> None:
    """The viewer and the reports must agree: HandsPlayers.totalProfit is in cents."""
    from fpdb_3_legacy.DerivedStats import DerivedStats

    stats = DerivedStats()
    stats.getStats(_parsed_tourney_hand(STARS_TOURNEY_UNCALLED))
    stored = stats.getHandsPlayers()

    for player in ("Hero", "Villain"):
        row = _row_for(player, _parsed_tourney_hand(STARS_TOURNEY_UNCALLED))
        assert row["Net"] == pytest.approx(stored[player]["totalProfit"] / 100)
