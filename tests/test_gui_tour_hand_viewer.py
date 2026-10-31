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


# --------------------------------------------------------------------------
# Category, Limit and Buy-In filters (#650)
# --------------------------------------------------------------------------

# hand id, tourney type id
_HANDS = ((1, 10), (2, 10), (3, 20), (4, 30), (5, 40))
# tourney type id, category, limitType, buyin, fee, currency
_TOURNEY_TYPES = (
    (10, "holdem", "nl", 100, 10, "EUR"),
    (20, "omahahi", "pl", 100, 10, "EUR"),
    (30, "holdem", "nl", 500, 50, "EUR"),
    (40, "holdem", "fl", 100, 10, "USD"),
)


def _mixed_tourney_db():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE Gametypes (id INTEGER, category TEXT, type TEXT);
        CREATE TABLE Hands (id INTEGER, gametypeId INTEGER, startTime TEXT, tourneyId INTEGER);
        CREATE TABLE HandsPlayers (handId INTEGER, playerId INTEGER, position TEXT);
        CREATE TABLE Tourneys (id INTEGER, tourneyTypeId INTEGER);
        CREATE TABLE TourneyTypes (
            id INTEGER, category TEXT, limitType TEXT, buyin INTEGER, fee INTEGER, currency TEXT
        );
        INSERT INTO Gametypes VALUES (1, 'holdem', 'tour');
        """
    )
    conn.executemany("INSERT INTO TourneyTypes VALUES (?, ?, ?, ?, ?, ?)", _TOURNEY_TYPES)
    for hand_id, type_id in _HANDS:
        conn.execute("INSERT INTO Tourneys VALUES (?, ?)", (hand_id, type_id))
        conn.execute("INSERT INTO Hands VALUES (?, 1, '2026-06-07 18:00:00', ?)", (hand_id, hand_id))
        # Two seats per hand: the query must still return each hand once.
        conn.execute("INSERT INTO HandsPlayers VALUES (?, 1, 'B')", (hand_id,))
        conn.execute("INSERT INTO HandsPlayers VALUES (?, 2, 'S')", (hand_id,))
    return conn


def _hand_ids(*, categories=(), limits=(), buyins=()):
    from fpdb_3_legacy.sql_queries_replayer import replayer_queries

    conn = _mixed_tourney_db()

    def no_other_filter(query):
        for placeholder in ("<game_test>", "<limit_test>", "<player_test>", "<position_test>"):
            query = query.replace(placeholder, "")
        return query

    viewer = SimpleNamespace(
        db=SimpleNamespace(sql=SimpleNamespace(query=replayer_queries()), get_cursor=conn.cursor),
        filters=SimpleNamespace(
            replace_placeholders_with_filter_values=no_other_filter,
            getTourneyCat=lambda: list(categories),
            getTourneyLim=lambda: list(limits),
            getTourneyBuyin=lambda: list(buyins),
        ),
    )
    return sorted(TourHandViewer.get_hand_ids_from_date_range(viewer, "2026-01-01", "2026-12-31"))


def test_the_category_filter_keeps_only_the_selected_category() -> None:
    """#650: with only Omaha selected, the holdem tournaments' hands were still listed."""
    assert _hand_ids(categories=["omahahi"]) == [3]
    assert _hand_ids(categories=["holdem"]) == [1, 2, 4, 5]


def test_the_limit_filter_keeps_only_the_selected_limits() -> None:
    assert _hand_ids(limits=["pl"]) == [3]
    assert _hand_ids(limits=["nl", "fl"]) == [1, 2, 4, 5]


def test_the_buyin_filter_tells_buyins_and_currencies_apart() -> None:
    from fpdb_3_legacy.Filters import tourney_buyin_key

    assert _hand_ids(buyins=[tourney_buyin_key(500, 50, "EUR")]) == [4]
    # The same 1.00+0.10 in another currency is another buy-in.
    assert _hand_ids(buyins=[tourney_buyin_key(100, 10, "EUR")]) == [1, 2, 3]


def test_the_filters_combine() -> None:
    from fpdb_3_legacy.Filters import tourney_buyin_key

    assert _hand_ids(categories=["holdem"], buyins=[tourney_buyin_key(100, 10, "EUR")]) == [1, 2]


def test_an_empty_filter_restricts_nothing() -> None:
    assert _hand_ids() == [1, 2, 3, 4, 5]


def test_null_tournament_values_match_their_none_boxes() -> None:
    from fpdb_3_legacy.GuiTourHandViewer import hands_in_tourney_selection

    rows = [(1, None, None, None, None, None), (2, "holdem", "nl", 100, 10, "EUR")]

    assert hands_in_tourney_selection(rows, categories=[None], limits=[], buyins=[]) == [1]
    assert hands_in_tourney_selection(rows, categories=[], limits=[None], buyins=[]) == [1]
    assert hands_in_tourney_selection(rows, categories=[], limits=[], buyins=["None"]) == [1]
