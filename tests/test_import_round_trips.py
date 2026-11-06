"""What a bulk import asks the database, and that asking less changes nothing it stores (#705).

Over a network each statement costs a round trip, so the number of statements
is what decides how long an import takes. SQLite runs the code that is not tied
to PostgreSQL; tests/test_import_round_trips_postgres.py runs the rest against a
live server.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fpdb_3_legacy import db_profile
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Exceptions import FpdbError
from fpdb_3_legacy.Importer import Importer

REPO = Path(__file__).resolve().parent.parent
TOURNEY_FILE = REPO / "regression-test-files/tour/PokerTracker/Flop/NLHE-2max-USD-0-STT-201307.Microgaming.txt"
CASH_FILES = [
    REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt",
    REPO / "regression-test-files/cash/PokerTracker/Flop/NLHE-USD-0.50-1.00-201101.Merge.txt",
]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    shutil.copyfile(REPO / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / "rounds.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    return config


def _importer(config: Config, files: list[Path]) -> tuple[Importer, list[str]]:
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    shown: list[str] = []
    importer.set_progress_callbacks(lambda _total: None, lambda _path, count: shown.append(count), lambda: None)
    for path in files:
        importer.addImportFile(str(path), "auto")
    return importer, shown


def test_the_hands_are_counted_once_and_the_count_shown_still_grows(config: Config, monkeypatch) -> None:
    importer, shown = _importer(config, CASH_FILES)
    calls: list[int] = []
    count = importer.database.getHandCount
    monkeypatch.setattr(importer.database, "getHandCount", lambda: calls.append(1) or count())

    stored, *_rest = importer.runImport()
    first_file_stored = importer.file_results[str(CASH_FILES[0])].stored
    in_database = count()
    importer.close()

    assert len(calls) == 1
    assert shown == ["0", str(first_file_stored)]
    assert in_database == stored


def test_importing_files_does_not_reconnect(config: Config, monkeypatch) -> None:
    importer, _shown = _importer(config, CASH_FILES)
    connection = importer.database.connection
    monkeypatch.setattr(
        importer.database, "do_connect", lambda _config: pytest.fail("an import opened a new connection")
    )

    importer.runImport()

    assert importer.database.connection is connection
    importer.close()


def test_duplicates_are_preloaded_after_the_hand_id_lock(config: Config, monkeypatch) -> None:
    """nextHandId waits for another importer to commit: asked before it, a hand just stored looks absent."""
    importer, _shown = _importer(config, CASH_FILES[:1])
    order: list[str] = []
    database = importer.database
    next_hand_id, preload = database.nextHandId, database.preload_duplicate_check
    monkeypatch.setattr(database, "nextHandId", lambda: order.append("lock") or next_hand_id())
    monkeypatch.setattr(database, "preload_duplicate_check", lambda hands: order.append("preload") or preload(hands))

    importer.runImport()
    importer.close()

    assert order == ["lock", "preload"]


def test_a_file_reads_its_tournament_once_rather_than_once_per_hand(config: Config, monkeypatch) -> None:
    monkeypatch.setenv(db_profile.ENV_FLAG, "1")
    importer, _shown = _importer(config, [TOURNEY_FILE])
    profile = db_profile.get_profile()
    profile.reset()

    stored, *_rest = importer.runImport()
    calls = {label: stats.calls for label, stats in profile.by_statement.items()}
    profile.reset()
    importer.close()

    assert stored > 2
    assert calls["getTourneyByTourneyNo"] == 1
    assert calls["updateTourneyEnd"] == 1
    # Once for the new tournament and once again after it was given a type.
    assert calls["getTourneyTypeIdByTourneyNo"] <= 2


class _Tourneys:
    """The Tourneys row a sequence of hands leaves behind."""

    def __init__(self, config: Config) -> None:
        self.db = Database(config)
        self.db.resetBulkCache()

    def hand(self, number: int, *, hour: int, name: str | None = None) -> SimpleNamespace:
        return SimpleNamespace(
            siteId=2,
            tourNo=number,
            tourneyTypeId=None,
            tourneyName=name,
            startTime=datetime(2026, 1, 1, hour),  # noqa: DTZ001 - stored naive, as the import does
        )

    def row(self, number: int) -> tuple[Any, ...]:
        c = self.db.get_cursor()
        c.execute("SELECT startTime, endTime, tourneyName FROM Tourneys WHERE siteTourneyNo = ?", (number,))
        return tuple(c.fetchone())


def _store_type_for_tourney(db: Database) -> None:
    # getTourneyByTourneyNo joins TourneyTypes, so a tourney needs a type of the site.
    c = db.get_cursor()
    c.execute("SELECT id FROM Sites LIMIT 1")
    c.execute("INSERT INTO TourneyTypes (id, siteId) VALUES (1, 2)")
    db.commit()


@pytest.mark.parametrize("hours", [(12, 14, 13, 16, 15), (12, 10, 11, 14, 9), (8, 8, 8)])
def test_times_read_once_end_as_they_would_one_hand_at_a_time(config: Config, hours: tuple[int, ...]) -> None:
    tourneys = _Tourneys(config)
    _store_type_for_tourney(tourneys.db)

    def play(number: int, hands: tuple[int, ...]) -> list[Any]:
        ids = []
        for position, hour in enumerate(hands):
            hand = tourneys.hand(number, hour=hour, name="Sunday" if position == 1 else None)
            hand.tourneyTypeId = 1
            ids.append(tourneys.db.getSqlTourneyIDs(hand))
        return ids

    # Each pass starts with a row already stored at the first hand's time, the
    # state of a tournament a previous file has begun.
    alone = play(1, hours)
    with tourneys.db.tourney_lookups_for_file():
        batched = play(2, hours)

    assert len(set(alone)) == 1
    assert len(set(batched)) == 1
    assert tourneys.row(2) == tourneys.row(1)
    tourneys.db.close_connection()


def test_a_failed_file_writes_no_times(config: Config) -> None:
    tourneys = _Tourneys(config)
    _store_type_for_tourney(tourneys.db)
    first = tourneys.hand(3, hour=12)
    first.tourneyTypeId = 1
    tourneys.db.getSqlTourneyIDs(first)
    before = tourneys.row(3)

    later = tourneys.hand(3, hour=18)
    later.tourneyTypeId = 1
    with pytest.raises(ValueError, match="broken"), tourneys.db.tourney_lookups_for_file():
        tourneys.db.getSqlTourneyIDs(later)
        raise ValueError("broken")

    assert tourneys.row(3) == before
    assert tourneys.db._tourney_lookups is None
    tourneys.db.close_connection()


class _ScriptedCursor:
    """Answers each statement from a script, and records what it was asked."""

    description = None

    def __init__(self, *answers: list[Any]) -> None:
        self.answers = list(answers)
        self.rows: list[Any] = []
        self.executed: list[tuple[str, Any]] = []
        self.batched: list[tuple[str, list[Any], bool]] = []
        self.results: list[list[Any]] = []

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))
        self.rows = list(self.answers.pop(0)) if self.answers else []

    def executemany(self, query: str, rows: list[Any], *, returning: bool = False) -> None:
        self.batched.append((query, rows, returning))
        self.results = [[(1000 + position,)] for position in range(len(rows))]
        self.nextset()

    def nextset(self) -> bool | None:
        if not self.results:
            return None
        self.rows = self.results.pop(0)
        return True

    def fetchone(self) -> Any:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[Any]:
        return self.rows


def _postgres_host(cursor: _ScriptedCursor) -> Database:
    """A Database talking to a scripted cursor, as the PostgreSQL backend does."""
    db = Database.__new__(Database)
    db.backend = Database.PGSQL
    db.sql = SimpleNamespace(
        query={
            "placeholder": "%s",
            "players_by_names": "players_by_names",
            "hands_already_stored": "hands_already_stored",
            "tourneysPlayersIdsByPlayers": "tourneysPlayersIdsByPlayers",
            "insertTourneysPlayer": "insertTourneysPlayer",
            "isAlreadyInDB": "isAlreadyInDB<heroSeat>",
        }
    )
    db.pcache = None
    db.tpcache = None
    db.get_cursor = lambda _connect=False: cursor
    db.resetBulkCache()
    return db


def _stored_hand(number: Any, *, public: bool = False, seat: Any = 1, site: int = 2) -> SimpleNamespace:
    return SimpleNamespace(siteId=site, publicDB=public, hands={"siteHandNo": number, "heroSeat": seat})


def test_an_insert_returns_its_id_without_asking_again() -> None:
    cursor = _ScriptedCursor([(7,)])

    assert _postgres_host(cursor).insert_returning_id(cursor, "INSERT x", (1,)) == 7
    assert cursor.executed == [("INSERT x RETURNING id", (1,))]


def test_a_batch_returns_its_ids_in_order() -> None:
    cursor = _ScriptedCursor()

    assert _postgres_host(cursor).insert_many_returning_ids(cursor, "INSERT x", [(1,), (2,), (3,)]) == [
        1000,
        1001,
        1002,
    ]
    assert cursor.batched == [("INSERT x RETURNING id", [(1,), (2,), (3,)], True)]


def test_the_preload_answers_for_each_hand_in_one_query() -> None:
    cursor = _ScriptedCursor([(5, 2, 1)])
    db = _postgres_host(cursor)

    db.preload_duplicate_check([_stored_hand("5"), _stored_hand("6"), _stored_hand("6")])

    assert len(cursor.executed) == 1
    assert cursor.executed[0][1] == ([5, 6], [2])
    assert db.isDuplicate(2, "5", 1, False) is True
    assert db.isDuplicate(2, "6", 1, False) is False
    # The second copy of a hand in the file.
    assert db.isDuplicate(2, "6", 1, False) is True
    assert len(cursor.executed) == 1


def test_a_public_database_compares_the_hero_seat_too() -> None:
    cursor = _ScriptedCursor([(5, 2, 3)])
    db = _postgres_host(cursor)

    db.preload_duplicate_check([_stored_hand("5", public=True, seat=3), _stored_hand("5", public=True, seat=4)])

    assert db.known_hands == {("5", 2, 3): True, ("5", 2, 4): False}


@pytest.mark.parametrize("number", [str(2**64), "not a number", None])
def test_a_number_the_column_cannot_hold_is_left_to_its_own_query(number: Any) -> None:
    cursor = _ScriptedCursor([])
    db = _postgres_host(cursor)

    db.preload_duplicate_check([_stored_hand(number)])

    assert not db.known_hands
    assert not cursor.executed
    assert db.isDuplicate(2, number, 1, False) is False
    assert len(cursor.executed) == 1


def test_no_hands_to_preload_ask_nothing() -> None:
    cursor = _ScriptedCursor()
    db = _postgres_host(cursor)

    db.preload_duplicate_check([])

    assert not cursor.executed


def test_preloading_is_for_postgresql_only() -> None:
    cursor = _ScriptedCursor()
    db = _postgres_host(cursor)
    db.backend = Database.SQLITE

    db.preload_duplicate_check([_stored_hand("5")])

    assert not db.known_hands
    assert not cursor.executed


def test_resetting_the_buffers_forgets_the_preload() -> None:
    cursor = _ScriptedCursor([])
    db = _postgres_host(cursor)
    db.preload_duplicate_check([_stored_hand("5")])

    db.resetBulkCache()

    assert not db.known_hands


def test_players_are_found_and_inserted_in_one_batch_each() -> None:
    # alice is stored without the hero flag, carol with it; bob and dave are new.
    cursor = _ScriptedCursor([(1, "alice", False), (3, "carol", True)])
    db = _postgres_host(cursor)

    ids = db.getSqlPlayerIDs(["alice", "bob", "carol", "dave", "bob"], 2, "alice")

    assert ids == {"alice": 1, "bob": 1000, "carol": 3, "dave": 1001}
    assert cursor.executed[0] == ("players_by_names", (2, ["alice", "bob", "carol", "dave"]))
    assert cursor.executed[1] == ("UPDATE Players SET hero=%s WHERE id=%s", (True, 1))
    assert len(cursor.executed) == 2
    query, rows, returning = cursor.batched[0]
    assert query.endswith("RETURNING id")
    assert returning is True
    assert rows == [("bob", 2, False, "BO"), ("dave", 2, False, "DA")]


def test_players_already_cached_ask_nothing() -> None:
    cursor = _ScriptedCursor([(1, "alice", True)])
    db = _postgres_host(cursor)
    db.getSqlPlayerIDs(["alice"], 2, "alice")
    cursor.executed.clear()

    assert db.getSqlPlayerIDs(["alice"], 2, "alice") == {"alice": 1}
    assert not cursor.executed


def test_two_names_cut_to_one_are_one_player_and_the_hero_if_either_is() -> None:
    cursor = _ScriptedCursor([])
    db = _postgres_host(cursor)
    long_name = "x" * 32

    ids = db.getSqlPlayerIDs([long_name + "1", long_name + "2"], 2, long_name + "2")

    assert ids == {long_name + "1": 1000, long_name + "2": 1000}
    assert cursor.batched[0][1] == [(long_name, 2, True, "XX")]


def test_tourney_entries_are_found_and_inserted_in_one_batch_each() -> None:
    cursor = _ScriptedCursor([(10, 50)])
    db = _postgres_host(cursor)
    hand = SimpleNamespace(
        players=[(1, "alice"), (2, "bob"), (3, "carol")],
        playerIds={"alice": 10, "bob": 11, "carol": 12},
        tourneyId=9,
        entryId=1,
    )

    assert db.getSqlTourneysPlayersIDs(hand) == {"alice": 50, "bob": 1000, "carol": 1001}
    assert cursor.executed == [("tourneysPlayersIdsByPlayers", (9, 1, [10, 11, 12]))]
    assert [row[:3] for row in cursor.batched[0][1]] == [(9, 11, 1), (9, 12, 1)]

    cursor.executed.clear()
    assert db.getSqlTourneysPlayersIDs(hand) == {"alice": 50, "bob": 1000, "carol": 1001}
    assert not cursor.executed


def test_tourney_entries_all_stored_insert_nothing() -> None:
    cursor = _ScriptedCursor([(10, 50)])
    db = _postgres_host(cursor)
    hand = SimpleNamespace(players=[(1, "alice")], playerIds={"alice": 10}, tourneyId=9, entryId=1)

    assert db.getSqlTourneysPlayersIDs(hand) == {"alice": 50}
    assert not cursor.batched


def _copying_host(cursor: _ScriptedCursor, bulk_path: Path) -> Database:
    db = _postgres_host(cursor)
    db.import_options = {"hhBulkPath": str(bulk_path)}
    return db


def test_a_bulk_path_loads_the_rows_with_copy_and_leaves_no_file(tmp_path: Path) -> None:
    written: list[str] = []

    class Cursor(_ScriptedCursor):
        def execute(self, query: str, params: Any = None) -> None:
            written.extend(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
            super().execute(query, params)

    cursor = Cursor()

    _copying_host(cursor, tmp_path).executemany(
        cursor, "insert into Hands (id, tableName) values (%s, %s)", [(1, "Alpha"), (2, "Beta")]
    )

    assert written == ["1\tAlpha\n2\tBeta\n"]
    assert len(cursor.executed) == 1
    assert cursor.executed[0][0].startswith("COPY Hands")
    assert not cursor.batched
    assert not list(tmp_path.iterdir())


def test_a_statement_copy_cannot_be_derived_from_is_refused(tmp_path: Path) -> None:
    cursor = _ScriptedCursor()

    with pytest.raises(FpdbError, match="COPY"):
        _copying_host(cursor, tmp_path).executemany(cursor, "UPDATE Hands SET id = %s", [(1,)])

    assert not cursor.executed
    assert not list(tmp_path.iterdir())


def test_without_a_bulk_path_rows_go_in_batches(tmp_path: Path) -> None:
    cursor = _ScriptedCursor()
    db = _copying_host(cursor, tmp_path)
    db.import_options["hhBulkPath"] = ""

    db.executemany(cursor, "INSERT INTO Hands (id) VALUES (%s)", [(1,), (2,)])

    assert [(query, rows) for query, rows, _returning in cursor.batched] == [
        ("INSERT INTO Hands (id) VALUES (%s)", [(1,), (2,)])
    ]
    assert not cursor.executed


def test_a_player_row_missing_a_column_is_not_stored_silently() -> None:
    cursor = _ScriptedCursor()
    db = _postgres_host(cursor)

    with pytest.raises(KeyError):
        db.storeHandsPlayers(1, {"alice": 10}, {"alice": {}})

    assert not db.hpbulk
