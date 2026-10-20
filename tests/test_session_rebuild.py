"""Rebuilding the session tables gives back what the import wrote (#598).

The import groups hands into Sessions, SessionsCache and TourneysCache as it
goes and nothing could regenerate them, so a repair that deleted hands left
their contribution behind. These tests import real hands with session caching
on, rebuild, and require every session table to match what the import wrote.

Row ids are not compared: a rebuild numbers its sessions afresh. Each session
is identified by its window, and every reference to one by that window.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_caches import SESSION_CACHE_KEYS
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

REPO = Path(__file__).resolve().parent.parent

# Cash Hold'em and 5 card Omaha on PokerStars, and an iPoker Twister SNG.
FILES = (
    REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt",
    REPO / "regression-test-files/cash/Stars/Flop/5-Card-PLO-6max-USD-3.00-6.00-201303.txt",
    REPO / "tests/fixtures/hands/ipoker/twister/twister_sng.txt",
)

SESSIONS = """SELECT s.id, s.sessionStart, s.sessionEnd, w.weekStart, m.monthStart
            FROM Sessions s
            INNER JOIN Weeks w ON (s.weekId = w.id)
            INNER JOIN Months m ON (s.monthId = m.id)"""
HAND_SESSIONS = "SELECT id, sessionId FROM Hands"
TOURNEY_SESSIONS = "SELECT id, sessionId FROM Tourneys"
SESSIONS_CACHE = "SELECT * FROM SessionsCache"
TOURNEYS_CACHE = "SELECT * FROM TourneysCache"
ORPHAN_WEEKS = "SELECT COUNT(*) FROM Weeks WHERE NOT EXISTS (SELECT 1 FROM Sessions s WHERE s.weekId = Weeks.id)"

# NUMERIC sums: SQLite adds REALs, so a different summation order may move the
# last digit.
FRACTIONAL = {"rakeDealt", "rakeContributed", "rakeWeighted", "allInEV"}


def _config(directory: Path):
    config = golden.build_config(directory)
    params = dict(config.get_import_parameters())
    params["cacheSessions"] = True
    config.get_import_parameters = lambda: params
    return config


def _import(directory: Path, files) -> None:
    directory.mkdir(exist_ok=True)
    config = _config(directory)
    Database(config).recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = Database(config)
    for path in files:
        importer.addImportFile(str(path), "auto")
    importer.runImport()


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp("rebuild598")
    _import(directory, FILES)
    return directory


@pytest.fixture
def database(imported, tmp_path) -> Database:
    target = tmp_path / "db"
    shutil.copytree(imported, target)
    return Database(_config(target))


def _fetch(db: Database, query: str) -> list[dict]:
    cursor = db.get_cursor()
    cursor.execute(query)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _cache(rows: list[dict], windows: dict, key: tuple[str, ...]) -> dict[tuple, dict]:
    cache = {}
    for row in rows:
        row = dict(row)
        row.pop("id")
        row["sessionId"] = windows.get(row["sessionId"])
        cache[tuple(row[column] for column in key)] = row
    return cache


def _snapshot(db: Database) -> dict[str, object]:
    windows = {row["id"]: (row["sessionStart"], row["sessionEnd"]) for row in _fetch(db, SESSIONS)}
    return {
        "Sessions": sorted(
            (row["sessionStart"], row["sessionEnd"], row["weekStart"], row["monthStart"])
            for row in _fetch(db, SESSIONS)
        ),
        "Hands": {row["id"]: windows.get(row["sessionId"]) for row in _fetch(db, HAND_SESSIONS)},
        "Tourneys": {row["id"]: windows.get(row["sessionId"]) for row in _fetch(db, TOURNEY_SESSIONS)},
        "SessionsCache": _cache(
            _fetch(db, SESSIONS_CACHE), windows, ("gametypeId", "playerId", "startTime", "endTime")
        ),
        "TourneysCache": _cache(_fetch(db, TOURNEYS_CACHE), windows, ("tourneyId", "playerId")),
    }


def _assert_same(rebuilt: dict[str, object], imported: dict[str, object]) -> None:
    for table in ("Sessions", "Hands", "Tourneys"):
        assert rebuilt[table] == imported[table], table
    for table in ("SessionsCache", "TourneysCache"):
        assert rebuilt[table].keys() == imported[table].keys(), table
        for key, row in imported[table].items():
            for column, value in row.items():
                other = rebuilt[table][key][column]
                if column in FRACTIONAL and value is not None:
                    assert float(other) == pytest.approx(float(value), abs=1e-9), (table, key, column)
                else:
                    assert other == value, (table, key, column, value, other)


def test_the_import_wrote_every_session_table(database) -> None:
    snapshot = _snapshot(database)

    assert snapshot["Sessions"]
    assert snapshot["SessionsCache"]
    assert snapshot["TourneysCache"]
    assert all(snapshot["Hands"].values()), "a hand without its session"
    assert all(snapshot["Tourneys"].values()), "a tournament without its session"


@pytest.mark.parametrize("batch", [500, 1], ids=["one-batch", "hand-by-hand"])
def test_a_rebuild_gives_back_what_the_import_wrote(database, batch) -> None:
    """Hand by hand, every session runs across batches and is merged through the database."""
    imported = _snapshot(database)

    database.rebuild_sessions(batch=batch)

    _assert_same(_snapshot(database), imported)


def test_hands_sharing_a_start_time_are_each_read_once(database) -> None:
    """The batches resume after the last (startTime, id) read, so ties across a batch boundary are kept."""
    cursor = database.get_cursor()
    cursor.execute(
        "UPDATE Hands SET startTime = (SELECT MIN(startTime) FROM Hands WHERE tourneyId IS NOT NULL) "
        "WHERE tourneyId IS NOT NULL"
    )
    database.commit()
    database.rebuild_sessions()
    whole = _snapshot(database)

    database.rebuild_sessions(batch=1)

    assert all(whole["Hands"].values()), "a hand the batches skipped"
    _assert_same(_snapshot(database), whole)


def test_a_rebuild_drops_what_no_hand_supports(database) -> None:
    imported = _snapshot(database)
    cursor = database.get_cursor()
    cursor.execute("UPDATE SessionsCache SET n = n + 7, totalProfit = totalProfit + 100")
    cursor.execute("UPDATE TourneysCache SET n = n + 7")
    cursor.execute("UPDATE Hands SET sessionId = NULL")
    database.commit()

    database.rebuild_sessions()

    _assert_same(_snapshot(database), imported)


def _split_twister(directory: Path) -> tuple[Path, Path]:
    """The Twister file cut in two, two hands each, as a client that rotates its logs writes it."""
    text = FILES[2].read_text(encoding="utf-8")
    header, games = text.split("<game ", 1)
    games = games.replace("</session>", "").strip()
    hands = ["<game " + game for game in games.split("<game ")]
    assert len(hands) == 4
    parts = []
    for name, chunk in (("part1.txt", hands[:2]), ("part2.txt", hands[2:])):
        path = directory / "ipoker" / "twister" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header + "".join(chunk) + "\n</session>\n", encoding="utf-8")
        parts.append(path)
    return parts[0], parts[1]


def test_a_tournament_spread_over_two_files_is_cached_whole(tmp_path) -> None:
    """The second file updates the tournament's TourneysCache row, which failed on SQLite."""
    _import(tmp_path / "whole", (FILES[2],))
    _import(tmp_path / "parts", _split_twister(tmp_path / "files"))
    whole = _snapshot(Database(_config(tmp_path / "whole")))
    parts = _snapshot(Database(_config(tmp_path / "parts")))

    assert len(parts["Hands"]) == 4
    assert [row["n"] for row in parts["TourneysCache"].values()] == [4] * len(parts["TourneysCache"])
    _assert_same(parts, whole)


def test_an_uncommitted_rebuild_can_be_rolled_back(database) -> None:
    imported = _snapshot(database)
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Hands WHERE tourneyId IS NOT NULL")
    cursor.execute("DELETE FROM HandsPlayers WHERE handId NOT IN (SELECT id FROM Hands)")

    database.rebuild_sessions(commit=False)
    assert not _snapshot(database)["TourneysCache"]
    database.rollback()

    _assert_same(_snapshot(database), imported)


def test_the_rebuild_leaves_no_orphan_week(database) -> None:
    cursor = database.get_cursor()
    cursor.execute("INSERT INTO Weeks (weekStart) VALUES ('1999-01-04 00:00:00')")
    database.commit()

    database.rebuild_session_caches()

    cursor.execute(ORPHAN_WEEKS)
    assert cursor.fetchone() == (0,)


def test_every_session_key_is_rebuilt() -> None:
    from fpdb_3_legacy.session_rebuild import DERIVED_KEYS, STORED_KEYS

    assert set(STORED_KEYS) | set(DERIVED_KEYS) == set(SESSION_CACHE_KEYS)
