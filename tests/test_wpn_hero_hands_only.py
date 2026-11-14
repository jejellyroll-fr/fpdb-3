"""ACR / WPN: HUD statistics from the user's own hands only (#719).

ACR Poker's Security & Game Integrity Policies, section 4.1.3, permit HUD
statistics only when they come from hands the player took part in, and nothing
from the hand in play. fpdb's HUD reads ``HudCache``, an aggregate per player
that cannot be filtered per hand when it is queried, so the rule is applied
where hands enter it: a WPN hand stored without the hero at the table
(``Hands.heroSeat = 0`` -- an imported archive, someone else's history) stays in
the database but feeds neither the cache at import nor its rebuild.

The hand in play never reaches the HUD at these tables: their statistics come
from imported, completed hands, and the WPN policy allows no live context.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import hud_room_policy as policy
from fpdb_3_legacy.Hand import Hand

ROOT = Path(__file__).resolve().parents[1]
WPN_HAND = next((ROOT / "regression-test-files/cash/Winning/Flop").glob("6+Holdem-6-max-USD-0.02-0.05-201902*.txt"))
WPN_SITES = ("WinningPoker", "Americas Cardroom", "ACR Poker", "BlackChipPoker", "TruePoker", "Ya Poker")


# ---------------------------------------------------------------------------
# The room policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("site", WPN_SITES)
def test_every_wpn_skin_gets_the_acr_policy(site) -> None:
    assert policy.network_of(site) == "wpn"
    assert policy.hero_hands_only(site)
    assert policy.capabilities_at(site) == policy.CONSERVATIVE
    assert "4.1.3" in policy.why_not("dynamic_hud", site)
    # Nothing from the hand in play.
    assert not policy.capabilities_at(site).live_context


@pytest.mark.parametrize("site", ["PokerStars.FR", "Winamax", "PMU Poker", "Unibet", "GGPoker"])
def test_other_rooms_keep_every_hand(site) -> None:
    assert not policy.hero_hands_only(site)


def test_the_rebuild_filter_names_every_wpn_site() -> None:
    from fpdb_3_legacy.database_schema import DatabaseSchemaMixin

    source = Path(DatabaseSchemaMixin.__module__.replace(".", "/") + ".py").read_text(encoding="utf-8")
    seeded = {int(i) for i in re.findall(r"VALUES \('(\d+)', '[^']+', 'WP'\)", source)}
    assert seeded == set(policy.WPN_SITE_IDS)
    ids = re.search(r"IN \(([^)]+)\)", policy.HERO_HANDS_ONLY_REBUILD_FILTER).group(1)
    assert {int(i) for i in ids.split(",")} == set(policy.WPN_SITE_IDS)


# ---------------------------------------------------------------------------
# Import: Hand.updateHudCache
# ---------------------------------------------------------------------------


def _hand(site: str, hero_seat: int) -> Hand:
    hand = Hand.__new__(Hand)
    hand.callHud = True
    hand.sitename = site
    hand.handid = "1"
    hand.hands = {"heroSeat": hero_seat}
    hand.dbid_gt = 1
    hand.gametype = {}
    hand.playerIds = {}
    hand.startTime = None
    hand.handsplayers = {}
    return hand


@pytest.mark.parametrize(
    ("site", "hero_seat", "stored"),
    [
        ("Americas Cardroom", 0, False),  # observed at a WPN table: kept out
        ("Americas Cardroom", 3, True),  # the user's own hand
        ("WinningPoker", 0, False),
        ("PokerStars.COM", 0, True),  # other rooms are unchanged
    ],
)
def test_the_import_feeds_the_hud_cache_with_own_hands_only(site, hero_seat, stored) -> None:
    db = MagicMock()
    _hand(site, hero_seat).updateHudCache(db)
    assert db.storeHudCache.called is stored


# ---------------------------------------------------------------------------
# Rebuild: the HudCache half only
# ---------------------------------------------------------------------------


def _rebuilder() -> object:
    from fpdb_3_legacy.database_rebuild import DatabaseRebuildMixin

    rebuilder = DatabaseRebuildMixin.__new__(DatabaseRebuildMixin)
    rebuilder.sql = SimpleNamespace(
        query={"rebuildCache": "SELECT ... <tourney_join_clause> <where_clause>", "placeholder": "?"}
    )
    rebuilder.replace_statscache = lambda _game, _table, query: query
    return rebuilder


def test_the_hud_cache_rebuild_leaves_observed_wpn_hands_out() -> None:
    sql = _rebuilder().rebuild_sql("ring", "HudCache", "WHERE g.type = 'ring'")
    assert sql.endswith("WHERE g.type = 'ring'" + policy.HERO_HANDS_ONLY_REBUILD_FILTER)


def test_other_caches_are_rebuilt_unchanged() -> None:
    sql = _rebuilder().rebuild_sql("ring", "CardsCache", "WHERE g.type = 'ring'")
    assert policy.HERO_HANDS_ONLY_REBUILD_FILTER not in sql


# ---------------------------------------------------------------------------
# End to end on SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def importer(tmp_path):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {"db-server": "sqlite", "db-backend": 4, "db-databaseName": str(tmp_path / "wpn.sqlite3"), "db-path": ""}
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    yield importer
    importer.close()


_COUNTS = {
    "Hands": "SELECT COUNT(*) FROM Hands",
    "HandsPlayers": "SELECT COUNT(*) FROM HandsPlayers",
    "HudCache": "SELECT COUNT(*) FROM HudCache",
}


def _count(importer, table: str) -> int:
    cursor = importer.database.get_cursor()
    cursor.execute(_COUNTS[table])
    return cursor.fetchone()[0]


def _import(importer, path: Path) -> None:
    importer.addImportFile(str(path), "auto")
    importer.runImport()


def test_an_own_wpn_hand_feeds_the_hud(importer) -> None:
    _import(importer, WPN_HAND)
    assert _count(importer, "Hands") == 1
    assert _count(importer, "HudCache") > 0


def test_an_observed_wpn_hand_is_stored_but_feeds_no_hud(importer, tmp_path) -> None:
    # Same file name: the WPN converter reads part of the game from it.
    observed = tmp_path / "observed" / WPN_HAND.name
    observed.parent.mkdir()
    # The hero's cards are what make the hand the user's: without them nobody is the hero.
    observed.write_text(
        re.sub(r"received card: \[\w\w\]", "received a card.", WPN_HAND.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    _import(importer, observed)

    assert _count(importer, "Hands") == 1
    assert _count(importer, "HandsPlayers") > 0
    assert _count(importer, "HudCache") == 0

    importer.database.rebuild_cache()
    assert _count(importer, "HudCache") == 0
