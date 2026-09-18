"""The 169 Hold'em starting-hand classes (#301).

What the range explorer rests on, checked without a database: the class an
engine query groups by and the class a label names are the same class, the grid
is the standard 13x13, and the SQL classification agrees with the Python one for
every card pair in the deck -- including the pairs nobody saw, which stay
unknown instead of being guessed.
"""

from __future__ import annotations

import sqlite3

import pytest

from fpdb_3_legacy import Card
from fpdb_3_legacy import holdem_classes as hc

# The deck as fpdb stores it: 1..52, rank-major within a suit, 0 for unknown.
CARDS = list(range(0, 53))


def test_the_three_class_types_have_the_combinations_they_claim():
    assert hc.combos(hc.class_id_of_label("AA")) == 6
    assert hc.combos(hc.class_id_of_label("AKs")) == 4
    assert hc.combos(hc.class_id_of_label("AKo")) == 12


def test_the_grid_covers_the_whole_deck_exactly():
    """169 classes, 1326 combinations: the arithmetic a range share rests on."""
    every = [class_id for row in hc.grid_ids() for class_id in row]
    assert len(every) == 169
    assert len(set(every)) == 169
    assert sum(hc.combos(class_id) for class_id in every) == hc.DEALT_COMBOS == 1326
    # 13 pairs x 6, 78 suited x 4, 78 offsuit x 12.
    kinds = [hc.kind(class_id) for class_id in every]
    assert kinds.count("pair") == 13
    assert kinds.count("suited") == 78
    assert kinds.count("offsuit") == 78


def test_the_grid_is_the_standard_one():
    labels = hc.grid_labels()
    assert labels[0][:3] == ("AA", "AKs", "AQs")
    assert [labels[row][0] for row in range(3)] == ["AA", "AKo", "AQo"]
    assert labels[0][12] == "A2s"
    assert labels[12][12] == "22"
    assert [labels[index][index] for index in range(13)] == [
        "AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66", "55", "44", "33", "22",
    ]


def test_a_label_and_its_id_are_the_same_thing_both_ways():
    for class_id in hc.ALL_IDS:
        text = hc.label(class_id)
        assert hc.class_id_of_label(text) == class_id
        assert hc.class_id_of_label(text.lower()) == class_id, "labels are case-insensitive"


def test_the_ids_are_the_codebase_s_canonical_ones():
    """``Card`` owns the numbering; this module must not invent a second one."""
    assert hc.class_id_of_label("AKs") == Card.twoStartCards(14, "s", 13, "s") == 168
    assert hc.class_id_of_label("AKo") == Card.twoStartCards(14, "s", 13, "h") == 156
    assert hc.class_id_of_label("22") == Card.twoStartCards(2, "h", 2, "d") == 1
    assert hc.class_id_of_label("xx") == Card.HOLDEM_UNKNOWN_HAND == 170
    assert hc.label(168) == Card.twoStartCardString(168)


def test_a_grid_position_and_a_label_agree():
    for row, labels in enumerate(hc.grid_labels()):
        for col, text in enumerate(labels):
            assert hc.grid_position(text) == (row, col)


@pytest.mark.parametrize(
    ("label", "expected"),
    [("AA", "pair"), ("AKs", "suited"), ("AKo", "offsuit"), ("xx", "unknown")],
)
def test_kind_reads_the_label(label, expected):
    assert hc.kind(hc.class_id_of_label(label)) == expected


def test_the_unknown_class_is_a_class_of_its_own():
    assert hc.is_unknown(hc.UNKNOWN_ID)
    assert hc.label(hc.UNKNOWN_ID) == hc.UNKNOWN_LABEL == "xx"
    assert hc.kind(hc.UNKNOWN_ID) == "unknown"
    assert hc.combos(hc.UNKNOWN_ID) == 0
    assert hc.label(9999) == "xx", "anything outside the table is not a class either"


def test_suited_and_offsuit_are_never_the_same_id():
    """The one arithmetic that must never collide: AKs is not AKo."""
    assert hc.class_id_of_label("AKs") != hc.class_id_of_label("AKo")
    pairs = [(high, low) for index, high in enumerate(hc.RANKS) for low in hc.RANKS[index + 1 :]]
    suited = {hc.class_id_of_label(f"{high}{low}s") for high, low in pairs}
    offsuit = {hc.class_id_of_label(f"{high}{low}o") for high, low in pairs}
    assert len(suited) == len(offsuit) == 78
    assert suited.isdisjoint(offsuit)
    assert suited.isdisjoint(set(hc.ALL_IDS) - suited - offsuit), "nor is either one a pair"


@pytest.mark.parametrize("text", ["AK", "AKx", "AAs", "KAo", "1", "", "AKso", "ZZs"])
def test_a_label_that_does_not_say_what_it_means_is_refused(text):
    with pytest.raises(hc.UnknownClass):
        hc.class_id_of_label(text)


def test_a_bare_pair_is_accepted_and_a_bare_suited_hand_is_not():
    assert hc.class_id_of_label("AA") == hc.class_id_of_label("aa")
    with pytest.raises(hc.UnknownClass, match="suited or offsuit"):
        hc.class_id_of_label("AK")


def test_class_ids_takes_labels_and_the_ids_the_engine_returns():
    assert hc.class_ids(["AKs", 168, "xx"]) == [168, 168, 170]
    assert hc.class_ids([hc.UNKNOWN_ID]) == [170]
    for bad in (0, 171, 999, True):
        with pytest.raises(hc.UnknownClass):
            hc.class_ids([bad])


def test_a_selection_counts_its_combinations_and_its_share_of_the_deck():
    assert hc.combos_of(["AA", "AKs", "AKo"]) == 6 + 4 + 12 == 22
    assert hc.share_of_dealt(["AA", "AKs", "AKo"]) == pytest.approx(22 / 1326)
    assert hc.share_of_dealt([*hc.ALL_IDS, hc.UNKNOWN_ID]) == pytest.approx(1.0), "the whole grid is the whole deck"


def test_the_cards_of_a_hand_player_become_a_class():
    """The encoding the SQL reads: 1..52, rank-major, 0 unknown."""
    assert hc.class_id_from_cards(Card.encodeCard("As"), Card.encodeCard("Ks")) == 168
    assert hc.class_id_from_cards(Card.encodeCard("As"), Card.encodeCard("Kh")) == 156
    assert hc.class_id_from_cards(Card.encodeCard("2h"), Card.encodeCard("2d")) == 1
    assert hc.class_id_from_cards(0, Card.encodeCard("As")) == hc.UNKNOWN_ID
    assert hc.class_id_from_cards(0, 0) == hc.UNKNOWN_ID
    assert hc.label_of_cards(Card.encodeCard("Ah"), Card.encodeCard("Ad")) == "AA"
    assert (hc.rank_of_card(Card.encodeCard("Ah")), hc.suit_of_card(Card.encodeCard("Ah"))) == (14, "h")


def test_the_sql_classification_agrees_with_the_python_one_for_every_card_pair():
    """The whole point of one definition: the grid cannot disagree with a filter.

    Every ordered pair of the 53 card values -- real cards, and the zero that
    means "not shown" -- is classified by SQL and by ``Card.twoStartCards``.
    """
    expression = hc.holdem_class_expression("")
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE t (card1 INT, card2 INT)")
        pairs = [(first, second) for first in CARDS for second in CARDS]
        connection.executemany("INSERT INTO t VALUES (?, ?)", pairs)
        rows = connection.execute(f"SELECT {expression} FROM t").fetchall()
    finally:
        connection.close()
    mismatches = [
        (first, second, int(got), hc.class_id_from_cards(first, second))
        for (first, second), (got,) in zip(pairs, rows)
        if int(got) != hc.class_id_from_cards(first, second)
    ]
    assert mismatches == []
    assert len(pairs) == 53 * 53


def test_the_sql_says_unknown_when_either_card_is_missing():
    expression = hc.holdem_class_expression("")
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE t (card1 INT, card2 INT)")
        connection.execute("INSERT INTO t VALUES (0, 52), (52, 0), (0, 0), (52, 51)")
        assert [row[0] for row in connection.execute(f"SELECT {expression} FROM t")] == [
            hc.UNKNOWN_ID,
            hc.UNKNOWN_ID,
            hc.UNKNOWN_ID,
            168,
        ]
    finally:
        connection.close()


def test_the_expression_is_qualified_for_the_query_engine():
    """The engine reads the pairs table, so the expression must name its alias."""
    assert "HP.card1" in hc.holdem_class_expression("HP.")
    assert hc.holdem_class_expression("X.").startswith("CASE WHEN X.card2 > 0" .replace("X.card2 > 0", "X.card1 > 0"))
