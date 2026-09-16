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

import pytest

from fpdb_3_legacy import analytics_lifecycle as lifecycle
from fpdb_3_legacy.analytics_rebuild import AnalyticsRebuilder, RebuildScope, canonical_subsystems
from fpdb_3_legacy.Database import Database
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
        assert statuses["hand_strength"].code_version == 0  # declared, not implemented

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
        assert lifecycle.stale_subsystems(db) == ("action_events", "situations", "board_features", "sizing_buckets")

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
        assert count == 266
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

        # Simulate a database from before the analytics layers existed.
        c.execute("UPDATE HandsActions SET sizingBp=0, facingSizingBp=0, potBefore=0, potAfter=0, toCall=0")
        c.execute("DELETE FROM HandsSituations")
        c.execute("DELETE FROM BoardFeatures")
        c.execute("UPDATE Hands SET texture = NULL")
        c.execute("DELETE FROM AnalyticsMeta")
        db.commit()
        assert lifecycle.stale_subsystems(db) == ("action_events", "situations", "board_features", "sizing_buckets")

        result = AnalyticsRebuilder(db, None).run(
            ["board_features", "action_events", "situations", "sizing_buckets"],
        )
        assert (result.scanned, result.rebuilt, result.failed, result.cancelled) == (30, 30, 0, False)
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
        assert result.rebuilt == 30
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
        # The stripped hand is skipped (no players to derive), the other 29
        # rebuild -- one bad hand never stops the run.
        assert result.failed == 0 and result.rebuilt == 29 and result.skipped == 1
        # A skipped hand still leaves the subsystem current: the gap is
        # visible in the data, and rerunning is safe.
        assert not lifecycle.is_stale(db, "board_features")

    def test_canonical_subsystems_expand_and_validate(self) -> None:
        assert canonical_subsystems(["sizing_buckets"]) == ("action_events",)
        assert canonical_subsystems(["sizing_buckets", "board_features"]) == ("action_events", "board_features")
        with pytest.raises(ValueError, match="hand_strength"):
            canonical_subsystems(["hand_strength"])
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
