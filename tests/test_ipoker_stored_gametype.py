"""Hands are stored under the game they were played at (#592).

Two bugs made iPoker hands land under the wrong gametype:

* every hand after the first of a 5 card Omaha session lost its game name and
  was classified from the file name instead, which created a second gametype
  for one table (fixed in iPoker/xml_format.py);
* with session caching on, appendHandsSessionIds wrote each hand's session id
  into the gametypeId column of the queued Hands row and left sessionId empty
  -- for every site, not only iPoker (fixed in database_caches.py).

The second one only shows when session ids and gametype ids differ, which a
fresh database with one session per file hides; the session table is
therefore seeded so that they cannot coincide.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import SQL
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_caches import HANDS_ROW_SESSION_ID, HANDS_ROW_TOURNEY_ID, DatabaseCachesMixin
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

REPO = Path(__file__).resolve().parent.parent

FILES = (
    REPO / "regression-test-files/cash/iPoker/Flop/5CPLO-EUR-2.00-4.00-201905.txt",
    REPO / "regression-test-files/cash/iPoker/Flop/NLHE-EUR-0.01-0.02-201701.new.datetime.format.txt",
    REPO / "tests/fixtures/hands/ipoker/twister/twister_sng.txt",
)

# What each hand was played at: (type, category, limitType, smallBlind, bigBlind).
EXPECTED = {
    3422554295: ("ring", "5_omahahi", "pl", 200, 400),
    3422554305: ("ring", "5_omahahi", "pl", 200, 400),
    3858162574: ("ring", "holdem", "nl", 1, 2),
    3858162748: ("ring", "holdem", "nl", 1, 2),
    3858162919: ("ring", "holdem", "nl", 1, 2),
    5631758947: ("tour", "holdem", "nl", None, None),
    5631759012: ("tour", "holdem", "nl", None, None),
    5631759050: ("tour", "holdem", "nl", None, None),
    5631759065: ("tour", "holdem", "nl", None, None),
}

SEED_SESSION = (
    "INSERT INTO Sessions (id, weekId, monthId, sessionStart, sessionEnd) "
    "VALUES (100, NULL, NULL, '2000-01-01 00:00:00', '2000-01-01 00:00:00')"
)
STORED_HANDS = (
    "SELECT h.siteHandNo, g.type, g.category, g.limitType, g.smallBlind, g.bigBlind, h.sessionId "
    "FROM Hands h LEFT JOIN Gametypes g ON g.id = h.gametypeId ORDER BY h.siteHandNo"
)


def _import(tmp_path: Path, *, cache_sessions: bool):
    config = golden.build_config(tmp_path)
    params = dict(config.get_import_parameters())
    params["cacheSessions"] = cache_sessions
    config.get_import_parameters = lambda: params
    Database(config).recreate_tables()

    db = Database(config)
    db.get_cursor().execute(SEED_SESSION)
    db.commit()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in FILES:
        importer.addImportFile(str(path), "auto")
    importer.runImport()

    reader = Database(config)
    cursor = reader.get_cursor()
    cursor.execute(STORED_HANDS)
    return cursor.fetchall()


@pytest.mark.parametrize("cache_sessions", [False, True], ids=["no-session-cache", "session-cache"])
def test_each_ipoker_hand_is_stored_under_its_own_game(tmp_path, cache_sessions) -> None:
    rows = _import(tmp_path, cache_sessions=cache_sessions)

    stored = {}
    for site_hand_no, game_type, category, limit_type, small_blind, big_blind, _session in rows:
        blinds = (small_blind, big_blind) if game_type == "ring" else (None, None)
        stored[int(site_hand_no)] = (game_type, category, limit_type, *blinds)
    assert stored == EXPECTED


def test_session_caching_records_each_hands_session(tmp_path) -> None:
    rows = _import(tmp_path, cache_sessions=True)

    assert [row[0] for row in rows if row[-1] is None] == []
    assert all(row[-1] > 100 for row in rows)


@pytest.mark.parametrize("server", ["sqlite", "postgresql", "mysql"])
def test_the_row_positions_follow_the_store_hand_columns(server) -> None:
    query = SQL.Sql(db_server=server).query["store_hand"]
    column_list = re.search(r"\(([^)]*)\)", query)
    assert column_list is not None
    columns = [name.strip().lower() for name in column_list.group(1).split(",")]

    assert columns[HANDS_ROW_TOURNEY_ID] == "tourneyid"
    assert columns[HANDS_ROW_SESSION_ID] == "sessionid"


def test_the_session_id_goes_to_the_session_column() -> None:
    row = [7, "Table", 123456, 42, 3, None, 1]
    queue = SimpleNamespace(hbulk=[row], hids=[7], s={7: {"id": 55}}, tbulk={})

    DatabaseCachesMixin.appendHandsSessionIds(queue)

    assert row[HANDS_ROW_SESSION_ID] == 55
    assert row[4] == 3, "the gametype must be left alone"
    assert queue.tbulk == {42: 55}
