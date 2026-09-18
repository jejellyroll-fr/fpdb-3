"""The normalized action-event model of issue #293.

``HandsActions`` used to carry the parser's own view of an action -- who, what,
how much -- and nothing about the decision: no pot, no price, no position, no
effective stack, no notion of what was being faced. Those are exactly the terms
the analytics layers above it (situations, filters, sizing, EV, research) need
to compose, so this module checks they are really there, on the golden corpus
of #308, and that the three places which have to agree about the new columns do:

* ``action_events.ACTION_EVENT_COLUMNS`` -- the vocabulary,
* ``sql_schema_hand.createHandsActionsTable`` -- the fresh-schema DDL, and
* ``store_hands_actions`` plus ``DatabaseBulkImportMixin.storeHandsActions``
  -- the insert, which must also match a database upgraded in place.

The semantic checks read the rows back out of a real SQLite database after a
real import, and cross-check the pot arithmetic against an independent reading
of the hand history text (the uncalled bet the file says was returned).
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

import fpdb_3_legacy.Database as Database
import fpdb_3_legacy.SQL as SQL
from fpdb_3_legacy.action_events import (
    ACTION_EVENT_COLUMNS,
    ACTION_EVENT_DEFAULTS,
    action_chips,
    derive_action_events,
    round_order,
)
from fpdb_3_legacy.database_schema import HANDS_ACTIONS_EVENT_DEFINITIONS
from fpdb_3_legacy.sql_schema_hand import hand_schema_queries
from tests.helpers import analytics_golden as golden

MANIFEST = golden.load_manifest()
SCENARIOS = {scenario.id: scenario for scenario in MANIFEST.scenarios}

# Streets, as the pipeline numbers them.
BLINDS, PREFLOP, FLOP, TURN, RIVER = -1, 0, 1, 2, 3

# Columns of the original HandsActions table, which the event columns follow.
ORIGINAL_ACTION_COLUMNS = (
    "handId",
    "playerId",
    "street",
    "actionNo",
    "streetActionNo",
    "actionId",
    "amount",
    "raiseTo",
    "amountCalled",
    "numDiscarded",
    "cardsDiscarded",
    "allIn",
)

# Where each street's own aggregate sizing column lives in HandsPlayers.
BET_MADE_BP_COLUMN = {FLOP: "val_f_bet_made_bp", TURN: "val_t_bet_made_bp", RIVER: "val_r_bet_made_bp"}
RAISE_MADE_BP_COLUMN = {
    PREFLOP: "val_p_raise_made_bp",
    FLOP: "val_f_raise_made_bp",
    TURN: "val_t_raise_made_bp",
    RIVER: "val_r_raise_made_bp",
}


def sql_columns(sql_text: str) -> list[str]:
    """The column names of an insert statement, in order."""
    block = re.search(r"\((.*?)\)\s*values", sql_text, re.IGNORECASE | re.DOTALL)
    assert block is not None
    return [column.strip() for column in block.group(1).split(",") if column.strip()]


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> golden.GoldenCorpus:
    """Import the whole golden corpus once, into a throwaway SQLite database."""
    return golden.import_golden_corpus(tmp_path_factory.mktemp("action-events"))


def hand_events(corpus: golden.GoldenCorpus, scenario_id: str, hand_index: int = 0) -> list[dict]:
    """The stored events of one scenario hand, in action order."""
    hand = SCENARIOS[scenario_id].hands[hand_index]
    return corpus.actions[hand.hand_id]


def event(corpus: golden.GoldenCorpus, scenario_id: str, action_no: int, hand_index: int = 0) -> dict:
    """One stored event, by its action number within the hand."""
    rows = hand_events(corpus, scenario_id, hand_index)
    return next(row for row in rows if row["actionNo"] == action_no)


class TestRoundOrder:
    """Who acts before whom, per betting round (Codex review of #293)."""

    HEADS_UP = {"Button": {"position": "S"}, "Blind": {"position": "B"}}
    THREE_HANDED = {"S": {"position": "S"}, "B": {"position": "B"}, "Btn": {"position": 0}}

    def test_heads_up_blind_acts_first_preflop_and_last_postflop(self) -> None:
        # Heads-up rules: the button is also the small blind. He opens the
        # preflop round and acts last from the flop on -- the opposite of a
        # full table, where the blinds both act first postflop.
        preflop = round_order(self.HEADS_UP, preflop=True)
        postflop = round_order(self.HEADS_UP, preflop=False)
        assert preflop["Button"] < preflop["Blind"]
        assert postflop["Blind"] < postflop["Button"]

    def test_full_table_blinds_still_act_first_postflop(self) -> None:
        postflop = round_order(self.THREE_HANDED, preflop=False)
        assert postflop["S"] < postflop["B"] < postflop["Btn"]

    def test_draw_blinds_carry_across_the_deal_boundary(self) -> None:
        """Draw games open their action on DEAL, not PREFLOP: the blinds stay
        the price of that round instead of a restart at toCall = 0."""
        from decimal import Decimal
        from types import SimpleNamespace

        def _action(name, word, amount=0):
            return [name, word, amount, 0, 0]

        players = {
            "Hero": {"position": "S", "startCash": 2000000},
            "Villain": {"position": "B", "startCash": 2000000},
        }
        hand = SimpleNamespace(
            actionStreets=["BLINDSANTES", "DEAL", "DRAWONE"],
            gametype={"bb": "2.00"},
            pot=SimpleNamespace(stp=0),
            actions={
                "BLINDSANTES": [_action("Hero", "small blind", Decimal("1.00")), _action("Villain", "big blind", Decimal("2.00"))],
                "DEAL": [_action("Hero", "calls", Decimal("2.00"))],
                "DRAWONE": [_action("Villain", "checks"), _action("Hero", "checks")],
            },
        )
        events = derive_action_events(hand, players)
        call = events[3]
        assert call["toCall"] == 100, "the small blind completes to the big blind"
        assert call["facingActionType"] is None, "a blind is a price, not a bet faced"


class TestEventVocabulary:
    """The column list, the DDL, the migration and the insert must all agree."""

    def test_every_column_has_a_default(self) -> None:
        assert set(ACTION_EVENT_DEFAULTS) == set(ACTION_EVENT_COLUMNS)

    def test_every_column_has_an_upgrade_definition(self) -> None:
        """A database predating the event model must gain every event column."""
        assert list(HANDS_ACTIONS_EVENT_DEFINITIONS) == list(ACTION_EVENT_COLUMNS)

    @pytest.mark.parametrize("backend", ["mysql", "postgresql", "sqlite"])
    def test_create_table_declares_the_event_columns(self, backend: str) -> None:
        ddl = hand_schema_queries(backend)["createHandsActionsTable"]
        for column in ACTION_EVENT_COLUMNS:
            assert re.search(rf"\b{column}\b", ddl), f"{column} missing from the {backend} DDL"

    def test_store_query_columns_match_the_vocabulary(self) -> None:
        """store_hands_actions appends the event columns after the original ones."""
        query = SQL.Sql(db_server="sqlite").query["store_hands_actions"]
        assert sql_columns(query) == list(ORIGINAL_ACTION_COLUMNS) + list(ACTION_EVENT_COLUMNS)
        placeholders = query.count("?") + query.count("%s")
        assert placeholders == len(ORIGINAL_ACTION_COLUMNS) + len(ACTION_EVENT_COLUMNS)

    def test_store_query_executes_on_sqlite(self) -> None:
        """Column/placeholder alignment is not enough: the statement must run."""
        query = SQL.Sql(db_server="sqlite").query
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(query["createHandsActionsTable"])
            values = [0] * (len(ORIGINAL_ACTION_COLUMNS) + len(ACTION_EVENT_COLUMNS))
            conn.execute(query["store_hands_actions"], values)
            assert conn.execute("SELECT COUNT(*) FROM HandsActions").fetchone()[0] == 1

    def test_action_chips_follows_the_parser_tuple(self) -> None:
        """A raise carries the raise-by amount and the call it made."""
        assert action_chips(("Anna", "raises", Decimal("3.00"), Decimal("5.00"), Decimal("2.00"), False)) == 500
        assert action_chips(("Anna", "bets", Decimal("17.00"), False)) == 1700
        assert action_chips(("Anna", "calls", Decimal("11.00"), False)) == 1100
        assert action_chips(("Anna", "folds")) == 0
        assert action_chips(("Anna", "checks")) == 0


class TestSchemaMigration:
    """An existing database gains the event columns rather than being rebuilt."""

    @staticmethod
    def _legacy_database() -> tuple[sqlite3.Connection, Database.Database]:
        """A SQLite connection holding HandsActions as it was before #293."""
        conn = sqlite3.connect(":memory:")
        columns = ", ".join(f"{column} INT" for column in ORIGINAL_ACTION_COLUMNS)
        conn.execute(f"CREATE TABLE HandsActions (id INTEGER PRIMARY KEY, {columns})")
        db = Database.Database.__new__(Database.Database)
        db.backend = Database.Database.SQLITE
        db.connection = conn
        db._in_transaction = 0
        return conn, db

    def test_ensure_handsactions_columns_repairs_an_old_schema(self) -> None:
        conn, db = self._legacy_database()
        with closing(conn):
            db.ensure_handsactions_columns()
            columns = [row[1] for row in conn.execute("PRAGMA table_info(HandsActions)")]
        assert columns[: len(ORIGINAL_ACTION_COLUMNS) + 1] == ["id", *ORIGINAL_ACTION_COLUMNS]
        for column in ACTION_EVENT_COLUMNS:
            assert column in columns

    def test_migrated_table_matches_a_fresh_one(self) -> None:
        """Upgrading in place has to leave the same columns as creating anew."""
        fresh = SQL.Sql(db_server="sqlite").query["createHandsActionsTable"]
        with closing(sqlite3.connect(":memory:")) as fresh_conn:
            fresh_conn.execute(fresh)
            fresh_columns = {row[1] for row in fresh_conn.execute("PRAGMA table_info(HandsActions)")}

        conn, db = self._legacy_database()
        with closing(conn):
            db.ensure_handsactions_columns()
            migrated_columns = {row[1] for row in conn.execute("PRAGMA table_info(HandsActions)")}
        assert migrated_columns == fresh_columns

    def test_old_action_rows_keep_their_columns(self) -> None:
        """The upgrade is additive: a row written before it still reads back."""
        conn, db = self._legacy_database()
        with closing(conn):
            conn.execute("INSERT INTO HandsActions (handId, playerId, actionNo) VALUES (1, 2, 3)")
            db.ensure_handsactions_columns()
            row = conn.execute("SELECT handId, playerId, actionNo, actionType FROM HandsActions").fetchone()
        assert row == (1, 2, 3, None)


class TestCorpusEvents:
    """Every golden hand converts to events that are ordered, complete and exact."""

    def test_every_hand_has_events(self, corpus: golden.GoldenCorpus) -> None:
        assert corpus.hand_count == 30
        for hand_id, rows in corpus.actions.items():
            assert rows, f"hand {hand_id} produced no action events"

    def test_action_numbers_are_dense_and_ordered(self, corpus: golden.GoldenCorpus) -> None:
        """The sequence is the parser's, with nothing dropped or reordered."""
        for hand_id, rows in corpus.actions.items():
            assert [row["actionNo"] for row in rows] == list(range(1, len(rows) + 1)), hand_id

    def test_street_action_numbers_restart_with_each_street(self, corpus: golden.GoldenCorpus) -> None:
        for hand_id, rows in corpus.actions.items():
            seen: dict[int, int] = {}
            for row in rows:
                seen[row["street"]] = seen.get(row["street"], 0) + 1
                assert row["streetActionNo"] == seen[row["street"]], hand_id

    def test_action_types_are_non_null(self, corpus: golden.GoldenCorpus) -> None:
        for hand_id, rows in corpus.actions.items():
            for row in rows:
                assert row["actionType"], f"hand {hand_id} action {row['actionNo']} has no action type"

    def test_pot_runs_continuously(self, corpus: golden.GoldenCorpus) -> None:
        """Each action starts from the pot the previous one ended with."""
        for hand_id, rows in corpus.actions.items():
            previous = 0
            for row in rows:
                assert row["potBefore"] == previous, f"hand {hand_id} action {row['actionNo']}"
                previous = row["potAfter"]

    def test_pot_grows_by_what_the_action_put_in(self, corpus: golden.GoldenCorpus) -> None:
        for hand_id, rows in corpus.actions.items():
            for row in rows:
                expected = row["amount"] + (row["amountCalled"] if row["actionType"] in ("raises", "completes") else 0)
                assert row["potAfter"] - row["potBefore"] == expected, f"hand {hand_id} action {row['actionNo']}"

    def test_deepest_pot_is_the_final_pot_plus_the_uncalled_bet(self, corpus: golden.GoldenCorpus) -> None:
        """Cross-checked against the hand history text, not against DerivedStats."""
        for scenario in MANIFEST.scenarios:
            returned = golden.returned_uncalled_cents(golden.scenario_file(scenario))
            for hand in scenario.hands:
                rows = corpus.actions[hand.hand_id]
                deepest = max(row["potAfter"] for row in rows)
                assert deepest - hand.pot_cents == returned[hand.hand_id], hand.hand_id

    def test_first_action_starts_from_an_empty_pot(self, corpus: golden.GoldenCorpus) -> None:
        """The corpus is rake-free and bomb-pot-free, so nothing seeds the pot."""
        for hand_id, rows in corpus.actions.items():
            assert rows[0]["potBefore"] == 0, hand_id

    def test_folders_leave_the_hand(self, corpus: golden.GoldenCorpus) -> None:
        """playersInHand only ever drops, and only when somebody folded."""
        for hand_id, rows in corpus.actions.items():
            assert rows[0]["playersInHand"] >= 1
            for before, after in zip(rows, rows[1:]):
                if after["playersInHand"] != before["playersInHand"]:
                    assert before["actionType"] == "folds", hand_id

    def test_the_folding_player_is_still_counted_at_their_own_decision(self, corpus: golden.GoldenCorpus) -> None:
        small = event(corpus, "rfi_open", 1)
        assert small["playersInHand"] == 6
        first_fold = event(corpus, "rfi_open", 3)
        assert first_fold["actionType"] == "folds" and first_fold["playersInHand"] == 6
        assert event(corpus, "rfi_open", 4)["playersInHand"] == 5

    def test_position_is_the_player_row_position(self, corpus: golden.GoldenCorpus) -> None:
        """The event's position agrees with the HandsPlayers row it belongs to."""
        for hand_id, rows in corpus.actions.items():
            for row in rows:
                stored = str(corpus.player_row(hand_id, row["playerName"])["position"])
                expected = {"S": -1, "B": -2}[stored] if stored in ("S", "B") else int(stored)
                assert row["position"] == expected, f"hand {hand_id} action {row['actionNo']}"

    def test_in_position_means_nobody_acts_behind(self, corpus: golden.GoldenCorpus) -> None:
        for hand_id, rows in corpus.actions.items():
            for row in rows:
                assert row["inPosition"] == (row["relativePosition"] == 0), hand_id

    def test_sizing_matches_the_aggregate_bet_made(self, corpus: golden.GoldenCorpus) -> None:
        """A bet's sizing is the column the HUD already averages, to the point."""
        for hand_id, rows in corpus.actions.items():
            for row in rows:
                if row["actionType"] != "bets":
                    continue
                column = BET_MADE_BP_COLUMN.get(row["street"])
                if column is None or not corpus.player_row(hand_id, row["playerName"])[column]:
                    continue
                assert row["sizingBp"] == corpus.player_row(hand_id, row["playerName"])[column]

    def test_sizing_matches_the_aggregate_raise_made(self, corpus: golden.GoldenCorpus) -> None:
        """A raise's sizing is the first-raise column, which is the same convention."""
        for hand_id, rows in corpus.actions.items():
            seen: set[tuple[str, int]] = set()
            for row in rows:
                if row["actionType"] not in ("raises", "completes"):
                    continue
                column = RAISE_MADE_BP_COLUMN.get(row["street"])
                key = (row["playerName"], row["street"])
                if column is None or key in seen:
                    continue
                seen.add(key)
                stored = corpus.player_row(hand_id, row["playerName"])[column]
                if stored:
                    assert row["sizingBp"] == stored, f"hand {hand_id} action {row['actionNo']}"

    def test_effective_stack_never_exceeds_a_still_covering_opponent(self, corpus: golden.GoldenCorpus) -> None:
        """Effective stack is playable money: it cannot be more than the table has."""
        for hand_id, rows in corpus.actions.items():
            stacks = [player["startCash"] for player in corpus.players[hand_id].values()]
            deepest = max(stacks)
            for row in rows:
                own = corpus.player_row(hand_id, row["playerName"])["startCash"]
                assert 0 <= row["effectiveStack"] <= min(own, deepest)
            assert rows[0]["effectiveStack"] == min(
                corpus.player_row(hand_id, rows[0]["playerName"])["startCash"],
                *[player["startCash"] for name, player in corpus.players[hand_id].items() if name != rows[0]["playerName"]],
            ), hand_id

    def test_street_entry_spr_matches_the_aggregate_column(self, corpus: golden.GoldenCorpus) -> None:
        """calcStreetSPR and the events share one formula, so they must agree."""
        spr_columns = {FLOP: ("cnt_f_spr", "val_f_spr"), TURN: ("cnt_t_spr", "val_t_spr"), RIVER: ("cnt_r_spr", "val_r_spr")}
        for hand_id, rows in corpus.actions.items():
            for street, (count_column, value_column) in spr_columns.items():
                first = next((row for row in rows if row["street"] == street), None)
                if first is None:
                    continue
                player = corpus.player_row(hand_id, first["playerName"])
                if not player[count_column]:
                    continue
                assert first["sprBefore"] == player[value_column], f"hand {hand_id} street {street}"


class TestPreflopSemantics:
    """Open, call, limp, over-limp, 3-bet, squeeze, 4-bet and 5-bet."""

    def test_open_raise_pays_the_big_blind(self, corpus: golden.GoldenCorpus) -> None:
        """Boris opens the unopened pot for 2.5bb over the blind."""
        opener = event(corpus, "rfi_open", 5)
        assert opener["playerName"] == "Boris"
        assert opener["actionType"] == "raises"
        assert opener["toCall"] == 200, "an opener still owes the big blind"
        assert opener["facingActionType"] is None, "the blind is a price, not a bet faced"
        assert opener["raiserCount"] == 0 and opener["callerCount"] == 0
        assert opener["potBefore"] == 300 and opener["potAfter"] == 800
        assert opener["sizingBp"] == 16666, "raise-to / pot before, the aggregate convention"
        assert opener["isAggressor"]

    def test_the_blinds_are_posted_before_the_round_and_are_not_bets(self, corpus: golden.GoldenCorpus) -> None:
        small, big = event(corpus, "rfi_open", 1), event(corpus, "rfi_open", 2)
        assert (small["actionType"], small["toCall"], small["potBefore"]) == ("small blind", 0, 0)
        assert (big["actionType"], big["toCall"], big["sizingBp"]) == ("big blind", 0, 0)
        assert big["potAfter"] == small["potAfter"] + 200
        assert not small["isAggressor"] and not big["isAggressor"]

    def test_folders_pay_the_price_they_declined(self, corpus: golden.GoldenCorpus) -> None:
        """The big blind folds for 300 because it already has 200 in."""
        folder = event(corpus, "rfi_open", 8)
        assert (folder["playerName"], folder["actionType"]) == ("Erin", "folds")
        assert folder["toCall"] == 300
        assert folder["facingActionType"] == "raises"
        assert folder["facingAmount"] == 300
        assert folder["facingSizingBp"] == 16666
        assert folder["potAfter"] == folder["potBefore"], "a fold adds nothing to the pot"

    def test_limp_versus_over_limp_is_the_caller_count(self, corpus: golden.GoldenCorpus) -> None:
        """#308 could not tell an open limp from an over-limp; the event can."""
        first_limper, over_limper = event(corpus, "limp_iso", 3), event(corpus, "limp_iso", 4)
        assert (first_limper["actionType"], first_limper["raiserCount"], first_limper["callerCount"]) == ("calls", 0, 0)
        assert (over_limper["actionType"], over_limper["raiserCount"], over_limper["callerCount"]) == ("calls", 0, 1)
        assert over_limper["toCall"] == 200, "limping behind a limper is still the big blind"

    def test_isolation_raise_sees_the_limpers(self, corpus: golden.GoldenCorpus) -> None:
        isolation = event(corpus, "limp_iso", 5)
        assert isolation["callerCount"] == 2, "the isolate is a raise over two limpers"
        assert isolation["raiserCount"] == 0, "an unraised pot, so this is the first raise"
        assert isolation["potBefore"] == 700 and isolation["potAfter"] == 1800
        assert isolation["sizingBp"] == 15714
        assert isolation["toCall"] == 200

    def test_three_bet_faces_the_open(self, corpus: golden.GoldenCorpus) -> None:
        three_bet = event(corpus, "open_3bet", 5)
        assert (three_bet["actionType"], three_bet["raiserCount"], three_bet["callerCount"]) == ("raises", 1, 0)
        assert three_bet["facingActionType"] == "raises"
        assert three_bet["facingAmount"] == 500
        assert three_bet["toCall"] == 500, "the 3-bettor owes the whole open"
        assert three_bet["potBefore"] == 800 and three_bet["sizingBp"] == 20000
        assert three_bet["isAggressor"]

    def test_four_bet_then_five_bet_all_in(self, corpus: golden.GoldenCorpus) -> None:
        four_bet = event(corpus, "four_bet_five_bet_allin", 9)
        assert four_bet["raiserCount"] == 2, "two raises behind the blinds: open, 3-bet"
        assert four_bet["facingAmount"] == 1100
        assert four_bet["potBefore"] == 2400 and four_bet["sizingBp"] == 16666
        assert four_bet["allIn"] == 0

        five_bet = event(corpus, "four_bet_five_bet_allin", 10)
        assert five_bet["allIn"] == 1
        assert five_bet["raiserCount"] == 3
        assert five_bet["facingAmount"] == 2400
        assert five_bet["potAfter"] == 24300, "the whole 100bb stack is in the pot"
        assert five_bet["effectiveStack"] == 16000, "what the shover had behind"

    def test_squeeze_faces_a_raise_with_a_caller_behind(self, corpus: golden.GoldenCorpus) -> None:
        squeeze = event(corpus, "squeeze", 5)
        assert squeeze["raiserCount"] == 1 and squeeze["callerCount"] == 1
        assert squeeze["facingActionType"] == "raises" and squeeze["facingAmount"] == 500
        assert squeeze["potBefore"] == 1300 and squeeze["sizingBp"] == 16923
        assert squeeze["playersInHand"] == 6

    def test_position_is_the_seat_order_not_who_happened_to_act_last(self, corpus: golden.GoldenCorpus) -> None:
        """Preflop the big blind is last, so nobody acts behind it.

        The cutoff opener has the button, the small blind and the big blind
        still behind them, whoever folds in between.
        """
        opener = event(corpus, "rfi_open", 5)
        assert (opener["position"], opener["relativePosition"], opener["inPosition"]) == (1, 3, False)
        big_blind_fold = event(corpus, "rfi_open", 8)
        assert (big_blind_fold["position"], big_blind_fold["relativePosition"]) == (-2, 0)
        assert big_blind_fold["inPosition"], "nobody acts after the big blind preflop"

    def test_postflop_position_follows_the_button(self, corpus: golden.GoldenCorpus) -> None:
        """Postflop the small blind, then the big blind, then away from the button.

        Scenario 07 is a hijack open and a cutoff call, so the aggressor is the
        one out of position and the caller is the one in position -- which is
        what the seat order says, whichever of them acts last on a street.
        """
        cbet, fold = event(corpus, "srp_cbet", 9), event(corpus, "srp_cbet", 10)
        assert (cbet["playerName"], cbet["position"], cbet["inPosition"]) == ("Anna", 2, False)
        assert (fold["playerName"], fold["position"], fold["inPosition"]) == ("Boris", 1, True)
        assert cbet["relativePosition"] == 1 and fold["relativePosition"] == 0

    def test_an_all_in_player_is_not_behind_anyone(self, corpus: golden.GoldenCorpus) -> None:
        """The cutoff shoves last: the early raiser has them behind, they have nobody."""
        four_bet, shove = event(corpus, "four_bet_five_bet_allin", 9), event(corpus, "four_bet_five_bet_allin", 10)
        assert four_bet["relativePosition"] == 1, "the cutoff still had to act"
        assert shove["allIn"] and shove["relativePosition"] == 0


class TestPostflopSemantics:
    """C-bet, check-raise, probe, barrel and river bet."""

    def test_cbet_faces_the_pot_it_was_checked_to(self, corpus: golden.GoldenCorpus) -> None:
        cbet = event(corpus, "srp_cbet", 9)
        assert cbet["playerName"] == "Anna" and cbet["street"] == FLOP
        assert cbet["actionType"] == "bets" and cbet["isAggressor"]
        assert cbet["toCall"] == 0, "the flop was checked to the aggressor"
        assert cbet["potBefore"] == 1300 and cbet["potAfter"] == 2000
        assert cbet["sizingBp"] == 5384, "700 into 1300"
        assert cbet["callerCount"] == 0 and cbet["raiserCount"] == 0

    def test_folding_to_the_cbet_pays_the_price(self, corpus: golden.GoldenCorpus) -> None:
        fold = event(corpus, "srp_cbet", 10)
        assert fold["actionType"] == "folds"
        assert fold["toCall"] == 700 and fold["facingActionType"] == "bets"
        assert fold["facingSizingBp"] == 5384, "the size of the bet that was folded to"

    def test_check_raise_faces_the_bet(self, corpus: golden.GoldenCorpus) -> None:
        bet, check_raise = event(corpus, "check_raise", 10), event(corpus, "check_raise", 11)
        assert (bet["playerName"], bet["actionType"]) == ("Cara", "bets")
        assert check_raise["actionType"] == "raises" and check_raise["raiserCount"] == 1
        assert check_raise["facingActionType"] == "bets"
        assert check_raise["facingAmount"] == 700, "the bet it raised"
        assert check_raise["toCall"] == 700
        assert check_raise["potBefore"] == 2000 and check_raise["sizingBp"] == 10500

    def test_check_raise_then_fold_pays_the_re_raise(self, corpus: golden.GoldenCorpus) -> None:
        fold = event(corpus, "check_raise", 12)
        assert fold["actionType"] == "folds"
        assert fold["toCall"] == 1400, "2100 to make minus the 700 already in"
        assert fold["facingActionType"] == "raises" and fold["facingSizingBp"] == 10500

    def test_turn_probe_opens_the_betting_after_a_checked_flop(self, corpus: golden.GoldenCorpus) -> None:
        flop_check, probe = event(corpus, "turn_probe", 10), event(corpus, "turn_probe", 12)
        assert (flop_check["playerName"], flop_check["actionType"], flop_check["street"]) == ("Boris", "checks", FLOP)
        assert probe["street"] == TURN and probe["actionType"] == "bets"
        assert probe["raiserCount"] == 0, "nobody had bet the turn"
        assert probe["potBefore"] == 1300 and probe["sizingBp"] == 5384
        assert not flop_check["isAggressor"]

    def test_turn_barrel_scales_to_the_growing_pot(self, corpus: golden.GoldenCorpus) -> None:
        flop_bet, turn_barrel = event(corpus, "turn_barrel", 9), event(corpus, "turn_barrel", 11)
        assert (flop_bet["street"], flop_bet["sizingBp"]) == (FLOP, 5384)
        assert (turn_barrel["street"], turn_barrel["sizingBp"]) == (TURN, 6666)
        assert turn_barrel["potBefore"] == 2700 and turn_barrel["potAfter"] == 4500
        assert turn_barrel["isAggressor"] and turn_barrel["raiserCount"] == 0, "a bet, not a raise"

    def test_river_barrel_is_priced_off_the_turn_pot(self, corpus: golden.GoldenCorpus) -> None:
        river_bet = event(corpus, "river_barrel", 13)
        assert (river_bet["street"], river_bet["playerName"]) == (RIVER, "Boris")
        assert river_bet["potBefore"] == 6300 and river_bet["potAfter"] == 10300
        assert river_bet["sizingBp"] == 6349
        assert river_bet["toCall"] == 0 and river_bet["callerCount"] == 0

    def test_all_in_before_the_river_leaves_nothing_behind(self, corpus: golden.GoldenCorpus) -> None:
        shove, call = event(corpus, "allin_before_river", 10), event(corpus, "allin_before_river", 11)
        assert shove["allIn"] == 1 and shove["sizingBp"] == 52571
        assert shove["potBefore"] == 3500 and shove["potAfter"] == 21900
        assert call["toCall"] == 18400
        assert call["effectiveStack"] == 0, "the only opponent left has no chips behind"
        assert call["allIn"] == 1

    def test_multiway_counts_the_players_in_the_hand(self, corpus: golden.GoldenCorpus) -> None:
        three_way_bet = event(corpus, "multiway", 9)
        assert three_way_bet["street"] == FLOP and three_way_bet["playersInHand"] == 3
        assert three_way_bet["callerCount"] == 0 and three_way_bet["raiserCount"] == 0
        assert three_way_bet["sizingBp"] == 5000, "900 into 1800"
        first_caller, second_caller = event(corpus, "multiway", 10), event(corpus, "multiway", 11)
        assert first_caller["callerCount"] == 0 and second_caller["actionType"] == "folds"
        assert second_caller["facingAmount"] == 900

    def test_postflop_sizing_tracks_the_bet_as_a_share_of_the_pot(self, corpus: golden.GoldenCorpus) -> None:
        """Scenario 17 varies one thing: the flop bet, over a constant 1300 pot.

        These are the numbers #296 will bucket, so they are pinned here: the
        column has to be the bet as a share of the pot it faced, every time.
        """
        sizes = [event(corpus, "bet_sizing", 9, hand_index=index)["sizingBp"] for index in range(10)]
        assert sizes == [2307, 3076, 3846, 4615, 6153, 7692, 9230, 12307, 13846, 15384]
        assert sizes == sorted(sizes), "one dimension, ten sizes"


class TestDerivedContextEdges:
    """Cases the golden corpus does not contain, on hand-built action streams.

    Amounts are written the way a parser writes them, in chips, and the events
    are read in cents -- the same conversion every amount column goes through.
    """

    @staticmethod
    def _hand(streets, actions, bb="2.00", stp=0):
        return SimpleNamespace(actionStreets=streets, actions=actions, gametype={"bb": bb}, pot=SimpleNamespace(stp=stp))

    @staticmethod
    def _players(positions: dict[str, Any], start_cash: int = 20000) -> dict[str, dict[str, Any]]:
        return {name: {"position": position, "startCash": start_cash} for name, position in positions.items()}

    def test_antes_are_dead_money_and_do_not_set_the_price(self) -> None:
        """Everyone antes, so the big blind is still exactly what the opener owes."""
        players = self._players({"a": 3, "b": 2, "c": 1, "d": 0, "e": "S", "f": "B"})
        actions = {
            "BLINDSANTES": [(name, "ante", Decimal("0.20"), False) for name in players]
            + [("e", "small blind", Decimal("1.00"), False), ("f", "big blind", Decimal("2.00"), False)],
            "PREFLOP": [("a", "raises", Decimal("3.00"), Decimal("5.00"), Decimal("2.00"), False)],
        }
        events = derive_action_events(self._hand(["BLINDSANTES", "PREFLOP"], actions), players)
        assert [events[number]["potAfter"] for number in range(1, 7)] == [20, 40, 60, 80, 100, 120]
        assert [events[number]["potAfter"] for number in (7, 8)] == [220, 420]
        opener = events[9]
        assert opener["toCall"] == 200, "the ante is already in, but it is not a bet to match"
        assert opener["potBefore"] == 420 and opener["potAfter"] == 920
        assert opener["sizingBp"] == 500 * 10000 // 420

    def test_a_live_straddle_sets_the_price(self) -> None:
        players = self._players({"a": 3, "b": 2, "c": 1, "d": 0, "e": "S", "f": "B"})
        actions = {
            "BLINDSANTES": [
                ("e", "small blind", Decimal("1.00"), False),
                ("f", "big blind", Decimal("2.00"), False),
                ("a", "straddle", Decimal("4.00"), False),
            ],
            "PREFLOP": [("b", "calls", Decimal("4.00"), False), ("f", "calls", Decimal("2.00"), False)],
        }
        events = derive_action_events(self._hand(["BLINDSANTES", "PREFLOP"], actions), players)
        assert events[3]["actionType"] == "straddle" and events[3]["potAfter"] == 700
        assert events[4]["toCall"] == 400, "everyone owes the straddle"
        assert events[5]["toCall"] == 200, "the big blind owes the difference"

    def test_a_short_all_in_call_faces_its_own_stack(self) -> None:
        """A player with 3bb behind cannot be asked 10bb, whatever is out there."""
        players = self._players({"a": 1, "b": 0, "c": "S", "d": "B"})
        players["d"]["startCash"] = 800  # 4bb, of which the blind is already in
        actions = {
            "BLINDSANTES": [("c", "small blind", Decimal("1.00"), False), ("d", "big blind", Decimal("2.00"), False)],
            "PREFLOP": [
                ("a", "raises", Decimal("18.00"), Decimal("20.00"), Decimal("2.00"), False),
                ("b", "folds"),
                ("c", "folds"),
                ("d", "calls", Decimal("6.00"), True),
            ],
        }
        events = derive_action_events(self._hand(["BLINDSANTES", "PREFLOP"], actions), players)
        short_call = events[6]

        assert short_call["actionType"] == "calls"
        assert short_call["toCall"] == 600, "the price is the six the big blind still has"
        assert short_call["facingAmount"] == 600, "and the size faced is that same price"

    def test_a_returning_player_posts_one_live_blind_and_one_dead_one(self) -> None:
        """``both`` is a big blind plus a dead small blind; ``secondsb`` is all dead.

        All of it reaches the pot, none of the dead part raises the price the
        rest of the table has to pay to come in.
        """
        players = self._players({"a": 1, "b": 0, "c": "S", "d": "B", "e": 2})
        actions = {
            "BLINDSANTES": [
                ("c", "small blind", Decimal("1.00"), False),
                ("d", "big blind", Decimal("2.00"), False),
                ("e", "both", Decimal("3.00"), False),
            ],
            "PREFLOP": [("a", "calls", Decimal("2.00"), False), ("e", "checks")],
        }
        events = derive_action_events(self._hand(["BLINDSANTES", "PREFLOP"], actions), players)

        assert events[3]["potAfter"] == 600, "the dead small blind is in the pot"
        assert events[4]["toCall"] == 200, "but the price to enter is still one big blind"
        assert events[5]["toCall"] == 0, "the poster has paid a big blind and owes nothing"

        actions["BLINDSANTES"][2] = ("e", "secondsb", Decimal("1.00"), False)
        actions["PREFLOP"][1] = ("e", "calls", Decimal("2.00"), False)
        events = derive_action_events(self._hand(["BLINDSANTES", "PREFLOP"], actions), players)

        assert events[3]["potAfter"] == 400
        assert events[4]["toCall"] == 200, "a dead small blind buys nothing"
        assert events[5]["toCall"] == 200, "least of all for the player who posted it"

    def test_a_forced_bet_never_makes_an_aggressor(self) -> None:
        players = self._players({"e": "S", "f": "B"}, start_cash=10000)
        actions = {
            "BLINDSANTES": [("e", "small blind", Decimal("1.00"), True), ("f", "big blind", Decimal("2.00"), False)],
        }
        events = derive_action_events(self._hand(["BLINDSANTES"], actions), players)
        assert [events[number]["isAggressor"] for number in (1, 2)] == [False, False]
        assert [events[number]["facingActionType"] for number in (1, 2)] == [None, None]

    def test_spr_and_effective_stack_are_measured_before_the_chips_go_in(self) -> None:
        players = self._players({"a": 1, "b": 0, "c": "S", "d": "B"})
        actions = {
            "BLINDSANTES": [("c", "small blind", Decimal("1.00"), False), ("d", "big blind", Decimal("2.00"), False)],
            "PREFLOP": [
                ("a", "raises", Decimal("3.00"), Decimal("5.00"), Decimal("2.00"), False),
                ("b", "calls", Decimal("5.00"), False),
            ],
        }
        events = derive_action_events(self._hand(["BLINDSANTES", "PREFLOP"], actions), players)
        opener, caller = events[3], events[4]
        assert opener["effectiveStack"] == 20000, "the deepest opponent is still whole"
        assert opener["sprBefore"] == 20000 * 100 // 300
        assert caller["effectiveStack"] == 19900, "the small blind, first to act, is the deepest opponent left"
        assert caller["sprBefore"] == 19900 * 100 // 800
        assert opener["effectiveStackBB"] == 10000, "100 big blinds, in centi-bb"
        assert caller["effectiveStackBB"] == 9950, "and 99.5 once the blind is deducted"

    def test_an_unknown_action_still_produces_a_complete_event(self) -> None:
        """A room-specific word the parser passes through must not lose its context."""
        players = self._players({"a": 0, "b": 1})
        actions = {"FLOP": [("a", "teleports", Decimal("5.00"), False)]}
        events = derive_action_events(self._hand(["FLOP"], actions), players)
        assert set(events[1]) == set(ACTION_EVENT_COLUMNS)
        assert events[1]["actionType"] == "teleports"
        assert events[1]["toCall"] == 0 and events[1]["sizingBp"] == 0

    def test_a_hand_with_no_actions_has_no_events(self) -> None:
        assert derive_action_events(self._hand([], {}), {}) == {}
        assert derive_action_events(self._hand(["PREFLOP"], {"PREFLOP": []}), {}) == {}

    def test_a_missing_position_keeps_the_player_out_of_the_way(self) -> None:
        """No derived position: the player is assumed to act last, not first."""
        players: dict[str, dict[str, Any]] = {
            "a": {"startCash": 10000},
            "b": {"position": None, "startCash": 10000},
            "c": {"position": 0, "startCash": 10000},
        }
        actions = {"PREFLOP": [("c", "bets", Decimal("1.00"), False)]}
        events = derive_action_events(self._hand(["PREFLOP"], actions), players)
        assert events[1]["position"] == 0
        assert events[1]["relativePosition"] == 2, "two players still have to act"
        assert events[1]["inPosition"] is False

    def test_a_player_with_nothing_behind_is_not_counted_as_behind(self) -> None:
        """The big blind shoves; it cannot act again, so it is not "behind" anyone."""
        players = self._players({"a": 1, "b": 0, "c": "S", "d": "B"}, start_cash=1000)
        actions = {
            "BLINDSANTES": [("c", "small blind", Decimal("1.00"), False), ("d", "big blind", Decimal("2.00"), False)],
            "PREFLOP": [
                ("d", "raises", Decimal("8.00"), Decimal("10.00"), Decimal("2.00"), True),
                ("a", "calls", Decimal("10.00"), False),
            ],
        }
        events = derive_action_events(self._hand(["BLINDSANTES", "PREFLOP"], actions), players)
        shove, caller = events[3], events[4]
        assert shove["effectiveStack"] == 800, "the big blind had 800 behind when it shoved"
        assert shove["relativePosition"] == 0
        assert caller["effectiveStack"] == 1000, "the caller's own stack, the button can still cover it"
        assert caller["relativePosition"] == 2, "the button and the small blind are still to act, not the shover"

    def test_stud_bring_in_is_a_forced_bet_that_acts_first(self) -> None:
        """The bring-in is the 'S' seat and opens the third street."""
        players: dict[str, dict[str, Any]] = {
            "a": {"position": 2, "startCash": 2000},
            "b": {"position": 1, "startCash": 2000},
            "c": {"position": "S", "startCash": 2000},
        }
        actions = {
            "BLINDSANTES": [],
            "THIRD": [
                ("c", "bringin", Decimal("1.00"), False),
                ("a", "raises", Decimal("2.00"), Decimal("3.00"), Decimal("1.00"), False),
                ("b", "folds"),
            ],
        }
        # Stud has no big blind: the bring-in alone is the price of third street.
        events = derive_action_events(self._hand(["BLINDSANTES", "THIRD"], actions, bb="0"), players)
        assert events[1]["actionType"] == "bringin" and events[1]["toCall"] == 0
        assert events[1]["isAggressor"] is False
        assert events[2]["toCall"] == 100, "the raiser owes the difference to the bring-in"
        assert events[2]["isAggressor"] is True
        assert events[2]["potAfter"] == 400

    def test_bomb_pot_money_seeds_the_pot(self) -> None:
        players = self._players({"a": 0, "b": 1})
        actions = {"PREFLOP": [("a", "bets", Decimal("1.00"), False)]}
        events = derive_action_events(self._hand(["PREFLOP"], actions, stp=Decimal("5.00")), players)
        assert events[1]["potBefore"] == 500
        assert events[1]["potAfter"] == 600
        assert events[1]["sizingBp"] == 100 * 10000 // 500
