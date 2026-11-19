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

Automatic notes follow the same rule (section 4.1.8 allows them from the
user's own hands): none is generated from another WPN hand, and the ones a
database made before the rule are removed once.

The hand in play never reaches the HUD at these tables: their statistics come
from imported, completed hands, and the WPN policy allows no live context. The
last section pins that down on auto-import: a hand the client is still
writing -- the user to act, or folded at a fast-fold table -- is not stored,
not sent to the HUD, not counted in ``HudCache`` (rebuilt or not) and not
noted, however many cycles pass, and counts once its end is written.
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
        database_rebuild.HERO_HANDS_ONLY_PLAYERS,
        policy._NONE_OF_THE_ROOMS,
        policy._ONLY_THE_USERS_HANDS,
        database_rebuild.REFRESH_WHERE_RING,
        database_rebuild.REFRESH_WHERE_TOUR,
        database_rebuild.DELETE_OTHERS_AUTONOTES,
        database_rebuild.DELETE_ALL_HERO_HANDS_ONLY_AUTONOTES,
    ):
        assert f"IN ({policy.WPN_SITE_ID_SQL})" in statement


def _always_noted() -> object:
    from fpdb_3_legacy.AutoNotes import AutoNoteRule

    return AutoNoteRule("probe_719", 1, "Probe", "{player} sat here", lambda *_: True, lambda *_: {})


_ALWAYS = _always_noted()


def _config(**names: str) -> SimpleNamespace:
    return SimpleNamespace(
        supported_sites={site: SimpleNamespace(hero_aliases=[name], screen_name=name) for site, name in names.items()}
    )


def test_user_names_span_the_whole_network() -> None:
    config = _config(**{"Americas Cardroom": "alice", "BlackChipPoker": "bob", "PokerStars": "carol"})
    assert policy.user_names(config, "WinningPoker") == {"alice", "bob"}
    assert policy.user_names(_config(**{"ACR Poker": "YOUR SCREEN NAME HERE"}), "ACR Poker") == frozenset()


@pytest.mark.parametrize(
    ("hand", "kept"),
    [
        # A parsed hand knows its site by name...
        (SimpleNamespace(sitename="Americas Cardroom", players=[[1, "bob", "1"], [2, "carol", "1"]]), True),
        (SimpleNamespace(sitename="BlackChipPoker", players=[[1, "alice", "1"], [2, "bob", "1"]]), False),
        (SimpleNamespace(sitename="PokerStars", players=[[1, "bob", "1"]]), False),
        # ...a hand rebuilt from the database by its id, as an int or a string.
        (SimpleNamespace(siteId=24, players=[(1, "bob", 1)]), True),
        (SimpleNamespace(siteId="116", players=[(1, "alice", 1)]), False),
        (SimpleNamespace(siteId=2, players=[(1, "bob", 1)]), False),
        (SimpleNamespace(siteId=None, players=[(1, "bob", 1)]), False),
    ],
)
def test_which_hands_are_kept_from_the_hud(hand, kept) -> None:
    assert policy.kept_from_hud(hand, _config(**{"Americas Cardroom": "alice"})) is kept


def test_without_a_configured_name_every_wpn_hand_is_kept_from_the_hud() -> None:
    hand = SimpleNamespace(sitename="Americas Cardroom", players=[[1, "alice", "1"]])
    assert policy.kept_from_hud(hand, None)
    assert policy.kept_from_hud(hand, _config(**{"PokerStars": "alice"}))


def test_no_auto_note_from_someone_elses_wpn_hand() -> None:
    from fpdb_3_legacy.AutoNotes import generate_for_hand

    def hand(*names: str) -> SimpleNamespace:
        return SimpleNamespace(
            sitename="Americas Cardroom",
            dbid_hands=1,
            players=[[seat, name, "1"] for seat, name in enumerate(names, start=1)],
            playerIds={name: seat for seat, name in enumerate(names, start=1)},
        )

    config = _config(**{"Americas Cardroom": "alice"})
    assert len(generate_for_hand(hand("alice", "bob"), rules=(_ALWAYS,), config=config)) == 2
    assert generate_for_hand(hand("bob", "carol"), rules=(_ALWAYS,), config=config) == []


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


def test_a_last_hand_kept_from_the_hud_still_flushes_the_batch() -> None:
    # storeHudCache writes its buffer only on doinsert, which the importer sets
    # on a file's last hand: an excluded last hand adds nothing but flushes.
    db = MagicMock()
    hand = _hand("Americas Cardroom", ["bob", "carol"], _config(**{"Americas Cardroom": "alice"}))
    hand.handsplayers = {"bob": {"n": 1}}
    hand.updateHudCache(db, doinsert=True)
    db.storeHudCache.assert_called_once()
    *_, pdata, doinsert = db.storeHudCache.call_args.args
    assert pdata == {}
    assert doinsert is True


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
    "PlayerAutoNotes": "SELECT COUNT(*) FROM PlayerAutoNotes",
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


def test_a_file_ending_with_someone_elses_hand_keeps_the_users_hud_rows(importer_for, tmp_path) -> None:
    # The user's hand, then one they did not play, as the file's last hand: the
    # importer flushes HudCache on the last hand only, so excluding that hand
    # must not drop what the first one buffered.
    first = WPN_HAND.read_text(encoding="utf-8").strip()
    second = first.replace(WPN_PLAYER, "SomeoneElse").replace("Game ID: 1377529121", "Game ID: 1377529122")
    path = tmp_path / WPN_HAND.name
    path.write_text(f"{first}\n\n\n{second}\n", encoding="utf-8")

    importer = importer_for(WPN_PLAYER)
    importer.addImportFile(str(path), "auto")
    importer.runImport()

    assert _count(importer, "Hands") == 2
    rows = _rows(
        importer,
        "SELECT p.name, SUM(hc.n) FROM HudCache hc JOIN Players p ON p.id = hc.playerId GROUP BY p.name",
    )
    counted = dict(rows)
    # Every player of the user's hand, once; nothing from the other hand.
    assert counted == {name: 1 for name in (WPN_PLAYER, "primo4", "validraize", "WhatAcrock420")}


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


# ---------------------------------------------------------------------------
# Auto-notes, end to end (section 4.1.8)
# ---------------------------------------------------------------------------


@pytest.fixture
def every_hand_noted(monkeypatch):
    """A rule that notes every player of every hand, so the import writes notes."""
    from fpdb_3_legacy import AutoNotes

    rule_set = AutoNotes.AutoNoteRuleSet("probe_719", (_ALWAYS,), lambda _hand: True)
    monkeypatch.setattr(AutoNotes, "_rule_sets_for_hand", lambda *_args, **_kwargs: (rule_set,))


@pytest.mark.usefixtures("every_hand_noted")
def test_the_users_wpn_hand_gets_auto_notes(importer_for) -> None:
    importer = importer_for(WPN_PLAYER)
    _import(importer)
    assert _count(importer, "PlayerAutoNotes") > 0


@pytest.mark.usefixtures("every_hand_noted")
def test_someone_elses_wpn_history_gets_no_auto_notes(importer_for) -> None:
    importer = importer_for("alice")
    _import(importer)
    assert _count(importer, "Hands") == 1
    assert _count(importer, "PlayerAutoNotes") == 0


def _notes_from_before_the_rule(importer, patch) -> None:
    importer.database.get_cursor().execute("DELETE FROM AnalyticsMeta WHERE name = 'autonotes_hero_hands_only_v1'")
    with patch.context() as before:
        _rule_off(before)
        _import(importer)
    assert _count(importer, "PlayerAutoNotes") > 0


@pytest.mark.usefixtures("every_hand_noted")
def test_auto_notes_from_before_the_rule_are_dropped_once(importer_for, monkeypatch) -> None:
    importer = importer_for("alice")
    _notes_from_before_the_rule(importer, monkeypatch)

    importer.database.drop_hero_hands_only_autonotes()
    assert _count(importer, "Hands") == 1
    assert _count(importer, "PlayerAutoNotes") == 0

    # Once: a note written afterwards is left alone.
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    hand_id = cursor.fetchone()[0]
    cursor.execute("SELECT playerId FROM HandsPlayers WHERE handId = ?", (hand_id,))
    player_id = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO PlayerAutoNotes (playerId, handId, ruleId, ruleVersion, noteText, evidence)"
        " VALUES (?, ?, 'probe_719', 2, 'later', '{}')",
        (player_id, hand_id),
    )
    importer.database.drop_hero_hands_only_autonotes()
    assert _count(importer, "PlayerAutoNotes") == 1


@pytest.mark.usefixtures("every_hand_noted")
def test_the_users_own_auto_notes_survive_the_drop(importer_for, monkeypatch) -> None:
    importer = importer_for(WPN_PLAYER)
    _notes_from_before_the_rule(importer, monkeypatch)
    noted = _count(importer, "PlayerAutoNotes")

    importer.database.drop_hero_hands_only_autonotes()
    assert _count(importer, "PlayerAutoNotes") == noted


# ---------------------------------------------------------------------------
# The hand in play (section 4.1.3: nothing from the hand in play)
# ---------------------------------------------------------------------------

BLITZ_HAND = next((ROOT / "regression-test-files/cash/Winning/Flop").glob("NLHE-6max-USD-0.05-0.10-201906.RUSHID-*"))

#: A finished hand, then the next one as far as the client has written it:
#: (history, the user, the hand id and the next one's, where the client is).
IN_PLAY = {
    # The user still has to act on the turn.
    "cash": (WPN_HAND, WPN_PLAYER, ("Game ID: 1377529121", "Game ID: 1377529122"), "Player ChazDazzle bets (0.05)"),
    # Fast-fold: the user folded and moved on; the hand plays out without them.
    "fast-fold": (BLITZ_HAND, "Hero", ("Hand #68217077", "Hand #68217078"), "Uncalled bet"),
}

_HANDS_STORED = "SELECT id, siteHandNo FROM Hands ORDER BY id"
_HANDS_IN_THE_HUD_CACHE = (
    "SELECT SUM(hc.n) FROM HudCache hc INNER JOIN Players p ON (p.id = hc.playerId) WHERE p.name = ?"
)
_NOTED_HANDS = "SELECT DISTINCT h.siteHandNo FROM PlayerAutoNotes pan INNER JOIN Hands h ON (h.id = pan.handId)"


def _rows(importer, query: str, params: tuple = ()) -> list:
    cursor = importer.database.get_cursor()
    cursor.execute(query, params)
    return cursor.fetchall()


@pytest.mark.usefixtures("every_hand_noted")
@pytest.mark.parametrize("case", sorted(IN_PLAY))
def test_the_hand_in_play_reaches_nothing_until_it_is_finished(case, importer_for, tmp_path) -> None:
    history, user, (hand_id, next_hand_id), client_is_at = IN_PLAY[case]
    finished = history.read_text(encoding="utf-8").strip() + "\n"
    next_hand = finished.replace(hand_id, next_hand_id)
    written_so_far = next_hand[: next_hand.index(client_is_at)]
    assert "SUMMARY" not in written_so_far.upper()  # the hand has no result yet

    importer = importer_for(user)
    importer.setMode("auto")
    importer.setCallHud(True)
    importer.zmq_sender = MagicMock()  # what the live HUD is told
    importer.caller = MagicMock()  # the auto-import tab, which logs each cycle
    path = tmp_path / history.name
    path.write_text(finished + "\n" + written_so_far, encoding="utf-8")
    assert importer.addImportFile(str(path), "auto")
    importer.runUpdated()  # a file seen for the first time is only registered

    # More cycles while the hand is in play: the client writes nothing new,
    # or the user left the table and it never will.
    for _cycle in range(3):
        path.touch()
        importer.runUpdated()
        stored = _rows(importer, _HANDS_STORED)
        assert [site_hand_no for _id, site_hand_no in stored] == [int(hand_id.split()[-1].lstrip("#"))]
        assert [call.args[0] for call in importer.zmq_sender.send_hand_id.call_args_list] == [stored[0][0]]
        assert _rows(importer, _HANDS_IN_THE_HUD_CACHE, (user,)) == [(1,)]
        assert _rows(importer, _NOTED_HANDS) == [(stored[0][1],)]
    # A cache rebuild has nothing more to count either.
    importer.database.rebuild_cache()
    assert _rows(importer, _HANDS_IN_THE_HUD_CACHE, (user,)) == [(1,)]

    # The client writes the end of the hand: now, and only now, it counts.
    path.write_text(finished + "\n" + next_hand, encoding="utf-8")
    importer.runUpdated()
    stored = _rows(importer, _HANDS_STORED)
    assert len(stored) == 2
    assert [call.args[0] for call in importer.zmq_sender.send_hand_id.call_args_list] == [row[0] for row in stored]
    assert _rows(importer, _HANDS_IN_THE_HUD_CACHE, (user,)) == [(2,)]
    assert sorted(_rows(importer, _NOTED_HANDS)) == sorted((row[1],) for row in stored)
