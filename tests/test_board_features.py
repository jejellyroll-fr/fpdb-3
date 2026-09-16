"""Board texture and runout features: classification, persistence, one source of truth (#295).

Three things the epic asks for are pinned here:

* the features are a stable, orthogonal vocabulary rather than one mutually
  exclusive texture integer, so the flag catalogue may only grow at its end;
* AutoNotes and analytics classify a flop the same way, so the two AutoNotes
  projections are checked against the shared classifier rather than trusted;
* a hand can be filtered by board without re-parsing a hand history, so the rows
  the importer writes are read back out of SQLite and re-classified from the
  parsed cards, including a hand run twice.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from typing import Any

import pytest

from fpdb_3_legacy import board_features as bf
from fpdb_3_legacy.AutoNotes import _flop_texture
from fpdb_3_legacy.board_features import (
    BOARD_FEATURE_COLUMNS,
    BOARD_FEATURE_DEFAULTS,
    CONNECTIVITIES,
    FLAG_BITS,
    FLAG_NAMES,
    PAIRINGS,
    RANK_BUCKETS,
    RUNOUT_BRICK,
    RUNOUT_FLAGS,
    SUIT_STRUCTURES,
    TEXTURE_FLAGS,
    autonote_flop_texture,
    autonote_flop_texture_word,
    card_rank,
    card_string,
    card_suit,
    classify_board,
    classify_street,
    derive_board_rows,
    describe,
    flag_names,
    flop_texture_mask,
    visible_cards,
)
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_import_auxiliary import import_auxiliary_queries
from fpdb_3_legacy.sql_schema_hand import hand_schema_queries
from fpdb_3_legacy.user_autonotes_parser import extract_field_value
from tests.helpers import analytics_golden as golden

BACKENDS = ("mysql", "postgresql", "sqlite")


def sql_columns(statement: str) -> list[str]:
    """The column names an INSERT lists, in order, without the table name."""
    body = statement.split("(", 1)[1].split(")", 1)[0]
    return [part.strip().strip("`") for part in body.split(",")]


# Clauses a CREATE TABLE body may carry that are not columns.
DDL_KEYWORDS = {"PRIMARY", "FOREIGN", "UNIQUE", "KEY", "CONSTRAINT", "INDEX", "ENGINE"}


def ddl_columns(ddl: str) -> list[str]:
    """The columns a CREATE TABLE declares, in order, clauses and comments aside."""
    body = re.sub(r"/\*.*?\*/", "", ddl, flags=re.DOTALL).split("(", 1)[1]
    names = []
    # Commas inside parentheses belong to a type or a clause, not between columns.
    for part in re.split(r",(?![^()]*\))", body):
        words = part.strip().split()
        if words and words[0].strip("`").upper() not in DDL_KEYWORDS:
            names.append(words[0].strip("`"))
    return names


def rows_by_street(hand: Any) -> list[tuple[int, list[str]]]:
    """Each community street of a parsed hand with the cards it dealt, if any."""
    board = getattr(hand, "board", None) or {}
    streets = []
    for position, street in enumerate(hand.communityStreets, start=1):
        dealt = [str(card) for card in board.get(street) or () if str(card) not in ("", "0x")]
        if dealt:
            streets.append((position, dealt))
    return streets


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------
class TestFlagCatalogue:
    def test_every_flag_is_a_clean_power_of_two_and_bits_are_never_reused(self) -> None:
        """Flags are append-only: a stored mask has to keep meaning what it meant."""
        bits = [bit for _, bit in bf.FLAGS]

        assert bits == [1 << index for index in range(len(bits))]

    def test_names_and_bits_are_one_to_one(self) -> None:
        assert len(set(FLAG_BITS)) == len(FLAG_BITS) == len(FLAG_NAMES)
        for name, bit in bf.FLAGS:
            assert FLAG_NAMES[bit] == name

    def test_the_two_halves_do_not_overlap(self) -> None:
        """A texture flag says what the board is, a runout flag what the street changed."""
        texture = {name for name, _ in TEXTURE_FLAGS}
        runout = {name for name, _ in RUNOUT_FLAGS}

        assert not texture & runout
        assert texture | runout == set(FLAG_BITS)

    def test_a_mask_fits_the_stored_integer(self) -> None:
        assert max(FLAG_BITS.values()) <= 2**31 - 1

    def test_flag_names_reports_only_what_is_set_in_catalogue_order(self) -> None:
        assert flag_names(BOARD_FEATURE_DEFAULTS["textureMask"]) == ()
        assert flag_names(bf.BROADWAY_HEAVY | bf.MONOTONE) == ("monotone", "broadway_heavy")


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
class TestCardNormalisation:
    @pytest.mark.parametrize(
        ("card", "expected"),
        [
            ("Ah", "Ah"),
            # The pipeline's own spelling is preserved rather than normalised, so
            # the stored label can never disagree with the history it came from.
            ("ah", "ah"),
            ("10h", "10h"),
            (0, ""),
            (1, "2h"),
            (52, "As"),
            (99, ""),
            (None, ""),
            ("0x", ""),
            ("0", ""),
            ("", ""),
            ("   ", ""),
            ((14, "h"), "Ah"),
            ((2, "s"), "2s"),
            ((7, "x"), ""),
        ],
    )
    def test_card_string_accepts_everything_the_pipeline_carries(self, card: Any, expected: str) -> None:
        assert card_string(card) == expected

    def test_visible_cards_drops_the_placeholders_for_not_dealt(self) -> None:
        assert visible_cards(["Ah", "0x", 0, None, "", "7d"]) == ("Ah", "7d")
        assert visible_cards("Ah7d") == ()
        assert visible_cards(None) == ()

    def test_ranks_and_suits_are_read_off_a_normalized_card(self) -> None:
        assert [card_rank("Ah"), card_rank("Td"), card_rank("2c")] == [14, 10, 2]
        assert [card_suit("Ah"), card_suit("Td"), card_suit("2c")] == ["h", "d", "c"]
        assert card_rank("") == 0
        assert card_suit("") == ""


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
FLOP_CASES = [
    # The five textures the golden corpus picks apart, one per scenario 16 hand.
    (["Ah", "7d", "2c"], "rainbow", "unpaired", "ace-high", "disconnected", ()),
    (["Kh", "9h", "3c"], "two-tone", "unpaired", "king-high", "disconnected", ()),
    (["Qs", "Js", "8s"], "monotone", "unpaired", "broadway", "connected", ("flush_possible",)),
    (["9d", "9c", "4h"], "rainbow", "paired", "middle", "disconnected", ("paired",)),
    (["7h", "6d", "5c"], "rainbow", "unpaired", "low", "connected", ("connected",)),
    # An ace reads both ways: A-2-3 is a wheel flop, and the same three cards
    # are an ace-high cluster rather than a Broadway one.
    (["Ah", "2d", "3c"], "rainbow", "unpaired", "ace-high", "connected", ()),
    (["Ah", "Kd", "Qc"], "rainbow", "unpaired", "ace-high", "connected", ("broadway_heavy",)),
    # Rank buckets at their boundaries.
    (["8h", "5d", "2c"], "rainbow", "unpaired", "middle", "disconnected", ()),
    (["Th", "7d", "2c"], "rainbow", "unpaired", "broadway", "disconnected", ()),
    # A four-card board keeps the flush shape and drops the flop words.
    (["Qh", "9h", "3c", "2s"], "two-tone", "unpaired", "broadway", "disconnected", ()),
    (["Kh", "9h", "3h", "2c"], "three-flush", "unpaired", "king-high", "disconnected", ("flush_possible",)),
    (["Kh", "9h", "3h", "2h"], "four-flush", "unpaired", "king-high", "disconnected", ("four_flush",)),
    # Pairing, strongest first. Three sevens and two fours is two-tone because
    # two of the sevens and one four are diamonds -- the suit counts do not stop
    # at the flop, they just lose their three-card names.
    (["9d", "9c", "9h", "4s"], "rainbow", "trips", "middle", "disconnected", ("trips",)),
    (["9d", "9c", "4h", "4s"], "rainbow", "two-pair", "middle", "disconnected", ("two_pair_board",)),
    (["9d", "9c", "9h", "4s", "4d"], "two-tone", "full-house", "middle", "disconnected", ("full_house_board",)),
    (["9d", "9c", "9h", "9s", "4d"], "two-tone", "quads", "middle", "disconnected", ("quads",)),
    # Five to a straight is four-to-a-straight or better, and clusters tightly.
    (["9d", "8c", "7h", "6s", "5d"], "two-tone", "unpaired", "middle", "connected", ("four_straight",)),
]


class TestClassification:
    @pytest.mark.parametrize(
        ("cards", "structure", "pairing", "bucket", "connectivity", "flags"),
        FLOP_CASES,
    )
    def test_every_column_and_flag_a_reviewed_board_carries(
        self,
        cards: list[str],
        structure: str,
        pairing: str,
        bucket: str,
        connectivity: str,
        flags: tuple[str, ...],
    ) -> None:
        features = classify_board(cards)

        assert features.suitStructure == structure
        assert features.pairing == pairing
        assert features.rankBucket == bucket
        assert features.connectivity == connectivity
        assert features.cardCount == len(cards)
        assert features.topRank == max(card_rank(card) for card in cards)
        for name in flags:
            assert features.textureMask & FLAG_BITS[name], f"{name} missing for {' '.join(cards)}"

    @pytest.mark.parametrize(
        ("column", "vocabulary"),
        [
            ("suitStructure", SUIT_STRUCTURES),
            ("pairing", PAIRINGS),
            ("rankBucket", RANK_BUCKETS),
            ("connectivity", CONNECTIVITIES),
        ],
    )
    def test_every_column_stays_inside_its_vocabulary(self, column: str, vocabulary: tuple[str, ...]) -> None:
        for cards, *_ in FLOP_CASES:
            assert classify_board(cards).row()[column] in vocabulary, cards

    def test_a_flop_always_sets_a_suit_structure_flag(self) -> None:
        """Which is what lets 0 mean "no flop" in ``Hands.texture``."""
        for cards, *_ in FLOP_CASES:
            if len(cards) == 3:
                assert classify_board(cards).textureMask & (bf.RAINBOW | bf.TWO_TONE | bf.MONOTONE)

    def test_an_empty_board_carries_no_flag(self) -> None:
        features = classify_board([])

        assert features.textureMask == 0
        assert features.row()["rankBucket"] == ""

    def test_connectivity_says_whether_a_straight_is_reachable(self) -> None:
        """Three board ranks inside one five-rank window is what it takes."""
        assert classify_board(["9d", "8c", "2h"]).connectivity == "disconnected"
        assert classify_board(["9d", "8c", "2h", "5s"]).connectivity == "semi-connected"
        assert classify_board(["9d", "8c", "7h"]).connectivity == "connected"
        # K-9-3 and Q-8-3 leave no window holding three of the board's ranks.
        for cards in (["Kh", "9h", "3c"], ["Qd", "8h", "3c"]):
            assert classify_board(cards).connectivity == "disconnected"

    def test_straight_possible_follows_the_connectivity_word(self) -> None:
        assert classify_board(["9d", "8c", "2h"]).straightPossible is False
        assert classify_board(["Ah", "2d", "3c"]).straightPossible is True
        assert classify_board(["Qd", "8h", "3c"]).straightPossible is False

    def test_the_label_reads_the_columns_back(self) -> None:
        assert describe(classify_board(["Ah", "7d", "2c"])) == "ace-high, rainbow, disconnected"
        assert describe(classify_board(["9d", "9c", "4h"])) == "middle, rainbow, disconnected, paired"
        assert describe(classify_board(["Qs", "Js", "8s"])) == "broadway, monotone, connected"


class TestDeterminism:
    def test_the_same_cards_classify_the_same_way_twice(self) -> None:
        cards = ["Kh", "9h", "3c", "Th"]

        assert classify_board(cards) == classify_board(cards)

    def test_the_order_the_cards_were_dealt_in_does_not_matter(self) -> None:
        """A board is a set of cards, not a sequence: the classification is order-free."""
        cards = ["Kh", "9h", "3c", "Th"]
        expected = classify_board(cards).row()

        assert classify_board(list(reversed(cards))).row() == expected
        assert classify_board(["Th", "3c", "Kh", "9h"]).row() == expected

    def test_the_label_is_stable_for_equal_boards(self) -> None:
        assert describe(classify_board(["9d", "9c", "4h"])) == describe(classify_board(["4h", "9d", "9c"]))


# ---------------------------------------------------------------------------
# Runouts
# ---------------------------------------------------------------------------
RUNOUT_CASES = [
    (["9d", "9c", "4h"], ["4s"], ("runout_paired_board",)),
    (["Kh", "9h", "3c"], ["2h"], ("runout_flush_completed", "runout_undercard")),
    (["Kh", "9h", "3c"], ["Ah"], ("runout_flush_completed", "runout_overcard")),
    (["Kh", "9h", "3c"], ["Th"], ("runout_flush_completed", "runout_straight_completed")),
    (["9d", "8c", "2h"], ["5s"], ("runout_straight_completed",)),
    # The eight on 7-6-5 joins a draw that was already live, so the street is
    # reported for the overcard it is and the live draw stays a state flag.
    (["7h", "6d", "5c"], ["8s"], ("runout_straight_completed", "runout_overcard")),
    (["Ah", "7d", "2c"], ["9h"], ("runout_brick",)),
    # A fourth heart is a flush card too: it is the board's flush deepening.
    (["Kh", "9h", "3c", "2h"], ["7h"], ("runout_flush_completed",)),
    # A-2-3-4-5 is a straight, so the deuce on A-9-4-2 opens the wheel draw.
    (["Ac", "9h", "4d"], ["2s"], ("runout_straight_completed", "runout_undercard")),
]


class TestRunout:
    @pytest.mark.parametrize(("previous", "added", "expected"), RUNOUT_CASES)
    def test_the_street_reports_what_it_changed(
        self, previous: list[str], added: list[str], expected: tuple[str, ...]
    ) -> None:
        features = classify_street(previous, added)

        assert set(flag_names(features.runoutMask)) == set(expected)
        assert features.cards == tuple(previous) + tuple(added)

    def test_a_brick_is_only_raised_when_nothing_else_is(self) -> None:
        for previous, added, expected in RUNOUT_CASES:
            features = classify_street(previous, added)
            if expected == ("runout_brick",):
                assert features.runoutMask == RUNOUT_BRICK
            else:
                assert not features.runoutMask & RUNOUT_BRICK, (previous, added)

    def test_the_flop_has_nothing_to_compare_against(self) -> None:
        assert classify_board(["Ah", "7d", "2c"]).runoutMask == 0
        assert classify_street([], ["Ah", "7d", "2c"]).runoutMask == 0

    def test_four_to_a_straight_needs_a_fourth_rank_in_the_window(self) -> None:
        three = classify_board(["9d", "8c", "7h"])
        four = classify_board(["9d", "8c", "7h", "6s"])

        assert three.textureMask & bf.CONNECTED
        assert not three.textureMask & bf.FOUR_STRAIGHT
        assert four.textureMask & bf.FOUR_STRAIGHT

    def test_the_card_that_deepens_the_board_s_flush_is_a_flush_card(self) -> None:
        """Three hearts already make a flush possible; the fourth deepens it."""
        deepened = classify_street(["Kh", "9h", "3h"], ["2h"])

        assert deepened.runoutMask & bf.RUNOUT_FLUSH_COMPLETED
        assert deepened.textureMask & bf.FOUR_FLUSH

    def test_a_card_off_the_draw_is_not_a_flush_card(self) -> None:
        off = classify_street(["Kh", "9h", "3h"], ["2s"])

        assert not off.runoutMask & bf.RUNOUT_FLUSH_COMPLETED
        assert not off.textureMask & bf.FOUR_FLUSH


# ---------------------------------------------------------------------------
# One source of truth with AutoNotes
# ---------------------------------------------------------------------------
class TestAutoNoteVocabulary:
    @pytest.mark.parametrize(
        ("cards", "expected"),
        [
            (["Ah", "7d", "2c"], ("dry", False)),
            (["Kh", "9h", "3c"], ("two-tone", True)),
            (["Qs", "Js", "8s"], ("monotone, connected", True)),
            (["9d", "9c", "4h"], ("paired", False)),
            (["7h", "6d", "5c"], ("connected", True)),
        ],
    )
    def test_the_autonote_dict_keeps_its_vocabulary(self, cards: list[str], expected: tuple[str, bool]) -> None:
        note = autonote_flop_texture(cards)

        assert note is not None
        assert (note["label"], note["wet"]) == expected
        assert note["board"] == " ".join(cards)

    def test_the_autonote_dict_refuses_a_board_short_of_a_flop(self) -> None:
        assert autonote_flop_texture(["Ah", "7d"]) is None
        assert autonote_flop_texture(["0x", "0x", "0x"]) is None

    @pytest.mark.parametrize(
        ("cards", "word"),
        [
            (["Ah", "7d", "2c"], "rainbow"),
            (["Kh", "9h", "3c"], "twotone"),
            (["Qs", "Js", "8s"], "monotone"),
            (["9d", "9c", "4h"], "paired"),
            ([], "dry"),
        ],
    )
    def test_the_custom_rule_word_keeps_its_vocabulary(self, cards: list[str], word: str) -> None:
        assert autonote_flop_texture_word(cards) == word

    def test_the_rule_engine_delegates_to_the_shared_classifier(self) -> None:
        """``_flop_texture`` reads a hand; it must not classify the flop itself."""

        class FlopHand:
            board = {"FLOP": ["Qs", "Js", "8s"]}

        assert _flop_texture(FlopHand()) == autonote_flop_texture(["Qs", "Js", "8s"])

    def test_the_custom_rule_field_delegates_to_the_shared_classifier(self) -> None:
        class BoardHand:
            board = {"FLOP": ["Ah", "7d", "2c"]}

        assert extract_field_value("board.flop_texture", BoardHand(), "Hero", None) == "rainbow"


# ---------------------------------------------------------------------------
# The hand walk
# ---------------------------------------------------------------------------
class FakeHand:
    """Just enough hand for the walk: a board, its streets, and the run count."""

    def __init__(self, board: dict[str, Any], streets: list[str], run_it_times: int = 1) -> None:
        self.board = board
        self.communityStreets = streets
        self.runItTimes = run_it_times
        self.handid = "1"


class TestHandWalk:
    def test_a_stud_hand_has_no_community_board(self) -> None:
        hand = FakeHand({"THIRD": [("Ah", "Kh")]}, [])

        assert derive_board_rows(hand) == []
        assert flop_texture_mask([]) == 0

    def test_a_preflop_only_hand_stores_nothing(self) -> None:
        hand = FakeHand({"FLOP": []}, ["FLOP", "TURN", "RIVER"])

        assert derive_board_rows(hand) == []

    def test_each_dealt_street_becomes_one_row_with_its_cards_cumulated(self) -> None:
        hand = FakeHand(
            {"FLOP": ["Ah", "7d", "2c"], "TURN": ["9h"], "RIVER": ["Ts"]},
            ["FLOP", "TURN", "RIVER"],
        )

        rows = derive_board_rows(hand)

        assert [(row["street"], row["streetName"], row["cardCount"]) for row in rows] == [
            (1, "flop", 3),
            (2, "turn", 4),
            (3, "river", 5),
        ]
        # 9h on A-7-2 changed nothing; Ts brought 7-9-T to a straight with two cards.
        assert rows[0]["runoutMask"] == 0
        assert rows[1]["runoutMask"] == bf.RUNOUT_BRICK
        assert rows[2]["runoutMask"] == bf.RUNOUT_STRAIGHT_COMPLETED
        assert list(rows[0]) == list(BOARD_FEATURE_COLUMNS)

    def test_a_hand_run_twice_carries_one_board_per_run(self) -> None:
        """The numbered streets belong to their own run, the shared flop to both."""
        hand = FakeHand(
            {
                "FLOP": ["Ah", "7d", "2c"],
                "TURN1": ["9h"],
                "RIVER1": ["Ts"],
                "TURN2": ["3d"],
                "RIVER2": ["5c"],
            },
            ["FLOP", "TURN", "RIVER"],
            run_it_times=2,
        )

        rows = derive_board_rows(hand)

        assert [(row["boardId"], row["streetName"], row["cardCount"]) for row in rows] == [
            (1, "flop", 3),
            (1, "turn", 4),
            (1, "river", 5),
            (2, "flop", 3),
            (2, "turn", 4),
            (2, "river", 5),
        ]
        # Both runs share the flop, so it classifies identically for each.
        assert {key: value for key, value in rows[0].items() if key != "boardId"} == {
            key: value for key, value in rows[3].items() if key != "boardId"
        }
        # Each run is classified on its own cards: a blank turn for the first, a
        # wheel draw for the second, and a straight card on both rivers.
        assert rows[1]["runoutMask"] == bf.RUNOUT_BRICK
        assert rows[4]["runoutMask"] & bf.RUNOUT_STRAIGHT_COMPLETED
        assert not rows[2]["runoutMask"] & bf.RUNOUT_BRICK
        assert not rows[5]["runoutMask"] & bf.RUNOUT_BRICK

    def test_the_legacy_texture_column_is_board_one_s_flop(self) -> None:
        hand = FakeHand(
            {"FLOP": ["Ah", "7d", "2c"], "TURN1": ["9h"], "TURN2": ["Kd"]},
            ["FLOP", "TURN", "RIVER"],
            run_it_times=2,
        )

        assert flop_texture_mask(derive_board_rows(hand)) == classify_board(["Ah", "7d", "2c"]).textureMask


# ---------------------------------------------------------------------------
# The stored shape
# ---------------------------------------------------------------------------
class TestPersistenceShape:
    def test_the_row_dict_has_exactly_the_stored_columns(self) -> None:
        features = classify_board(["Ah", "7d", "2c"])

        assert set(features.row()) == set(BOARD_FEATURE_COLUMNS) - {"boardId", "street", "streetName"}

    def test_every_column_has_a_default_of_the_right_type(self) -> None:
        assert set(BOARD_FEATURE_DEFAULTS) == set(BOARD_FEATURE_COLUMNS)

        for column, value in classify_board(["Ah", "7d", "2c"]).row().items():
            assert isinstance(value, type(BOARD_FEATURE_DEFAULTS[column])), column

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_create_table_declares_every_column_in_order(self, backend: str) -> None:
        ddl = hand_schema_queries(backend)["createBoardFeaturesTable"]

        assert ddl_columns(ddl) == ["id", "handId", *BOARD_FEATURE_COLUMNS]

    def test_store_query_columns_match_the_vocabulary(self) -> None:
        query = import_auxiliary_queries()["store_board_features"]

        assert sql_columns(query) == ["handId", *BOARD_FEATURE_COLUMNS]
        assert query.count("%s") == len(BOARD_FEATURE_COLUMNS) + 1

    def test_store_query_executes_on_sqlite(self) -> None:
        """Column and placeholder counts agreeing is not enough: it has to run."""
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(hand_schema_queries("sqlite")["createBoardFeaturesTable"])
            query = import_auxiliary_queries()["store_board_features"].replace("%s", "?")
            conn.execute(query, [1, *BOARD_FEATURE_DEFAULTS.values()])

            assert conn.execute("SELECT COUNT(*) FROM BoardFeatures").fetchone()[0] == 1

    def test_the_bulk_store_fills_a_partial_row(self, fresh_db: Database) -> None:
        """A producer that only knows some columns still writes a complete row."""
        fresh_db.storeBoardFeatures(1, [{"cardCount": 3, "textureMask": 5}], True)

        row = (
            fresh_db.get_cursor()
            .execute(f"SELECT {', '.join(BOARD_FEATURE_COLUMNS)} FROM BoardFeatures")
            .fetchone()
        )

        assert dict(zip(BOARD_FEATURE_COLUMNS, row)) == {
            **BOARD_FEATURE_DEFAULTS,
            "cardCount": 3,
            "textureMask": 5,
        }


class TestSchemaMigration:
    """An existing database gains the table on its next connection."""

    @staticmethod
    def _database_without_the_table(fresh_db: Database) -> Database:
        """Stand in for a database created before #295."""
        fresh_db.get_cursor().execute("DROP TABLE BoardFeatures")
        fresh_db.commit()
        return fresh_db

    def test_an_older_database_gains_the_table_and_its_indexes(self, fresh_db: Database) -> None:
        db = self._database_without_the_table(fresh_db)

        db.ensure_feature_tables()

        names = {row[0] for row in db.get_cursor().execute("SELECT name FROM sqlite_master")}
        assert "BoardFeatures" in names
        assert {"boardfeatures_hand_idx", "boardfeatures_texture_idx"} <= names

    def test_the_migrated_table_matches_a_fresh_one(self, fresh_db: Database) -> None:
        db = self._database_without_the_table(fresh_db)
        db.ensure_feature_tables()

        migrated = {row[1] for row in db.get_cursor().execute("PRAGMA table_info(BoardFeatures)")}
        with closing(sqlite3.connect(":memory:")) as fresh:
            fresh.execute(hand_schema_queries("sqlite")["createBoardFeaturesTable"])
            created = {row[1] for row in fresh.execute("PRAGMA table_info(BoardFeatures)")}

        assert migrated == created

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_the_indexes_are_declared_for_every_backend(self, backend: str) -> None:
        catalogue = Sql(db_server=backend).query

        assert "boardfeatures_hand_idx" in catalogue["addBoardFeaturesHandIndex"]
        assert "boardfeatures_texture_idx" in catalogue["addBoardFeaturesTextureIndex"]


# ---------------------------------------------------------------------------
# The same rows, out of the database, for the whole corpus
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> golden.GoldenCorpus:
    return golden.import_golden_corpus(tmp_path_factory.mktemp("board-features"))


@pytest.fixture(scope="module")
def parsed_hands(tmp_path_factory) -> dict[str, list]:
    config = golden.build_config(tmp_path_factory.mktemp("board-parse"))
    return {path.name: golden.parse_golden_file(config, path) for path in golden.golden_files()}


class TestCorpusRows:
    def test_every_stored_row_is_readable_and_classified(self, corpus: golden.GoldenCorpus) -> None:
        for hand_id, rows in corpus.boards.items():
            for row in rows:
                assert row["streetName"] in ("flop", "turn", "river"), row
                assert row["textureMask"] != 0, row
                assert row["cardCount"] in (3, 4, 5), row
                assert row["suitStructure"] in SUIT_STRUCTURES, row

    def test_every_row_is_the_classification_of_the_cards_the_hand_dealt(
        self, corpus: golden.GoldenCorpus, parsed_hands: dict[str, list]
    ) -> None:
        """Classify the parsed cards again and compare, street by street.

        The stored row is not trusted to witness its own correctness: the cards
        come from a hand parsed without a database, and the classification is
        recomputed for the same street.
        """
        by_file = {scenario.file: scenario for scenario in corpus.manifest.scenarios}
        checked = 0
        for name, hands in parsed_hands.items():
            assert name in by_file
            for hand in hands:
                previous: list[str] = []
                for position, dealt in rows_by_street(hand):
                    expected = classify_street(previous, dealt)
                    stored = corpus.board_rows(int(hand.handid), street=position)

                    assert len(stored) == 1, (name, hand.handid, position)
                    assert stored[0]["textureMask"] == expected.textureMask, (name, hand.handid, position)
                    assert stored[0]["runoutMask"] == expected.runoutMask, (name, hand.handid, position)
                    assert stored[0]["cardCount"] == len(expected.cards), (name, hand.handid, position)
                    previous = list(expected.cards)
                    checked += 1
        assert checked == sum(len(rows) for rows in corpus.boards.values())

    def test_the_flop_mask_is_stored_on_the_hand_row_as_well(self, corpus: golden.GoldenCorpus) -> None:
        for hand_id, hand in corpus.hands.items():
            flop = corpus.board_rows(hand_id, street=1)

            assert int(hand["texture"]) == (int(flop[0]["textureMask"]) if flop else 0), hand_id

    def test_no_hand_stores_a_board_street_twice(self, corpus: golden.GoldenCorpus) -> None:
        for hand_id, rows in corpus.boards.items():
            streets = [(row["boardId"], row["street"]) for row in rows]

            assert len(set(streets)) == len(streets), hand_id

    def test_the_last_row_carries_the_whole_board(self, corpus: golden.GoldenCorpus) -> None:
        """A hand that reached the river stores five cards on its last row."""
        for scenario in corpus.manifest.scenarios:
            for hand in scenario.hands:
                declared = sum(len(hand.board[street]) for street in golden.BOARD_KEYS)
                rows = corpus.boards[hand.hand_id]

                assert not rows or rows[-1]["cardCount"] == declared, hand.hand_id
