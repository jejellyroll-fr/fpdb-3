"""ACR / WPN: HUD statistics from the user's own hands only (#719).

ACR Poker's Security & Game Integrity Policies, section 4.1.3, permit HUD
statistics only when they come from hands the player took part in, and nothing
from the hand in play. "The player" is the user: the screen names and aliases
configured for a WPN skin. A history someone else exported names *them* as its
hero (it shows their hole cards), so the parsed hero is never the test.

Every path that puts statistics in front of the HUD applies the rule:

* the import, which fills ``HudCache`` hand by hand;
* the cache rebuild;
* the session statistics, read from ``Hands``/``HandsPlayers`` directly;
* a database filled before the rule, whose WPN rows are refilled once.

The hand in play never reaches the HUD at these tables: their statistics come
from imported, completed hands, and the WPN policy allows no live context.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import database_rebuild
from fpdb_3_legacy import hud_room_policy as policy
from fpdb_3_legacy.Hand import Hand

ROOT = Path(__file__).resolve().parents[1]
WPN_HAND = next((ROOT / "regression-test-files/cash/Winning/Flop").glob("6+Holdem-6-max-USD-0.02-0.05-201902*.txt"))
WPN_PLAYER = "ChazDazzle"  # the player whose cards the fixture shows
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


def test_the_spelled_out_ids_are_every_wpn_site() -> None:
    from fpdb_3_legacy.database_schema import DatabaseSchemaMixin

    source = Path(DatabaseSchemaMixin.__module__.replace(".", "/") + ".py").read_text(encoding="utf-8")
    seeded = {int(i) for i in re.findall(r"VALUES \('(\d+)', '[^']+', 'WP'\)", source)}
    assert seeded == set(policy.WPN_SITE_IDS)
    assert {int(i) for i in policy.WPN_SITE_ID_SQL.split(",")} == seeded
    for statement in (
        database_rebuild.DELETE_HERO_HANDS_ONLY_HUDCACHE,
        database_rebuild.REFRESH_WHERE_RING,
        database_rebuild.REFRESH_WHERE_TOUR,
    ):
        assert f"IN ({policy.WPN_SITE_ID_SQL})" in statement


def _config(**names: str) -> SimpleNamespace:
    return SimpleNamespace(
        supported_sites={site: SimpleNamespace(hero_aliases=[name], screen_name=name) for site, name in names.items()}
    )


def test_user_names_span_the_whole_network() -> None:
    config = _config(**{"Americas Cardroom": "alice", "BlackChipPoker": "bob", "PokerStars": "carol"})
    assert policy.user_names(config, "WinningPoker") == {"alice", "bob"}
    assert policy.user_names(_config(**{"ACR Poker": "YOUR SCREEN NAME HERE"}), "ACR Poker") == frozenset()


def test_the_sql_condition() -> None:
    assert policy.hero_hands_only_sql([]) == f" AND g.siteId NOT IN ({policy.WPN_SITE_ID_SQL})"
    condition = policy.hero_hands_only_sql([7, "3"], "h2", "gt")
    assert condition.startswith(f" AND (gt.siteId NOT IN ({policy.WPN_SITE_ID_SQL}) OR EXISTS")
    assert "own.handId = h2.id AND own.playerId IN (3, 7)" in condition


# ---------------------------------------------------------------------------
# Import: Hand.updateHudCache
# ---------------------------------------------------------------------------


def _hand(site: str, players: list[str], config: SimpleNamespace) -> Hand:
    hand = Hand.__new__(Hand)
    hand.callHud = True
    hand.sitename = site
    hand.handid = "1"
    hand.config = config
    hand.players = [[seat, name, "1.00"] for seat, name in enumerate(players, start=1)]
    hand.hands = {"heroSeat": 1}  # someone's cards are shown: not proof it is the user's hand
    hand.dbid_gt = 1
    hand.gametype = {}
    hand.playerIds = {}
    hand.startTime = None
    hand.handsplayers = {}
    return hand


@pytest.mark.parametrize(
    ("site", "players", "stored"),
    [
        ("Americas Cardroom", ["alice", "bob"], True),  # the user played it
        ("WinningPoker", ["alice", "bob"], True),  # a name configured on another WPN skin
        ("Americas Cardroom", ["bob", "carol"], False),  # someone else's history
        ("PokerStars.COM", ["bob", "carol"], True),  # other rooms are unchanged
    ],
)
def test_the_import_feeds_the_hud_cache_with_the_users_hands_only(site, players, stored) -> None:
    db = MagicMock()
    _hand(site, players, _config(**{"Americas Cardroom": "alice"})).updateHudCache(db)
    assert db.storeHudCache.called is stored


def test_with_no_configured_name_no_wpn_hand_feeds_the_hud() -> None:
    db = MagicMock()
    _hand("Americas Cardroom", ["alice"], _config()).updateHudCache(db)
    assert not db.storeHudCache.called


# ---------------------------------------------------------------------------
# Rebuild: the HudCache half only
# ---------------------------------------------------------------------------


def _rebuilder(user_ids: list[int]) -> object:
    rebuilder = database_rebuild.DatabaseRebuildMixin.__new__(database_rebuild.DatabaseRebuildMixin)
    rebuilder.sql = SimpleNamespace(
        query={"rebuildCache": "SELECT ... <tourney_join_clause> <where_clause>", "placeholder": "?"}
    )
    rebuilder.replace_statscache = lambda _game, _table, query: query
    rebuilder.hero_hands_only_user_ids = lambda: user_ids
    return rebuilder


def test_the_hud_cache_rebuild_keeps_the_users_wpn_hands_only() -> None:
    sql = _rebuilder([5]).rebuild_sql("ring", "HudCache", "WHERE g.type = 'ring'")
    assert sql.endswith("WHERE g.type = 'ring'" + policy.hero_hands_only_sql([5]))


def test_other_caches_are_rebuilt_unchanged() -> None:
    sql = _rebuilder([5]).rebuild_sql("ring", "CardsCache", "WHERE g.type = 'ring'")
    assert "siteId NOT IN" not in sql


# ---------------------------------------------------------------------------
# End to end on SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def importer_for(tmp_path):
    """An importer on a fresh SQLite database, with ``screen_name`` set on Americas Cardroom."""
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    made = []

    def make(screen_name: str):
        folder = tmp_path / screen_name
        folder.mkdir()
        text = (
            (ROOT / "HUD_config.xml")
            .read_text(encoding="utf-8")
            .replace(
                '<site site_name="Americas Cardroom" enabled="False" screen_name=""',
                f'<site site_name="Americas Cardroom" enabled="False" screen_name="{screen_name}"',
            )
        )
        (folder / "HUD_config.xml").write_text(text, encoding="utf-8")
        config = Config(file=str(folder / "HUD_config.xml"))
        params = config.get_db_parameters()
        params.update(
            {"db-server": "sqlite", "db-backend": 4, "db-databaseName": str(folder / "wpn.sqlite3"), "db-path": ""}
        )
        config.get_db_parameters = lambda: params
        schema = Database(config)
        schema.recreate_tables()
        schema.close_connection()
        importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
        importer.setCallHud(False)
        made.append(importer)
        return importer

    yield make
    for importer in made:
        importer.close()


_COUNTS = {
    "Hands": "SELECT COUNT(*) FROM Hands",
    "HudCache": "SELECT COUNT(*) FROM HudCache",
}


def _count(importer, table: str) -> int:
    cursor = importer.database.get_cursor()
    cursor.execute(_COUNTS[table])
    return cursor.fetchone()[0]


def _import(importer) -> int:
    importer.addImportFile(str(WPN_HAND), "auto")
    importer.runImport()
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    return cursor.fetchone()[0]


def _session_players(importer, hand_id: int) -> set:
    db = importer.database
    db.hand_1day_ago = 0
    stats: dict = {}
    db.get_stats_from_hand_session(hand_id, stats, -1, "S", 1, 10, "S", 1, 10)
    return set(stats)


def test_the_users_wpn_hand_feeds_the_hud(importer_for) -> None:
    importer = importer_for(WPN_PLAYER)
    hand_id = _import(importer)

    assert _count(importer, "HudCache") > 0
    importer.database.rebuild_cache()
    assert _count(importer, "HudCache") > 0
    assert _session_players(importer, hand_id)


def test_someone_elses_wpn_history_is_stored_but_feeds_no_hud(importer_for) -> None:
    # The history shows ChazDazzle's cards; the user is alice.
    importer = importer_for("alice")
    hand_id = _import(importer)

    assert _count(importer, "Hands") == 1
    assert _count(importer, "HudCache") == 0
    importer.database.rebuild_cache()
    assert _count(importer, "HudCache") == 0
    # Session statistics read the hands directly: they apply the rule too.
    assert _session_players(importer, hand_id) == set()


def _rule_off(patch) -> None:
    """The code as it was before #719: every hand feeds the cache."""
    patch.setattr(policy, "hero_hands_only", lambda _site: False)
    patch.setattr(policy, "hero_hands_only_sql", lambda *_args, **_kwargs: "")


def test_a_cache_filled_before_the_rule_is_refilled_once(importer_for, monkeypatch) -> None:
    importer = importer_for("alice")
    db = importer.database
    # A database from before #719: its flag is not set, and the hand went
    # into the cache at import.
    db.get_cursor().execute("DELETE FROM AnalyticsMeta WHERE name = 'hudcache_hero_hands_only_v1'")
    with monkeypatch.context() as patch:
        _rule_off(patch)
        _import(importer)
    assert _count(importer, "HudCache") > 0

    db.refresh_hero_hands_only_hudcache()
    assert _count(importer, "HudCache") == 0

    # Once: a later run leaves the cache alone, whatever is in it.
    with monkeypatch.context() as patch:
        _rule_off(patch)
        db.rebuild_cache()
    assert _count(importer, "HudCache") > 0
    db.refresh_hero_hands_only_hudcache()
    assert _count(importer, "HudCache") > 0
