"""Hand-level advanced filter semantics for the Hand Viewer (#396)."""

import sqlite3

import pytest

from fpdb_3_legacy.analytics_query import escape_literal_percent
from fpdb_3_legacy.hand_viewer_filters import (
    POSTFLOP_ACTION_TYPES,
    build_filter_clauses,
    required_analytics_subsystems,
)
from fpdb_3_legacy.holdem_classes import class_id_of_label


def _run_filters(connection, filters):
    clauses, params = build_filter_clauses(filters, "?")
    where = " AND ".join(clauses) if clauses else "1=1"
    return [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT h.id FROM Hands h JOIN Gametypes gt ON gt.id = h.gametypeId "
            f"JOIN HandsPlayers hp ON hp.handId = h.id WHERE {where} ORDER BY h.id",
            params,
        )
    ]


def _database():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE Hands (id INTEGER PRIMARY KEY, gametypeId INTEGER, finalPot INTEGER);
        CREATE TABLE Gametypes (id INTEGER PRIMARY KEY, category TEXT, bigBlind INTEGER, base TEXT DEFAULT 'hold');
        CREATE TABLE HandsPlayers (
            handId INTEGER, playerId INTEGER, card1 INTEGER, card2 INTEGER,
            card3 INTEGER, card4 INTEGER, card5 INTEGER, card6 INTEGER,
            card7 INTEGER, card8 INTEGER, card9 INTEGER, card10 INTEGER,
            card11 INTEGER, card12 INTEGER, card13 INTEGER, card14 INTEGER,
            card15 INTEGER, card16 INTEGER, card17 INTEGER, card18 INTEGER,
            card19 INTEGER, card20 INTEGER,
            street0VPIChance INTEGER, street0VPI INTEGER, wentAllIn INTEGER,
            street0Seen INTEGER, street1Seen INTEGER, street2Seen INTEGER, street3Seen INTEGER,
            sawShowdown INTEGER, totalProfit INTEGER
        );
        CREATE TABLE HandsActions (
            handId INTEGER, playerId INTEGER, actionNo INTEGER, street INTEGER,
            actionType TEXT, effectiveStackBB INTEGER, sizingBp INTEGER, allIn INTEGER
        );
        CREATE TABLE HandsSituations (
            handId INTEGER, playerId INTEGER, actionNo INTEGER,
            primaryLabel TEXT, labels TEXT, response TEXT
        );
        INSERT INTO Gametypes (id, category, bigBlind) VALUES
            (1, 'holdem', 10), (2, 'omahahi', 10), (6, 'aof_omaha', 10);
        INSERT INTO Hands VALUES (1, 1, 100), (2, 1, 600), (3, 2, 100);
        INSERT INTO HandsPlayers (
            handId, playerId, card1, card2, card3, card4,
            street0VPIChance, street0VPI, wentAllIn,
            street0Seen, street1Seen, street2Seen, street3Seen, sawShowdown, totalProfit
        ) VALUES
            (1, 11, 13, 12, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 50),
            (2, 22, 13, 12, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, -100),
            (3, 33, 7, 8, 13, 12, 1, 1, 0, 0, 1, 0, 0, 0, 20);
        INSERT INTO HandsActions VALUES
            (1, 11, 1, 0, 'raises', 10000, 0, 0), (1, 11, 2, 1, 'calls', 9000, 5000, 0),
            (2, 22, 1, 0, 'folds', 2000, 0, 0), (2, 22, 2, 1, 'bets', 1800, 2500, 1);
        INSERT INTO HandsSituations VALUES
            (1, 11, 1, 'open_raise', '["open_raise"]', 'raise'),
            (1, 11, 2, 'facing_cbet', '["facing_cbet"]', 'call'),
            (2, 22, 1, 'facing_open', '["facing_open"]', 'fold');
        """
    )
    return connection


def test_starting_hand_filter_includes_two_card_games_and_excludes_omaha():
    connection = _database()
    try:
        connection.execute("INSERT INTO Gametypes (id, category, bigBlind) VALUES (3, 'aof_holdem', 10)")
        connection.execute("INSERT INTO Gametypes (id, category, bigBlind) VALUES (4, 'fusion', 10)")
        connection.execute("INSERT INTO Hands VALUES (5, 3, 100)")
        connection.execute("INSERT INTO Hands VALUES (6, 4, 100)")
        connection.execute(
            "INSERT INTO HandsPlayers (handId, playerId, card1, card2) VALUES (5, 55, 13, 12)"
        )
        connection.execute(
            "INSERT INTO HandsPlayers (handId, playerId, card1, card2) VALUES (6, 66, 13, 12)"
        )
        assert _run_filters(connection, {"starting_hands": ["AKs"]}) == [1, 2, 5, 6]
        assert class_id_of_label("AKs") in range(1, 170)
    finally:
        connection.close()


def test_preflop_and_postflop_filters_match_different_decisions_in_one_hand():
    connection = _database()
    try:
        filters = {"preflop": "rfi", "postflop": "faced_cbet"}
        assert _run_filters(connection, filters) == [1]
    finally:
        connection.close()


def test_generic_limp_filter_includes_over_limps():
    connection = _database()
    try:
        connection.execute("INSERT INTO Hands VALUES (4, 1, 100)")
        connection.execute(
            "INSERT INTO HandsPlayers (handId, playerId, street0VPIChance, street0VPI, wentAllIn, "
            "street1Seen, street2Seen, street3Seen, sawShowdown, totalProfit) "
            "VALUES (4, 44, 1, 1, 0, 0, 0, 0, 0, 20)"
        )
        connection.execute(
            "INSERT INTO HandsActions VALUES (4, 44, 1, 0, 'calls', 10000, 0, 0)"
        )
        connection.execute(
            "INSERT INTO HandsSituations VALUES "
            "(4, 44, 1, 'over_limp', '[\"over_limp\", \"facing_limpers\"]', 'call')"
        )
        assert _run_filters(connection, {"preflop": "limp"}) == [4]
    finally:
        connection.close()


def test_exact_cards_match_known_cards_without_becoming_a_range_class():
    connection = _database()
    try:
        assert _run_filters(connection, {"exact_card_1": "Ah", "exact_card_2": "Kh"}) == [1, 2, 3]
        assert _run_filters(connection, {"exact_card_1": "Ah"}) == [1, 2, 3]
        assert _run_filters(connection, {"exact_card_1": "Ah", "exact_card_2": "Ah"}) == []
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"starting_hands": ["AKs"], "exact_card_1": "Ah", "exact_card_2": "Kh"}, [1, 2]),
        ({"preflop": "vpip"}, [1, 3]),
        ({"preflop": "not_vpip"}, [2]),
        ({"postflop": "saw_turn"}, [1]),
        ({"postflop": "showdown"}, [2]),
        ({"postflop": "bet"}, [2]),
        ({"pot_min_bb": 20}, [2]),
        ({"net_max_bb": -5}, [2]),
        ({"stack_min_bb": 50, "stack_max_bb": 120}, [1]),
        ({"stack_min_bb": 95}, [1]),
        ({"sizing_bucket": "50_75"}, [1]),
        ({"sizing_bucket": "25_50"}, [2]),
        ({"players_min": 1, "players_max": 1}, [1, 2, 3]),
    ],
)
def test_action_and_numeric_filters(filters, expected):
    connection = _database()
    try:
        assert _run_filters(connection, filters) == expected
    finally:
        connection.close()


def test_empty_advanced_filters_do_not_add_sql_or_parameters():
    assert build_filter_clauses({}, "?") == ([], ())


def test_sql_placeholder_must_be_a_supported_driver_marker():
    with pytest.raises(ValueError, match="Unsupported SQL parameter placeholder"):
        build_filter_clauses({"preflop": "vpip"}, "? OR 1=1 --")


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"preflop": "vpip"}, ()),
        ({"preflop": "all_in"}, ()),
        ({"preflop": "rfi"}, ("action_events", "situations")),
        ({"postflop": "bet"}, ()),
        ({"postflop": "check_raise"}, ("action_events", "situations")),
        ({"sizing_bucket": "25_50"}, ("action_events",)),
        ({"stack_min_bb": 30}, ("action_events",)),
    ],
)
def test_advanced_filters_declare_the_analytics_subsystems_they_need(filters, expected):
    assert required_analytics_subsystems(filters) == expected


def test_starting_hand_modulo_is_escaped_for_format_style_drivers():
    clauses, _params = build_filter_clauses({"starting_hands": ["AKs"]}, "%s")
    query = escape_literal_percent(" AND ".join(clauses), "%s")

    assert "%%" in query
    assert "%s" in query


@pytest.mark.parametrize(
    ("action", "stored_action"),
    [("bet", "bets"), ("call", "calls"), ("raise", "raises"), ("check", "checks"), ("fold", "folds")],
)
def test_postflop_action_filter_uses_the_persisted_action_verb(action, stored_action):
    clauses, params = build_filter_clauses({"postflop": action}, "?")

    assert clauses
    assert params == (stored_action,)
    assert POSTFLOP_ACTION_TYPES[action] == stored_action


def test_preflop_all_in_does_not_match_an_all_in_on_the_flop():
    connection = _database()
    try:
        connection.execute("UPDATE HandsPlayers SET wentAllIn = 1 WHERE handId = 2")
        assert _run_filters(connection, {"preflop": "all_in"}) == []
        connection.execute("UPDATE HandsActions SET allIn = 1 WHERE handId = 1 AND street = 0")
        assert _run_filters(connection, {"preflop": "all_in"}) == [1]
    finally:
        connection.close()


def test_preflop_all_in_includes_a_forced_all_in_on_the_blinds_round():
    connection = _database()
    try:
        connection.execute("INSERT INTO HandsActions VALUES (2, 22, 0, -1, 'big blind', 0, 0, 1)")
        assert _run_filters(connection, {"preflop": "all_in"}) == [2]
    finally:
        connection.close()


def test_postflop_action_filter_includes_stud_seventh_street():
    connection = _database()
    try:
        connection.execute("INSERT INTO HandsActions VALUES (3, 33, 5, 4, 'checks', 0, 0, 0)")
        assert _run_filters(connection, {"postflop": "check"}) == [3]
    finally:
        connection.close()


def test_aof_omaha_flop_actions_are_postflop_but_holdem_preflop_is_not():
    connection = _database()
    try:
        connection.execute("INSERT INTO Hands VALUES (8, 6, 100)")
        connection.execute("INSERT INTO HandsPlayers (handId, playerId) VALUES (8, 88)")
        connection.execute("INSERT INTO HandsActions VALUES (8, 88, 1, 0, 'bets', 0, 0, 0)")
        # Street zero is preflop for Hold'em, but the flop for AoF Omaha.
        connection.execute("INSERT INTO HandsActions VALUES (1, 11, 3, 0, 'bets', 0, 0, 0)")
        assert _run_filters(connection, {"postflop": "bet"}) == [2, 8]
    finally:
        connection.close()


def test_starting_hand_labels_are_validated_before_querying():
    with pytest.raises(ValueError):
        build_filter_clauses({"starting_hands": ["not a range"]}, "?")


def test_named_board_street_filters_exclude_stud_and_draw():
    connection = _database()
    try:
        connection.execute("INSERT INTO Gametypes VALUES (5, 'studhi', 10, 'stud')")
        connection.execute("INSERT INTO Hands VALUES (7, 5, 100)")
        connection.execute(
            "INSERT INTO HandsPlayers (handId, playerId, street1Seen, street2Seen, street3Seen) "
            "VALUES (7, 77, 1, 1, 1)"
        )
        assert _run_filters(connection, {"postflop": "saw_flop"}) == [1, 2, 3]
        assert _run_filters(connection, {"postflop": "saw_river"}) == []
    finally:
        connection.close()


def test_named_board_street_filters_map_aof_omaha_streets():
    connection = _database()
    try:
        connection.execute("INSERT INTO Hands VALUES (8, 6, 100)")
        connection.execute(
            "INSERT INTO HandsPlayers (handId, playerId, street0Seen, street1Seen, street2Seen) "
            "VALUES (8, 88, 1, 1, 1)"
        )
        assert _run_filters(connection, {"postflop": "saw_flop"}) == [1, 2, 3, 8]
        assert _run_filters(connection, {"postflop": "saw_turn"}) == [1, 8]
        assert _run_filters(connection, {"postflop": "saw_river"}) == [8]
    finally:
        connection.close()
