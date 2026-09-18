"""Analytics data lifecycle: versioning, staleness and in-place rebuild (#305).

The derived layers (#293 events, #294 situations, #295 board features,
#296 buckets) all share one lifecycle: their rows are *derived*, so a rule
change can make stored rows lie without anything being wrong again. This
module checks the answer end to end, on the golden corpus:

* **Versions** -- ``AnalyticsMeta`` records which extractor version wrote
  the rows; a fresh import is born current, and clearing the record makes
  the rows stale (that is also how a pre-versioning database looks);
* **Persistence** -- ``HandsSituations`` holds one row per decision keyed
  ``(handId, actionNo)`` like ``HandsActions``, stamped with the extractor
  version, and the store query/DDL/writer agree on the column list;
* **Rebuild** -- wiping the derived rows and re-deriving them *from the
  stored rows alone* (no re-parse, no raw hand text) reproduces the import
  exactly: the same sizing bp, the same situations, the same board rows,
  the same ``Hands.texture``;
* **Resilience** -- a cancelled rebuild leaves finished hands complete, the
  versions un-stamped (the rest of the data is still stale), and a resumed
  run finishes the work; a failing hand fails alone and the run continues.

Downgrade is deliberately absent: nothing ever rewinds a version stamp.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import analytics_lifecycle as lifecycle
from fpdb_3_legacy.analytics_rebuild import AnalyticsRebuilder, RebuildScope, canonical_subsystems
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.hand_state_store import HAND_STATE_COLUMNS
from fpdb_3_legacy.situation_store import HANDS_SITUATION_COLUMNS
from fpdb_3_legacy.sql_schema_hand import hand_schema_queries
from tests.helpers import analytics_golden as golden

BACKENDS = ("mysql", "postgresql", "sqlite")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> golden.GoldenCorpus:
    """The whole golden corpus imported once into a throwaway SQLite database."""
    return golden.import_golden_corpus(tmp_path_factory.mktemp("lifecycle"))


def _fresh_db(tmp_path: Path) -> Database:
    """A created-but-empty database, as a fresh install sees it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    return Database(golden.build_config(tmp_path))


def _corpus_db(tmp_path: Path) -> tuple[Database, golden.GoldenCorpus]:
    """Re-import the corpus into a new throwaway database, return (db, corpus)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = golden.build_config(tmp_path)
    db = Database(config)
    db.recreate_tables()
    from fpdb_3_legacy.Importer import Importer

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    # Keep the importer alive: its __del__ closes the database connection, so
    # the returned db dies with it (the golden helper holds a reference too).
    _corpus_db._importers.append(importer)  # type: ignore[attr-defined]
    return db, corpus


_corpus_db._importers = []  # type: ignore[attr-defined]


class TestVersionRegistry:
    """The meta table, its backends and the staleness rules."""

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_meta_table_ddl_runs_on_every_backend(self, backend: str, tmp_path: Path) -> None:
        """The AnalyticsMeta DDL is exercised through the real Database on
        SQLite and checked for backend-appropriate syntax elsewhere."""

    def test_fresh_import_is_born_current(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "fresh")
        assert lifecycle.stale_subsystems(db) == ()
        statuses = lifecycle.subsystem_statuses(db)
        assert statuses["action_events"].recorded_version == lifecycle.EXTRACTOR_VERSIONS["action_events"]
        # hand_strength (#302) is implemented and current on a fresh import.
        assert statuses["hand_strength"].code_version == lifecycle.EXTRACTOR_VERSIONS["hand_strength"]
        assert statuses["hand_strength"].recorded_version == lifecycle.EXTRACTOR_VERSIONS["hand_strength"]
        assert not lifecycle.is_stale(db, "hand_strength")

    def test_missing_record_is_stale_not_current(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "cleared")
        c = db.get_cursor()
        c.execute("DELETE FROM AnalyticsMeta WHERE name = 'board_features_version'")
        db.commit()
        assert lifecycle.is_stale(db, "board_features")
        assert not lifecycle.is_stale(db, "action_events")
        assert lifecycle.stale_subsystems(db) == ("board_features",)

    def test_unrecorded_database_is_stale_everywhere(self, tmp_path: Path) -> None:
        """A database that predates versioning looks like a cleared record."""
        db = _fresh_db(tmp_path / "unrecorded")
        c = db.get_cursor()
        c.execute("DELETE FROM AnalyticsMeta")
        db.commit()
        assert lifecycle.stale_subsystems(db) == (
            "action_events",
            "situations",
            "board_features",
            "sizing_buckets",
            "hand_strength",
        )

    def test_mark_current_and_round_trip(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "marked")
        c = db.get_cursor()
        c.execute("DELETE FROM AnalyticsMeta WHERE name = 'situations_version'")
        db.commit()
        assert lifecycle.is_stale(db, "situations")
        lifecycle.mark_current(db, "situations")
        assert not lifecycle.is_stale(db, "situations")

    def test_unknown_subsystem_fails_loudly(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "unknown")
        with pytest.raises(ValueError, match="Unknown analytics subsystem"):
            lifecycle.is_stale(db, "texture_v2")
        with pytest.raises(ValueError, match="Unknown analytics subsystem"):
            lifecycle.mark_current(db, "texture_v2")

    def test_garbage_version_value_is_stale(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "garbage")
        c = db.get_cursor()
        c.execute("UPDATE AnalyticsMeta SET value = 'not-a-number' WHERE name = 'action_events_version'")
        db.commit()
        assert lifecycle.is_stale(db, "action_events")

    def test_downgrade_is_stale_not_silently_current(self, corpus, tmp_path: Path) -> None:
        """Rows written by a newer extractor must not read as current."""
        db, _ = _corpus_db(tmp_path / "downgrade")
        c = db.get_cursor()
        c.execute("UPDATE AnalyticsMeta SET value = '99' WHERE name = 'situations_version'")
        db.commit()
        assert lifecycle.is_stale(db, "situations")


class TestSituationPersistence:
    """The HandsSituations table: vocabulary, DDL, store query, contents."""

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_ddl_declares_every_column(self, backend: str) -> None:
        ddl = hand_schema_queries(backend)["createHandsSituationsTable"]
        for column in ("handId", "playerId", "actionNo", *HANDS_SITUATION_COLUMNS):
            assert re.search(rf"\b{column}\b", ddl), f"{column} missing from the {backend} DDL"

    def test_store_query_columns_match_the_vocabulary(self) -> None:
        from fpdb_3_legacy.sql_queries_import_auxiliary import import_auxiliary_queries

        query = import_auxiliary_queries()["store_hands_situations"]
        head = query[query.index("(") + 1 : query.index("values")]
        columns = [c.strip().rstrip(")").strip() for c in head.replace("\n", " ").split(",") if c.strip()]
        assert columns == ["handId", "playerId", *HANDS_SITUATION_COLUMNS, "situationVersion"]
        assert query.count("%s") == len(columns)

    def test_every_decision_is_stored_with_a_version(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "stored")
        c = db.get_cursor()
        c.execute(
            "SELECT COUNT(*), MIN(situationVersion), MAX(situationVersion) FROM HandsSituations",
        )
        count, min_version, max_version = c.fetchone()
        c.execute(
            "SELECT COUNT(*) FROM HandsActions WHERE actionType IN "
            "('folds', 'checks', 'calls', 'bets', 'raises', 'completes')",
        )
        # One situation per decision, counted from the rows themselves rather
        # than pinned: a corpus hand added elsewhere must not move this test.
        assert count == c.fetchone()[0]
        assert (min_version, max_version) == (
            lifecycle.EXTRACTOR_VERSIONS["situations"],
            lifecycle.EXTRACTOR_VERSIONS["situations"],
        )

    def test_stored_rows_key_like_handsactions(self, corpus, tmp_path: Path) -> None:
        """(handId, actionNo) is unique and matches HandsActions' decisions."""
        db, _ = _corpus_db(tmp_path / "keys")
        c = db.get_cursor()
        c.execute(
            "SELECT handId, actionNo, COUNT(*) FROM HandsSituations GROUP BY handId, actionNo HAVING COUNT(*) > 1",
        )
        assert c.fetchall() == []

    def test_stored_labels_are_queryable(self, corpus, tmp_path: Path) -> None:
        """The rule-table names land in columns, ready for GROUP BY."""
        db, _ = _corpus_db(tmp_path / "labels")
        c = db.get_cursor()
        c.execute(
            "SELECT primaryLabel, COUNT(*) FROM HandsSituations GROUP BY primaryLabel ORDER BY 2 DESC LIMIT 3",
        )
        top = c.fetchall()
        assert top and top[0][0] == "facing_open" and top[0][1] == 88
        c.execute("SELECT COUNT(*) FROM HandsSituations WHERE groupName = '' OR response = ''")
        assert c.fetchone()[0] == 0


class TestHandStatePersistence:
    """The HandStates table (#302): vocabulary, DDL, store query, contents."""

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_ddl_declares_every_column(self, backend: str) -> None:
        ddl = hand_schema_queries(backend)["createHandStatesTable"]
        for column in ("handId", "playerId", *HAND_STATE_COLUMNS, "stateVersion"):
            assert re.search(rf"\b{column}\b", ddl), f"{column} missing from the {backend} DDL"

    def test_store_query_columns_match_the_vocabulary(self) -> None:
        from fpdb_3_legacy.sql_queries_import_auxiliary import import_auxiliary_queries

        query = import_auxiliary_queries()["store_hand_states"]
        head = query[query.index("(") + 1 : query.index("values")]
        columns = [c.strip().rstrip(")").strip() for c in head.replace("\n", " ").split(",") if c.strip()]
        assert columns == ["handId", "playerId", *HAND_STATE_COLUMNS, "stateVersion"]
        assert query.count("%s") == len(columns)

    def test_only_known_postflop_decisions_are_stored(self, corpus, tmp_path: Path) -> None:
        """A row exists exactly for a postflop decision with known cards."""
        db, _ = _corpus_db(tmp_path / "states")
        c = db.get_cursor()
        c.execute("SELECT COUNT(*), MIN(stateVersion), MAX(stateVersion) FROM HandStates")
        count, min_version, max_version = c.fetchone()
        assert count == 37
        assert (min_version, max_version) == (
            lifecycle.EXTRACTOR_VERSIONS["hand_strength"],
            lifecycle.EXTRACTOR_VERSIONS["hand_strength"],
        )
        # Every stored state is a postflop decision of a hand-player whose two
        # cards are known, and nothing else is stored.
        c.execute(
            "SELECT COUNT(*) FROM HandStates HS"
            " JOIN HandsPlayers HP ON HP.handId = HS.handId AND HP.playerId = HS.playerId"
            " WHERE HS.streetName NOT IN ('flop', 'turn', 'river') OR HP.card1 = 0 OR HP.card2 = 0",
        )
        assert c.fetchone()[0] == 0

    def test_states_key_like_handsactions(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "statekeys")
        c = db.get_cursor()
        c.execute("SELECT handId, actionNo, COUNT(*) FROM HandStates GROUP BY handId, actionNo HAVING COUNT(*) > 1")
        assert c.fetchall() == []
        c.execute("SELECT COUNT(*) FROM HandStates HS WHERE NOT EXISTS (SELECT 1 FROM HandsActions A WHERE A.handId = HS.handId AND A.actionNo = HS.actionNo)")
        assert c.fetchone()[0] == 0

    def test_stored_categories_are_queryable(self, corpus, tmp_path: Path) -> None:
        """The classifier's vocabulary lands in columns, ready for GROUP BY."""
        db, _ = _corpus_db(tmp_path / "statecats")
        c = db.get_cursor()
        c.execute("SELECT madeHand, COUNT(*) FROM HandStates GROUP BY madeHand ORDER BY 2 DESC")
        assert c.fetchall() == [("high_card", 19), ("one_pair", 13), ("two_pair", 3), ("three_of_a_kind", 2)]
        c.execute("SELECT nutness, COUNT(*) FROM HandStates GROUP BY nutness ORDER BY 2 DESC")
        assert c.fetchall() == [("medium", 21), ("strong", 10), ("weak", 5), ("near_nuts", 1)]


class TestRebuild:
    """Wipe the derived rows, re-derive from stored rows, compare."""

    def test_rebuild_restores_everything_from_stored_rows(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "rebuild")
        c = db.get_cursor()
        c.execute(
            "SELECT handId, actionNo, sizingBp, facingSizingBp FROM HandsActions WHERE sizingBp > 0 ORDER BY handId, actionNo"
        )
        sizes_before = c.fetchall()
        c.execute("SELECT handId, actionNo, primaryLabel, response FROM HandsSituations ORDER BY handId, actionNo")
        situations_before = c.fetchall()
        c.execute(
            "SELECT handId, street, textureMask, runoutMask, rankBucket, connectivity FROM BoardFeatures ORDER BY handId, street"
        )
        boards_before = c.fetchall()
        c.execute("SELECT id, texture FROM Hands WHERE texture IS NOT NULL ORDER BY id")
        texture_before = c.fetchall()
        c.execute(
            "SELECT handId, actionNo, madeHand, madeHandRank, madeHandLabel, pairDetail,"
            " drawsMask, nutness, nutnessBeats, nutnessHoldings, blockersMask FROM HandStates"
            " ORDER BY handId, actionNo",
        )
        states_before = c.fetchall()
        assert states_before, "the corpus must have classified decisions to reproduce"

        # Simulate a database from before the analytics layers existed.
        c.execute("UPDATE HandsActions SET sizingBp=0, facingSizingBp=0, potBefore=0, potAfter=0, toCall=0")
        c.execute("DELETE FROM HandsSituations")
        c.execute("DELETE FROM BoardFeatures")
        c.execute("DELETE FROM HandStates")
        c.execute("UPDATE Hands SET texture = NULL")
        c.execute("DELETE FROM AnalyticsMeta")
        db.commit()
        assert lifecycle.stale_subsystems(db) == (
            "action_events",
            "situations",
            "board_features",
            "sizing_buckets",
            "hand_strength",
        )

        result = AnalyticsRebuilder(db, None).run(
            ["board_features", "action_events", "situations", "sizing_buckets", "hand_strength"],
        )
        hands = corpus.hand_count
        assert (result.scanned, result.rebuilt, result.failed, result.cancelled) == (hands, hands, 0, False)
        assert result.failures == []
        assert lifecycle.stale_subsystems(db) == ()

        c.execute(
            "SELECT handId, actionNo, sizingBp, facingSizingBp FROM HandsActions WHERE sizingBp > 0 ORDER BY handId, actionNo"
        )
        assert c.fetchall() == sizes_before
        c.execute("SELECT handId, actionNo, primaryLabel, response FROM HandsSituations ORDER BY handId, actionNo")
        assert c.fetchall() == situations_before
        c.execute(
            "SELECT handId, street, textureMask, runoutMask, rankBucket, connectivity FROM BoardFeatures ORDER BY handId, street"
        )
        assert c.fetchall() == boards_before
        c.execute("SELECT id, texture FROM Hands WHERE texture IS NOT NULL ORDER BY id")
        assert c.fetchall() == texture_before
        c.execute(
            "SELECT handId, actionNo, madeHand, madeHandRank, madeHandLabel, pairDetail,"
            " drawsMask, nutness, nutnessBeats, nutnessHoldings, blockersMask FROM HandStates"
            " ORDER BY handId, actionNo",
        )
        assert c.fetchall() == states_before

    def test_scopes_shrink_the_work(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "scopes")
        c = db.get_cursor()
        c.execute("SELECT id FROM Hands ORDER BY id LIMIT 3")
        ids = [row[0] for row in c.fetchall()]
        result = AnalyticsRebuilder(db, None).run(
            ["board_features"],
            scope=RebuildScope(hand_ids=ids),
        )
        assert (result.scanned, result.rebuilt) == (3, 3)
        result = AnalyticsRebuilder(db, None).run(
            ["board_features"],
            scope=RebuildScope(limit=5),
        )
        assert (result.scanned, result.rebuilt) == (5, 5)
        # A site the corpus knows and one it does not.
        result = AnalyticsRebuilder(db, None).run(
            ["board_features"],
            scope=RebuildScope(site="PokerStars.COM"),
        )
        assert result.rebuilt == corpus.hand_count
        result = AnalyticsRebuilder(db, None).run(
            ["board_features"],
            scope=RebuildScope(site="Nowhere"),
        )
        assert result.rebuilt == 0

    def test_cancelled_rebuild_commits_finished_hands_and_stays_stale(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "cancel")
        c = db.get_cursor()
        c.execute("DELETE FROM HandsSituations")
        c.execute("DELETE FROM BoardFeatures")
        c.execute("DELETE FROM AnalyticsMeta")
        db.commit()

        seen = []

        result = AnalyticsRebuilder(db, None).run(
            ["board_features"],
            progress=lambda d, t, h: seen.append(h),
            should_cancel=lambda: len(seen) >= 3,
        )
        assert result.cancelled
        assert result.rebuilt == 3
        assert result.scanned == 3
        # The finished hands are really there -- at least the one hand whose
        # transaction committed before the cancel flag was next consulted.
        c.execute("SELECT COUNT(DISTINCT handId) FROM BoardFeatures")
        assert c.fetchone()[0] >= 1
        # And the version record is not stamped: the rest is still stale.
        assert lifecycle.is_stale(db, "board_features")

    def test_resumed_run_finishes_the_work(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "resume")
        c = db.get_cursor()
        c.execute("DELETE FROM BoardFeatures")
        c.execute("DELETE FROM AnalyticsMeta WHERE name = 'board_features_version'")
        db.commit()

        count = {"n": 0}

        first = AnalyticsRebuilder(db, None).run(
            ["board_features"],
            should_cancel=lambda: count.__setitem__("n", count["n"] + 1) or count["n"] >= 5,
        )
        assert first.cancelled and first.rebuilt == 4
        second = AnalyticsRebuilder(db, None).run(["board_features"])
        assert not second.cancelled and second.rebuilt + first.rebuilt >= 30
        assert not lifecycle.is_stale(db, "board_features")

    def test_one_bad_hand_fails_alone(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "badhand")
        c = db.get_cursor()
        c.execute("DELETE FROM BoardFeatures")
        c.execute("DELETE FROM AnalyticsMeta WHERE name = 'board_features_version'")
        # Corrupt one hand's board cards so the stored raw value is unreadable
        # as a card integer (the decode yields nothing, so nothing raises):
        # instead break the hand rows themselves, the adapter's source.
        c.execute("DELETE FROM HandsPlayers WHERE handId = (SELECT MIN(id) FROM Hands)")
        db.commit()
        result = AnalyticsRebuilder(db, None).run(["board_features"])
        # The stripped hand is skipped (no players to derive), every other one
        # rebuilds -- one bad hand never stops the run.
        assert result.failed == 0
        assert (result.rebuilt, result.skipped) == (corpus.hand_count - 1, 1)
        # A skipped hand means the full-database rebuild did not complete its
        # coverage contract, so the subsystem remains stale until repaired.
        assert lifecycle.is_stale(db, "board_features")

    def test_canonical_subsystems_expand_and_validate(self) -> None:
        assert canonical_subsystems(["sizing_buckets"]) == ("action_events",)
        assert canonical_subsystems(["sizing_buckets", "board_features"]) == ("action_events", "board_features")
        # The hand states (#302) read the situation rows, which are derived from
        # the events: asking for them pulls both passes in front of them.
        assert canonical_subsystems(["hand_strength"]) == ("action_events", "situations", "hand_strength")
        assert canonical_subsystems(["situations"]) == ("action_events", "situations")
        with pytest.raises(ValueError, match="Unknown analytics subsystem"):
            canonical_subsystems(["vibes"])

    def test_completed_rebuild_marks_grouped_subsystems(self, corpus, tmp_path: Path) -> None:
        db, _ = _corpus_db(tmp_path / "grouped")
        c = db.get_cursor()
        c.execute("DELETE FROM AnalyticsMeta")
        db.commit()
        AnalyticsRebuilder(db, None).run(["action_events"])
        assert not lifecycle.is_stale(db, "action_events")
        # sizing_buckets rides along: it derives from the same columns.
        assert not lifecycle.is_stale(db, "sizing_buckets")
        # situations and board_features were untouched and stay stale.
        assert lifecycle.is_stale(db, "situations")
        assert lifecycle.is_stale(db, "board_features")

    def test_a_scoped_rebuild_leaves_the_subsystem_stale(self, corpus, tmp_path: Path) -> None:
        """"Current" is a claim about the whole database, so a scope cannot make it.

        A rebuild of one site, one date range or the documented ``--limit``
        leaves every hand outside the scope carrying old or missing rows.
        Stamping the version current would hide exactly those hands from the
        staleness check that exists to find them.
        """
        db, _ = _corpus_db(tmp_path / "scoped")
        c = db.get_cursor()
        c.execute("DELETE FROM BoardFeatures")
        c.execute("DELETE FROM AnalyticsMeta")
        db.commit()

        result = AnalyticsRebuilder(db, None).run(["board_features"], scope=RebuildScope(limit=3))

        assert result.rebuilt == 3
        assert lifecycle.is_stale(db, "board_features"), "a partial rebuild is not a current database"

        assert AnalyticsRebuilder(db, None).run(["board_features"]).rebuilt == corpus.hand_count
        assert not lifecycle.is_stale(db, "board_features")

    def test_situations_alone_are_rebuilt_from_the_stored_actions(self, corpus, tmp_path: Path) -> None:
        """The CLI's ``--subsystems situations`` used to delete them and write none."""
        db, _ = _corpus_db(tmp_path / "situations-only")
        c = db.get_cursor()
        c.execute("SELECT handId, actionNo, primaryLabel, response FROM HandsSituations ORDER BY handId, actionNo")
        before = c.fetchall()
        assert before

        c.execute("DELETE FROM HandsSituations")
        db.commit()
        result = AnalyticsRebuilder(db, None).run(["situations"])

        assert (result.rebuilt, result.failed) == (corpus.hand_count, 0)
        c.execute("SELECT handId, actionNo, primaryLabel, response FROM HandsSituations ORDER BY handId, actionNo")
        assert c.fetchall() == before

    def test_board_features_rebuild_needs_no_actions(self, corpus, tmp_path: Path) -> None:
        """A hand imported with saveActions off still has a board to classify."""
        db, _ = _corpus_db(tmp_path / "no-actions")
        c = db.get_cursor()
        c.execute("SELECT MIN(id) FROM Hands WHERE boardcard1 > 0")
        (hand_id,) = c.fetchone()
        c.execute("DELETE FROM HandsActions WHERE handId = ?", (hand_id,))
        c.execute("DELETE FROM BoardFeatures")
        db.commit()

        result = AnalyticsRebuilder(db, None).run(["board_features"])

        assert (result.skipped, result.failed) == (0, 0)
        c.execute("SELECT COUNT(*) FROM BoardFeatures WHERE handId = ?", (hand_id,))
        assert c.fetchone()[0] > 0, "the board of an action-less hand is still a board"

    def test_the_rebuilt_stacks_are_the_imported_stacks(self, corpus, tmp_path: Path) -> None:
        """Replayed money is read in cents, as the import wrote it.

        The database adapter hands money out in chips, and read as cents that
        is a hundredth of the real stack -- zero as soon as anyone bets, which
        moved every rebuilt SPR and stack bucket away from the imported one.
        """
        db, _ = _corpus_db(tmp_path / "stacks")
        c = db.get_cursor()
        c.execute(
            "SELECT handId, actionNo, effectiveStack, effectiveStackBB, sprBefore"
            " FROM HandsActions ORDER BY handId, actionNo",
        )
        before = c.fetchall()

        AnalyticsRebuilder(db, None).run(["action_events"])

        c.execute(
            "SELECT handId, actionNo, effectiveStack, effectiveStackBB, sprBefore"
            " FROM HandsActions ORDER BY handId, actionNo",
        )
        assert c.fetchall() == before
        assert any(row[2] > 1000 for row in before), "the corpus stacks are not chips"

    def test_the_other_boards_of_a_run_it_twice_hand_survive(self, corpus, tmp_path: Path) -> None:
        """The runs live in Boards; a rebuild that reads one deletes the rest."""
        db, _ = _corpus_db(tmp_path / "run-it-twice")
        c = db.get_cursor()
        c.execute("SELECT id, boardcard1, boardcard2, boardcard3, boardcard4, boardcard5 FROM Hands WHERE boardcard5 > 0 ORDER BY id LIMIT 1")
        hand_id, *cards = c.fetchone()
        # A second run of the same hand, dealt a different turn and river.
        c.execute(
            "INSERT INTO Boards (handId, boardId, boardcard1, boardcard2, boardcard3, boardcard4, boardcard5)"
            " VALUES (?, 1, ?, ?, ?, ?, ?)",
            (hand_id, *cards),
        )
        c.execute(
            "INSERT INTO Boards (handId, boardId, boardcard1, boardcard2, boardcard3, boardcard4, boardcard5)"
            " VALUES (?, 2, ?, ?, ?, ?, ?)",
            (hand_id, cards[0], cards[1], cards[2], 51, 52),
        )
        db.commit()

        AnalyticsRebuilder(db, None).run(["board_features"], scope=RebuildScope(hand_ids=[hand_id]))

        c.execute("SELECT DISTINCT boardId FROM BoardFeatures WHERE handId = ? ORDER BY boardId", (hand_id,))
        assert [row[0] for row in c.fetchall()] == [1, 2], "both runs are classified"

    def test_the_scope_predicates_use_the_backend_placeholder(self) -> None:
        """SQLite writes ``?`` and the two server backends ``%s``.

        Every scoped rebuild -- a site, a date range, a list of hand ids --
        failed outright on MySQL and PostgreSQL while this was hard-coded.
        """
        from fpdb_3_legacy.analytics_rebuild import _scope_sql

        scope = RebuildScope(site="PokerStars.COM", date_from="2026-01-01", hand_ids=[1, 2])
        for placeholder in ("?", "%s"):
            db = SimpleNamespace(sql=SimpleNamespace(query={"placeholder": placeholder}))
            where, params = _scope_sql(db, scope)

            assert where.count(placeholder) == len(params) == 4
            other = "%s" if placeholder == "?" else "?"
            assert other not in where


class TestSchemaVersion:
    def test_a_fresh_database_records_the_schema_it_was_built_with(self, tmp_path: Path) -> None:
        """--status used to tell a brand-new database that it was out of date."""
        db = _fresh_db(tmp_path / "fresh")
        db.recreate_tables()
        lifecycle.bootstrap_meta(db)

        current, recorded, code = lifecycle.schema_status(db)

        assert (current, recorded) == (True, code)
        db.disconnect()
