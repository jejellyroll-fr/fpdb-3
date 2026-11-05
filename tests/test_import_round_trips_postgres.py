"""The PostgreSQL batches of a bulk import, against a live server (#705).

Skipped unless FPDB_TEST_DATABASES names postgresql, like the other live tests.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

import pytest

from fpdb_3_legacy import db_profile
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.test_database_backend_integration import _connection, _enabled_backends, _reset_schema
from tools import benchmark_import

REPO = Path(__file__).resolve().parent.parent
TOURNAMENT = "NLHE-2max-USD-0-STT-201307.Microgaming.txt"
HAND_FILE = REPO / "regression-test-files/tour/PokerTracker/Flop" / TOURNAMENT
SUMMARY_FILE = REPO / "regression-test-files/summaries/PokerTracker" / TOURNAMENT
CASH_FILE = REPO / "regression-test-files/cash/PokerTracker/Flop/NLHE-USD-0.50-1.00-201101.Merge.txt"

pytestmark = pytest.mark.integration


@pytest.fixture
def config(tmp_path: Path, monkeypatch) -> Iterator[Config]:
    if "postgresql" not in _enabled_backends():
        pytest.skip("live postgresql service not requested")
    monkeypatch.setenv(db_profile.ENV_FLAG, "1")
    with _connection("postgresql") as connection:
        _reset_schema(connection, "postgresql")
    shutil.copyfile(REPO / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "postgresql",
            "db-backend": Database.PGSQL,
            "db-databaseName": os.environ.get("FPDB_POSTGRES_DB", "fpdb"),
            "db-host": os.environ.get("FPDB_POSTGRES_HOST", "127.0.0.1"),
            "db-port": int(os.environ.get("FPDB_POSTGRES_PORT", "5432")),
            "db-user": os.environ.get("FPDB_POSTGRES_USER", "fpdb"),
            "db-password": os.environ.get("FPDB_POSTGRES_PASSWORD", "fpdb"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    yield config
    db_profile.get_profile().reset()


@pytest.fixture
def db(config: Config) -> Iterator[Database]:
    database = Database(config)
    database.resetBulkCache()
    yield database
    database.rollback()
    database.close_connection()


def _statements(label: str) -> int:
    stats = db_profile.get_profile().by_statement.get(label)
    return stats.calls if stats is not None else 0


def _players(db: Database) -> dict[str, tuple[Any, ...]]:
    c = db.get_cursor()
    c.execute("SELECT name, id, hero, chars FROM Players WHERE siteId = 2")
    return {row[0]: tuple(row[1:]) for row in c.fetchall()}


def _import(config: Config, files: list[Path]) -> tuple[int, int]:
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    importer.set_progress_callbacks(lambda _total: None, lambda _path, _count: None, lambda: None)
    for path in files:
        importer.addImportFile(str(path), "auto")
    stored, duplicates, *_rest = importer.runImport()
    importer.close()
    return stored, duplicates


def test_an_import_asks_per_file_not_per_hand(config: Config) -> None:
    profile = db_profile.get_profile()
    profile.reset()

    stored, duplicates = _import(config, [CASH_FILE, HAND_FILE, SUMMARY_FILE])

    assert stored > 10
    assert duplicates == 0
    assert _statements("select lastval()") == 0
    assert _statements("isAlreadyInDB (assembled)") == 0
    assert _statements("hands_already_stored") == 2
    assert _statements("getHandCount") == 1
    assert _statements("getSettings") == 1, "one connection: the importer's own, never a reconnection per file"


def test_importing_twice_stores_each_hand_once(config: Config) -> None:
    stored, _duplicates = _import(config, [CASH_FILE, HAND_FILE])
    profile = db_profile.get_profile()
    profile.reset()

    stored_again, duplicates = _import(config, [CASH_FILE, HAND_FILE])

    assert stored > 0
    assert stored_again == 0
    assert duplicates == stored
    assert _statements("isAlreadyInDB (assembled)") == 0


def test_a_hand_another_importer_commits_before_the_lock_counts_as_a_duplicate(config: Config, monkeypatch) -> None:
    """The other importer holds the hand-id lock until it commits, so nextHandId is where to wait for it."""
    _import(config, [CASH_FILE])
    with _connection("postgresql") as other:
        cursor = other.cursor()
        # Hide the file's hands behind other numbers: the import sees them as new.
        cursor.execute("UPDATE Hands SET siteHandNo = siteHandNo + 1000000")
        other.commit()

        importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
        importer.setCallHud(False)
        importer.set_progress_callbacks(lambda _total: None, lambda _path, _count: None, lambda: None)
        importer.addImportFile(str(CASH_FILE), "auto")
        next_hand_id = importer.database.nextHandId

        def the_other_importer_commits_first() -> Any:
            cursor.execute("UPDATE Hands SET siteHandNo = siteHandNo - 1000000")
            other.commit()
            return next_hand_id()

        monkeypatch.setattr(importer.database, "nextHandId", the_other_importer_commits_first)
        stored, duplicates, _partial, _skipped, errors, *_rest = importer.runImport()
        importer.close()

    assert errors == 0
    assert stored == 0
    assert duplicates > 0


@pytest.mark.usefixtures("config")
def test_the_benchmark_delay_reaches_every_connection() -> None:
    """A loopback host tries the default socket first: --rtt-ms must hold there too."""
    server = benchmark_import.PostgresServer(
        os.environ.get("FPDB_POSTGRES_HOST", "127.0.0.1"),
        int(os.environ.get("FPDB_POSTGRES_PORT", "5432")),
        os.environ.get("FPDB_POSTGRES_USER", "fpdb"),
        os.environ.get("FPDB_POSTGRES_PASSWORD", "fpdb"),
    )
    rtt_ms = 40.0
    import psycopg

    with benchmark_import._delayed(server, rtt_ms) as reachable, benchmark_import._default_connection(reachable):
        # The call Database makes first for a loopback host, with no host or port.
        with psycopg.connect(dbname="postgres", autocommit=True) as connection:
            started = perf_counter()
            connection.execute("SELECT 1")
            elapsed = perf_counter() - started

    assert elapsed >= rtt_ms / 1000.0


def test_a_summary_reads_its_entries_once(config: Config) -> None:
    _import(config, [HAND_FILE, SUMMARY_FILE])
    profile = db_profile.get_profile()
    profile.reset()

    _import(config, [SUMMARY_FILE])

    assert _statements("getTourneysPlayersByIds") == 0
    assert _statements("getTourneysPlayersByTourney") == 1


def test_players_are_found_and_created_in_one_batch(db: Database) -> None:
    alice = db.getSqlPlayerIDs(["alice"], 2, "someone else")["alice"]
    db.commit()
    profile = db_profile.get_profile()
    profile.reset()

    ids = db.getSqlPlayerIDs(["alice", "bob", "1carol", "d", "alice"], 2, "bob")

    assert ids["alice"] == alice
    assert len({ids["alice"], ids["bob"], ids["1carol"], ids["d"]}) == 4
    stored = _players(db)
    assert stored["bob"] == (ids["bob"], True, "BO ")
    assert stored["1carol"] == (ids["1carol"], False, "123")
    assert stored["d"] == (ids["d"], False, "D1 ")
    assert _statements("players_by_names") == 1
    assert _statements("select lastval()") == 0


def test_a_batch_gives_a_stored_player_the_hero_flag_and_keeps_their_id(db: Database) -> None:
    alice = db.getSqlPlayerIDs(["alice"], 2, "someone else")["alice"]
    assert _players(db)["alice"][1] is False

    assert db.getSqlPlayerIDs(["alice"], 2, "alice")["alice"] == alice

    assert _players(db)["alice"] == (alice, True, "AL ")


def test_names_cut_to_the_same_length_are_one_player(db: Database) -> None:
    long_name = "x" * 32
    ids = db.getSqlPlayerIDs([long_name + "1", long_name + "2"], 2, long_name + "2")

    assert ids[long_name + "1"] == ids[long_name + "2"]
    assert _players(db)[long_name][1] is True


def test_players_a_batch_has_seen_cost_nothing_more(db: Database) -> None:
    db.getSqlPlayerIDs(["alice", "bob"], 2, "alice")
    profile = db_profile.get_profile()
    profile.reset()

    db.getSqlPlayerIDs(["alice", "bob"], 2, "alice")

    assert profile.total.calls == 0


def _hand(site_hand_no: Any, *, public: bool = False, seat: int = 1) -> SimpleNamespace:
    return SimpleNamespace(siteId=2, publicDB=public, hands={"siteHandNo": site_hand_no, "heroSeat": seat})


def _stored_hand(config: Config) -> tuple[int, int]:
    """A real hand's number and site, stored by a real import."""
    _import(config, [CASH_FILE])
    database = Database(config)
    c = database.get_cursor()
    c.execute("SELECT H.siteHandNo, G.siteId FROM Hands H JOIN Gametypes G ON G.id = H.gametypeId LIMIT 1")
    number, site = c.fetchone()
    database.rollback()
    database.close_connection()
    return number, site


def test_the_batch_answers_for_stored_and_unknown_hands(config: Config, db: Database) -> None:
    number, site = _stored_hand(config)
    stored, unknown = _hand(str(number)), _hand("123456789")
    stored.siteId = unknown.siteId = site
    db.preload_duplicate_check([stored, unknown])
    profile = db_profile.get_profile()
    profile.reset()

    assert db.isDuplicate(site, str(number), 1, False) is True
    assert db.isDuplicate(site, "123456789", 1, False) is False
    # The same hand twice in a file.
    assert db.isDuplicate(site, "123456789", 1, False) is True
    assert profile.total.calls == 0


def test_a_hand_number_the_column_cannot_hold_is_left_to_its_own_query(db: Database) -> None:
    too_big = str(2**64)

    db.preload_duplicate_check([_hand(too_big), _hand("not a number"), _hand("7")])

    assert db.known_hands == {("7", 2): False}


def test_public_databases_also_compare_the_hero_seat(config: Config, db: Database) -> None:
    number, site = _stored_hand(config)
    c = db.get_cursor()
    c.execute("SELECT heroSeat FROM Hands WHERE siteHandNo = %s", (number,))
    seat = c.fetchone()[0]
    same, other = _hand(number, public=True, seat=seat), _hand(number, public=True, seat=seat + 1)
    same.siteId = other.siteId = site

    db.preload_duplicate_check([same, other])

    assert db.known_hands == {(number, site, seat): True, (number, site, seat + 1): False}


def test_a_new_row_gets_its_id_from_the_insert(db: Database) -> None:
    profile = db_profile.get_profile()
    profile.reset()
    c = db.get_cursor()
    query = "INSERT INTO Players (name, siteId, hero, chars) VALUES (%s, %s, %s, %s)"

    one = db.insert_returning_id(c, query, ("alice", 2, False, "AL"))
    several = db.insert_many_returning_ids(c, query, [("bob", 2, False, "BO"), ("carol", 2, False, "CA")])

    stored = _players(db)
    assert stored["alice"][0] == one
    assert [stored["bob"][0], stored["carol"][0]] == several
    assert _statements("select lastval()") == 0
