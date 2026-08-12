"""The first hand of a Fast-Fold table must show statistics, not empty blocks.

A table built from the client log exists before any of its hands has been
imported: the log names it within milliseconds, the hand history arrives
seconds to minutes later. Its first seat update therefore had no hand to take
a gametypeId from, and ``get_player_stats_for_seat_map`` skips the statistics
query outright when that id is None -- so every block came up with the
player's name and nothing else. The log said so plainly and was ignored::

    00:18:49  stats-applied table=Bucarest 3 #61825 players=5 with_history=0
    00:18:56  FF import applied: hand=939 ...
    00:19:36  stats-applied table=Bucarest 3 #61825 players=6 with_history=6

The pool has been played before, so its own last imported hand answers what
game it deals. That lookup is keyed on the site's *name*, because the site id
is itself read off an imported hand -- the thing that is missing.
"""

from __future__ import annotations

import os
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Configuration, HUD_main
from fpdb_3_legacy.fast_fold_engine import FastFoldEngine, FastFoldStatsRequest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_TEMPLATE = os.path.join(REPO_ROOT, "HUD_config.xml")

HAND_COLUMNS = (
    "tableName,siteHandNo,gametypeId,fileId,startTime,importTime,seats,heroSeat,maxPosition,"
    "playersVpi,playersAtStreet1,playersAtStreet2,playersAtStreet3,playersAtStreet4,"
    "playersAtShowdown,street0Raises,street1Raises,street2Raises,street3Raises,street4Raises"
)
HAND_VALUES = "6,4,-1,0,0,0,0,0,0,0,0,0,0,0"


# --------------------------------------------------------------------------
# The pool name a HUD key is built from
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("temp_key", "expected"),
    [
        ("Bucarest 3 #61825", "Bucarest"),  # pool + client index + native window
        ("Casablanca 5", "Casablanca"),  # pool + client index, no window yet
        ("Colorado", "Colorado"),  # bare pool
        ("Bucarest 12 #7", "Bucarest"),  # multi-digit index
    ],
)
def test_pool_name_strips_the_hud_key_suffixes(temp_key: str, expected: str) -> None:
    """Hands are written under the bare pool name; the HUD key carries more."""
    assert HUD_main.HudMain._pool_name(temp_key) == expected


# --------------------------------------------------------------------------
# The lookup, against a real database
# --------------------------------------------------------------------------


@pytest.fixture
def database(tmp_path):
    """A real SQLite database with the shipped schema, and nothing else."""
    from fpdb_3_legacy import SQL, Database

    config_path = tmp_path / "HUD_config.xml"
    shutil.copy(CONFIG_TEMPLATE, config_path)
    config = Configuration.Config(file=str(config_path))
    config.dir_database = str(tmp_path)
    config.add_db_parameters(db_name="fast_fold.db3", db_server="sqlite")
    config.db_selected = "fast_fold.db3"
    db = Database.Database(config, sql=SQL.Sql(db_server="sqlite"))
    yield db
    db.disconnect()


def _add_hand(db, site: str, table_name: str) -> int:
    """Write one hand of ``table_name`` and return its gametypeId."""
    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM Sites WHERE name = ?", (site,))
    site_id = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO Gametypes (siteId, currency, type, base, category, limitType, hiLo, mix, "
        "smallBlind, bigBlind, smallBet, bigBet, maxSeats, ante, buyinType, fast, newToGame, "
        "homeGame, split) VALUES (?,'EUR','ring','hold','omahahi','pl','h','none',1,2,0,0,6,0,"
        "'regular',1,0,0,0)",
        (site_id,),
    )
    gametype_id = cursor.lastrowid
    cursor.execute(
        f"INSERT INTO Hands ({HAND_COLUMNS}) VALUES (?,?,?,1,'2026-08-12 00:00:00',"  # noqa: S608 - fixed column list
        f"'2026-08-12 00:00:00',{HAND_VALUES})",
        (table_name, f"hand-{table_name}-{gametype_id}", gametype_id),
    )
    db.commit()
    return gametype_id


def test_the_pools_own_last_hand_answers_the_gametype(database) -> None:
    """The lookup finds what this pool deals, with no hand of the table's own."""
    gametype_id = _add_hand(database, "Winamax", "Bucarest")

    assert database.get_last_gametype_id_for_table("Winamax", "Bucarest") == gametype_id


def test_the_newest_hand_of_the_pool_wins(database) -> None:
    """A pool that changed stakes must report what it deals now."""
    _add_hand(database, "Winamax", "Bucarest")
    newest = _add_hand(database, "Winamax", "Bucarest")

    assert database.get_last_gametype_id_for_table("Winamax", "Bucarest") == newest


def test_another_pool_is_not_borrowed_from(database) -> None:
    """Guessing another pool's stakes would be worse than showing nothing."""
    _add_hand(database, "Winamax", "Bucarest")

    assert database.get_last_gametype_id_for_table("Winamax", "Casablanca") is None


def test_another_site_is_not_borrowed_from(database) -> None:
    """Two sites can run a pool of the same name."""
    _add_hand(database, "Winamax", "Bucarest")

    assert database.get_last_gametype_id_for_table("PokerStars", "Bucarest") is None


def test_a_pool_never_played_before_returns_nothing(database) -> None:
    """First ever session on a pool: no answer is the honest one."""
    assert database.get_last_gametype_id_for_table("Winamax", "Bucarest") is None


@pytest.mark.parametrize(("site", "table"), [("", "Bucarest"), ("Winamax", ""), (None, None)])
def test_missing_identity_is_not_queried(database, site, table) -> None:
    """An unknown site or table must not turn into a wildcard query."""
    assert database.get_last_gametype_id_for_table(site, table) is None


# --------------------------------------------------------------------------
# The worker uses it, and only when it has to
# --------------------------------------------------------------------------


def _worker_stats(request: FastFoldStatsRequest, database) -> tuple[object, list]:
    """Run the worker's read for one request, capturing the gametypeId used."""
    used: list = []

    def capture(_seat_map, **kwargs):
        used.append(kwargs.get("gametype_id"))
        return {}

    engine = MagicMock()
    engine.get_player_stats_for_seat_map.side_effect = capture
    original = HUD_main.FastFoldEngine
    HUD_main.FastFoldEngine = MagicMock(return_value=engine)
    try:
        result = HUD_main.HudReadWorker._read_fast_fold_stats(database, request)
    finally:
        HUD_main.FastFoldEngine = original
    return result, used


def _database_stub(*, gameinfo=None, pool_gametype=None):
    database = MagicMock()
    database.get_gameinfo_from_hid.return_value = gameinfo
    database.get_last_gametype_id_for_table.return_value = pool_gametype
    return database


def test_a_table_with_no_hand_falls_back_to_its_pool() -> None:
    """The first update of a log-built table must still read statistics."""
    database = _database_stub(pool_gametype=77)
    request = FastFoldStatsRequest(
        temp_key="Bucarest 3 #61825",
        seat_map={4: "jejellyroll"},
        hand_id=None,
        site_name="Winamax",
        pool_name="Bucarest",
    )

    _result, used = _worker_stats(request, database)

    database.get_last_gametype_id_for_table.assert_called_once_with("Winamax", "Bucarest")
    assert used == [77]


def test_a_table_with_a_hand_does_not_query_the_pool() -> None:
    """The table's own hand is the better answer, and costs one round trip."""
    database = _database_stub(gameinfo={"gametypeId": 42}, pool_gametype=77)
    request = FastFoldStatsRequest(
        temp_key="Bucarest 3 #61825",
        seat_map={4: "jejellyroll"},
        hand_id=939,
        site_name="Winamax",
        pool_name="Bucarest",
    )

    _result, used = _worker_stats(request, database)

    database.get_last_gametype_id_for_table.assert_not_called()
    assert used == [42]


def test_a_hand_not_committed_yet_falls_back_to_the_pool() -> None:
    """A hand id whose row has not landed must not lose the statistics."""
    database = _database_stub(gameinfo=None, pool_gametype=77)
    request = FastFoldStatsRequest(
        temp_key="Bucarest 3 #61825",
        seat_map={4: "jejellyroll"},
        hand_id=939,
        site_name="Winamax",
        pool_name="Bucarest",
    )

    _result, used = _worker_stats(request, database)

    assert used == [77]


@pytest.mark.parametrize(("site_name", "pool_name"), [("", "Bucarest"), ("Winamax", ""), ("", "")])
def test_an_unidentified_table_is_not_guessed_at(site_name: str, pool_name: str) -> None:
    """Without a pool to ask about, the worker must not ask anything.

    Empty blocks on a table nobody can name are honest. Borrowing whatever
    gametype a query without a WHERE clause returned would put another
    table's stakes on this one's players.
    """
    database = _database_stub(pool_gametype=77)
    request = FastFoldStatsRequest(
        temp_key="Winamax Escape 1",
        seat_map={4: "jejellyroll"},
        hand_id=None,
        site_name=site_name,
        pool_name=pool_name,
    )

    _result, used = _worker_stats(request, database)

    database.get_last_gametype_id_for_table.assert_not_called()
    assert used == [None]


def test_a_failing_fallback_does_not_take_the_read_down() -> None:
    """No gametype is a table with empty blocks; an exception is no table."""
    database = _database_stub()
    database.get_last_gametype_id_for_table.side_effect = RuntimeError("no such column")
    request = FastFoldStatsRequest(
        temp_key="Bucarest 3 #61825",
        seat_map={4: "jejellyroll"},
        hand_id=None,
        site_name="Winamax",
        pool_name="Bucarest",
    )

    result, used = _worker_stats(request, database)

    assert used == [None]
    assert result.temp_key == "Bucarest 3 #61825"


# --------------------------------------------------------------------------
# The request the GUI thread builds carries what the fallback needs
# --------------------------------------------------------------------------


def test_a_gametype_of_none_yields_no_statistics() -> None:
    """Why the fallback matters: this is what the reported screen was.

    Every seat comes back named and empty, which is exactly ``with_history=0``
    in the trace.
    """
    connection = MagicMock()
    engine = FastFoldEngine(db_connection=connection)
    engine._resolve_player_ids = MagicMock(return_value={"jejellyroll": 1, "Slevink888": 2})

    stat_dict = engine.get_player_stats_for_seat_map(
        {4: "jejellyroll", 5: "Slevink888"},
        db_conn=connection,
        gametype_id=None,
    )

    connection.get_stats_for_players.assert_not_called()
    assert sorted(row["screen_name"] for row in stat_dict.values()) == ["Slevink888", "jejellyroll"]
    assert all(row["n"] == 0 for row in stat_dict.values())


def test_the_request_carries_the_site_and_pool() -> None:
    """The worker can only fall back on what the GUI thread sent it."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main._ff_pending_hand = {}
    hud_main._ff_pending_request = {}
    hud_main._ff_pending_generation = {}
    hud_main._ff_request_sequence = 0
    hud_main._ff_trace = MagicMock()
    hud_main._fast_fold_pending = {}
    hud_main._stats_reference_hand = MagicMock(return_value=None)
    submitted: list[FastFoldStatsRequest] = []
    hud_main._db_worker = SimpleNamespace(submit=submitted.append)

    hud = MagicMock()
    hud.max = 6
    hud.table.site = "Winamax"
    hud.table.number = 61825
    hud._fpdb_generation = 1

    HUD_main.HudMain._request_fast_fold_stats(
        hud_main,
        temp_key="Bucarest 3 #61825",
        hud=hud,
        seat_map={4: "jejellyroll"},
        hand_id="live:1",
    )

    assert len(submitted) == 1
    assert submitted[0].site_name == "Winamax"
    assert submitted[0].pool_name == "Bucarest"
