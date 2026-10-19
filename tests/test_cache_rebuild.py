"""Rebuilding a statistics cache gives back what the import wrote (#591).

The rebuild aggregates HandsPlayers with one INSERT ... SELECT whose column
lists used to be written by hand and fell behind the keys the import writes,
so a rebuild zeroed 138 HudCache columns and street0FaceRaise everywhere. The
lists are now generated from those keys; these tests import real hands, rebuild
each cache and require the rows the import wrote.
"""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from fpdb_3_legacy.action_enum_stats import CACHE_KEYS as ACTION_ENUM_CACHE_KEYS
from fpdb_3_legacy.cache_rebuild import rebuild_stat_columns
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_caches import CACHE_KEYS, HUDCACHE_EXTRA_KEYS, SESSION_CACHE_KEYS, DatabaseCachesMixin
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

REPO = Path(__file__).resolve().parent.parent

# Cash Hold'em and 5 card Omaha on PokerStars, and an iPoker Twister SNG.
FILES = (
    REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt",
    REPO / "regression-test-files/cash/Stars/Flop/5-Card-PLO-6max-USD-3.00-6.00-201303.txt",
    REPO / "tests/fixtures/hands/ipoker/twister/twister_sng.txt",
)

SELECT_ROWS = {
    "HudCache": "SELECT * FROM HudCache",
    "CardsCache": "SELECT * FROM CardsCache",
    "PositionsCache": "SELECT * FROM PositionsCache",
}
KEY_COLUMNS = {
    "HudCache": ("gametypeId", "playerId", "seats", "position", "tourneyTypeId", "styleKey"),
    "CardsCache": ("weekId", "monthId", "gametypeId", "tourneyTypeId", "playerId", "startCards"),
    "PositionsCache": (
        "weekId",
        "monthId",
        "gametypeId",
        "tourneyTypeId",
        "playerId",
        "seats",
        "maxPosition",
        "position",
    ),
}
# NUMERIC sums: SQLite adds REALs, so a different summation order may move the
# last digit.
FRACTIONAL = {"rakeDealt", "rakeContributed", "rakeWeighted", "allInEV"}


def _config(directory: Path):
    config = golden.build_config(directory)
    params = dict(config.get_import_parameters())
    params["cacheSessions"] = True
    config.get_import_parameters = lambda: params
    return config


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp("rebuild591")
    config = _config(directory)
    Database(config).recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = Database(config)
    for path in FILES:
        importer.addImportFile(str(path), "auto")
    importer.runImport()
    return directory


@pytest.fixture
def database(imported, tmp_path) -> Database:
    target = tmp_path / "db"
    shutil.copytree(imported, target)
    return Database(_config(target))


def _rows(db: Database, table: str) -> dict[tuple, dict]:
    cursor = db.get_cursor()
    cursor.execute(SELECT_ROWS[table])
    columns = [description[0] for description in cursor.description]
    rows = {}
    for values in cursor.fetchall():
        row = dict(zip(columns, values, strict=True))
        row.pop("id")
        rows[tuple(row[key] for key in KEY_COLUMNS[table])] = row
    return rows


def _assert_same_rows(rebuilt: dict[tuple, dict], imported: dict[tuple, dict]) -> None:
    assert rebuilt.keys() == imported.keys()
    for key, row in imported.items():
        for column, value in row.items():
            other = rebuilt[key][column]
            if column in FRACTIONAL and value is not None:
                assert float(other) == pytest.approx(float(value), abs=1e-9), (key, column)
            else:
                assert other == value, (key, column, value, other)


@pytest.mark.parametrize("table", ["HudCache", "CardsCache", "PositionsCache"])
@pytest.mark.parametrize("dates", [(None, None), ("1970-01-01", "1970-01-01")], ids=["all-hands", "from-a-date"])
def test_a_rebuild_gives_back_what_the_import_wrote(database, table, dates) -> None:
    imported = _rows(database, table)
    assert imported, "the import wrote nothing to compare with"

    database.rebuild_cache(dates[0], dates[1], table)

    _assert_same_rows(_rows(database, table), imported)


def test_the_hud_counters_survive_a_rebuild(database) -> None:
    """The columns the old hand-written lists left out are not all zero to begin with."""
    imported = _rows(database, "HudCache")
    database.rebuild_cache(None, None, "HudCache")
    rebuilt = _rows(database, "HudCache")

    for column in ("street0FaceRaise", "amt_blind", "cnt_f_spr", "showdownWinnings"):
        total = sum(row[column] or 0 for row in imported.values())
        assert total, column
        assert sum(row[column] or 0 for row in rebuilt.values()) == total


@pytest.mark.parametrize("server", ["sqlite", "postgresql", "mysql"])
def test_every_key_the_import_writes_can_be_rebuilt(server) -> None:
    for keys in ([*CACHE_KEYS, *HUDCACHE_EXTRA_KEYS], SESSION_CACHE_KEYS):
        insert, select = rebuild_stat_columns(server, keys)
        assert insert.count(",") == select.count("\n") == len(keys)


def test_a_key_the_rebuild_cannot_compute_is_refused() -> None:
    with pytest.raises(ValueError, match="notAColumn"):
        rebuild_stat_columns("sqlite", ["n", "notAColumn"])


def test_postgresql_sums_booleans_as_integers() -> None:
    _insert, select = rebuild_stat_columns("postgresql", ["street0VPI", "totalProfit"])

    assert "sum(CAST(hp.street0VPI AS integer))" in select
    assert "sum(hp.totalProfit)" in select


def test_the_action_enum_counters_follow_the_import() -> None:
    """faced counts F, C and R, as action_enum_stats.derive_counters does."""
    faced = next(key for key in ACTION_ENUM_CACHE_KEYS if key.startswith("cnt_p_face_"))
    _insert, select = rebuild_stat_columns("sqlite", [faced])

    assert "in ('F', 'C', 'R')" in select


TWISTER_DAYS = "SELECT DISTINCT styleKey FROM HudCache WHERE tourneyTypeId IS NOT NULL ORDER BY styleKey"


def test_a_rebuild_puts_hands_near_midnight_in_the_import_s_day(tmp_path, monkeypatch) -> None:
    """HudCache buckets a hand into the player's day: UTC start minus day_start and the UTC offset.

    The Twister hands start at 00:57 UTC; moved back one hour they belong to the
    day before, as the import files them. The rebuild used to take the UTC date
    and moved them to the next day. The offset is pinned rather than read off the
    machine's time zone, so the check is the same on every runner.
    """
    monkeypatch.setattr(DatabaseCachesMixin, "hud_day_offset", lambda _self: timedelta(hours=1))
    config = _config(tmp_path)
    Database(config).recreate_tables()
    db = Database(config)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    importer.addImportFile(str(FILES[2]), "auto")
    importer.runImport()
    database = Database(config)
    imported = _rows(database, "HudCache")
    cursor = database.get_cursor()
    cursor.execute(TWISTER_DAYS)
    assert cursor.fetchall() == [("d140406",)]

    database.rebuild_cache(None, None, "HudCache")

    _assert_same_rows(_rows(database, "HudCache"), imported)
