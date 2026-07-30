"""Structured All-in or Fold decision persistence and backfill."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import fpdb_3_legacy.autonotes_aof as autonotes_aof
from fpdb_3_legacy import Hand
from fpdb_3_legacy.AutoNotes import generate_for_hand
from fpdb_3_legacy.autonotes_aof import (
    AofDecisionAnalysis,
    extract_decisions,
)
from fpdb_3_legacy.backfill_aof_decisions import backfill_database
from fpdb_3_legacy.coinpoker_hand_builder import build_hands
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.equity import EquityEngine
from fpdb_3_legacy.http_capture_hand_builder import (
    HttpCaptureHandConfig,
    build_fpdb_hand,
    import_fpdb_hand,
)
from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_schema_aof import aof_schema_queries
from fpdb_3_legacy.stats_aof import aof_splash_freq, aof_splash_won

FIXTURE = Path(__file__).parent / "data" / "coinpoker_aof_hand_events.json"


def _config() -> MagicMock:
    config = MagicMock()
    config.get_db_parameters.return_value = {
        "db-backend": 4,
        "db-server": "sqlite",
        "db-databaseName": ":memory:",
        "db-user": "",
        "db-password": "",
        "db-host": "",
        "db-port": "",
        "db-path": "",
    }
    config.get_import_parameters.return_value = {
        "saveActions": True,
        "callFpdbHud": False,
        "cacheSessions": False,
        "publicDB": False,
        "fastStoreHudCache": False,
        "sessionTimeout": 30,
    }
    config.get_general_params.return_value = {}
    config.get_site_id.return_value = 30
    return config


def _database() -> Database:
    return Database(_config(), Sql(db_server="sqlite"))


SHOWDOWN_REVEALS = ("game.show_hole_cards", "game.reveal_cards")


def _hand(site_hand_offset: int = 0, *, reveal: bool = True):
    """The captured hand, optionally as a capture that missed the showdown.

    Both shovers are turned face up in the recording, so a hand where someone
    commits without showing -- the commonest case of all, a shove that takes
    the pot uncontested -- has to be made by dropping the reveals.
    """
    raw = json.loads(FIXTURE.read_text())
    events = [tuple(event) for event in raw["hand"]]
    if not reveal:
        events = [event for event in events if event[0] not in SHOWDOWN_REVEALS]
    (hand_data,) = build_hands([tuple(raw["join"]), *events], "PLO4")
    hand = build_fpdb_hand(
        hand_data,
        config=HttpCaptureHandConfig(site_ids={"CoinPoker": 30, "default": 30}),
    )
    if site_hand_offset:
        hand.handid = str(int(hand.handid) + site_hand_offset)
    return hand


def _import(db: Database, hand_id: int, site_hand_offset: int = 0, hand=None):
    db.resetBulkCache()
    return import_fpdb_hand(
        hand or _hand(site_hand_offset),
        db,
        file_id=1,
        doinsert=True,
        printtest=False,
        starting_hand_id=hand_id,
    )


def test_the_real_hand_produces_each_decision_at_its_decision_point() -> None:
    hand = _hand()
    hand.playerIds = {player[1]: seat for seat, player in enumerate(hand.players, start=1)}
    hand.dbid_hands = 41

    decisions = extract_decisions(hand)

    assert [(item.decision, item.role, item.active_opponents) for item in decisions] == [
        ("fold", "open_shove", 2),
        ("allin", "open_shove", 1),
        ("allin", "call_shove", 1),
    ]
    assert [(item.pot_before, item.amount_to_commit, item.blind_committed) for item in decisions] == [
        (35, 0, 0),
        (35, 190, 10),
        (225, 175, 25),
    ]


def test_a_third_all_in_is_an_overcall() -> None:
    hand = MagicMock()
    hand.gametype = {"category": "aof_omaha"}
    hand.actionStreets = ["BLINDSANTES", "FLOP"]
    hand.actions = {
        "BLINDSANTES": [],
        "FLOP": [
            ("a", "raises", 2, 2, 0, True),
            ("b", "calls", 2, True),
            ("c", "calls", 2, True),
        ],
    }
    hand.board = {"FLOP": ["2h", "3d", "4c"]}
    hand.players = [(1, "a", 2), (2, "b", 2), (3, "c", 2)]
    hand.playerIds = {"a": 1, "b": 2, "c": 3}
    hand.dbid_hands = 40
    hand.join_holecards.side_effect = lambda _player, asList=False: ["0x"] * 4

    assert [item.role for item in extract_decisions(hand)] == ["open_shove", "call_shove", "overcall"]


def test_aof_holdem_is_structured_without_omaha_classification() -> None:
    hand = MagicMock()
    hand.gametype = {"category": "aof_holdem"}
    hand.actionStreets = ["BLINDSANTES", "FLOP"]
    hand.actions = {"BLINDSANTES": [], "FLOP": [("hero", "raises", 1, 1, 0, True)]}
    hand.board = {"FLOP": ["2h", "3d", "4c"]}
    hand.players = [(1, "hero", 1)]
    hand.playerIds = {"hero": 7}
    hand.dbid_hands = 44
    hand.join_holecards.side_effect = lambda _player, asList=False: ["As", "Kd"]

    (decision,) = extract_decisions(hand)

    assert decision.category == "aof_holdem"
    assert decision.cards_observable
    assert decision.hole_cards == "As Kd"
    assert decision.made_hand is None


def test_hidden_cards_are_a_decision_but_never_an_observation() -> None:
    hand = _hand(reveal=False)
    hand.playerIds = {player[1]: seat for seat, player in enumerate(hand.players, start=1)}
    hand.dbid_hands = 42

    hidden = next(item for item in extract_decisions(hand) if item.decision == "allin" and not item.cards_observable)

    assert hidden.hole_cards is None
    assert hidden.flop_cards is None
    assert hidden.made_hand is None
    assert hidden.flush_draw is None
    assert hidden.straight_outs is None


def test_text_notes_are_rendered_from_the_structured_decision(monkeypatch) -> None:
    hand = _hand()
    hand.playerIds = {player[1]: seat for seat, player in enumerate(hand.players, start=1)}
    hand.dbid_hands = 43
    extract_decisions(hand)

    def fail_if_reclassified(*_args, **_kwargs):
        msg = "the note must consume the structured decision"
        raise AssertionError(msg)

    monkeypatch.setattr(autonotes_aof, "_classify_all_in_uncached", fail_if_reclassified)

    notes = {note.note_text.split(":")[0]: note for note in generate_for_hand(hand)}

    # Both shovers were turned face up, so both are described.
    assert set(notes) == {"hero", "villain1"}
    note = notes["hero"]
    assert note.evidence["made"] == "a pair"
    assert note.evidence["straight_outs"] == 4


def test_live_import_persists_structured_decisions_with_the_hand() -> None:
    db = _database()

    hand = _import(db, 1)

    cursor = db.get_cursor()
    cursor.execute(
        "SELECT decision, role, cardsObservable, madeHand, straightOuts FROM AofDecisions ORDER BY id",
    )
    # Both shovers were turned face up at showdown, so both holdings are on
    # record; only the player who folded showed nothing.
    assert cursor.fetchall() == [
        ("fold", "open_shove", 0, None, None),
        ("allin", "open_shove", 1, "two pair", 0),
        ("allin", "call_shove", 1, "a pair", 4),
    ]
    assert hand.aof_decision_ids == [1, 2, 3]


def test_a_decision_storage_failure_never_costs_the_hand(capsys) -> None:
    db = _database()
    db.storeAofDecisions = MagicMock(side_effect=RuntimeError("decision table unavailable"))

    _import(db, 1)

    cursor = db.get_cursor()
    cursor.execute(
        "SELECT (SELECT COUNT(*) FROM Hands), (SELECT COUNT(*) FROM HandsPlayers), (SELECT COUNT(*) FROM HandsActions)",
    )
    assert cursor.fetchone() == (1, 3, 5)
    assert "structured AoF decisions not stored: decision table unavailable" in capsys.readouterr().out


def test_replaying_a_hand_updates_decisions_without_duplicating_them() -> None:
    db = _database()
    hand = _import(db, 1)
    decisions = extract_decisions(hand)

    db.storeAofDecisions(decisions, doinsert=True)
    db.storeAofDecisions(decisions, doinsert=True)
    db.commit()

    cursor = db.get_cursor()
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT playerId) FROM AofDecisions WHERE handId=1")
    assert cursor.fetchone() == (3, 3)


def test_disabled_writes_and_an_empty_profile_are_database_noops() -> None:
    db = _database()
    db.get_cursor = MagicMock(side_effect=AssertionError("a no-op must not open a cursor"))

    assert db.storeAofDecisions([MagicMock()]) == []
    assert db.storeAofDecisionAnalyses([MagicMock()]) == []
    assert db.getAofProfileStats([], "aof_omaha") == {}
    db.get_cursor.assert_not_called()


def test_profile_aggregates_every_player_with_one_query() -> None:
    db = _database()
    _import(db, 1)
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT p.id, p.name FROM Players p JOIN AofDecisions d ON d.playerId=p.id GROUP BY p.id, p.name",
    )
    player_ids = {name: int(player_id) for player_id, name in cursor.fetchall()}
    statements = []
    db.connection.set_trace_callback(statements.append)

    grouped = db.getAofProfileStats(
        [*player_ids.values(), player_ids["hero"]],
        "aof_omaha",
    )

    db.connection.set_trace_callback(None)
    profile_reads = [
        statement for statement in statements if "from AofDecisions" in statement and "group by" in statement.lower()
    ]
    assert len(profile_reads) == 1
    assert set(grouped) == set(player_ids.values())
    assert grouped[player_ids["hero"]] == {
        "aof_obs": 1,
        "aof_no_made": 0,
        "aof_made": 1,
        "aof_nfd": 0,
        "aof_non_nfd": 0,
        "aof_wrap9": 0,
        "aof_big_wrap13": 0,
        "aof_pair": 1,
        "aof_two_pair": 0,
        "aof_trips": 0,
        "aof_straight": 0,
        "aof_flush": 0,
        "aof_full_house": 0,
        "aof_quads": 0,
        "aof_straight_flush": 0,
        "aof_known": 0,
        "aof_known_equity_ppm": 0,
        "aof_known_ev_bb_ppm": 0,
        "aof_range": 0,
        "aof_range_equity_ppm": 0,
        "aof_decision_ev": 0,
        "aof_weak": 0,
        "aof_decision_ev_bb_ppm": 0,
        "aof_splash_seen": 0,
        "aof_splash_hit": 0,
        "aof_splash_cents": 0,
    }


def test_the_hud_merges_one_grouped_read_and_skips_other_games() -> None:
    db = _database()
    db.getAofProfileStats = MagicMock(
        return_value={
            2: {
                "aof_obs": 5,
                "aof_no_made": 3,
                "aof_splash_seen": 4,
                "aof_splash_hit": 2,
                "aof_splash_cents": 250,
            },
            7: {
                "aof_obs": 1,
                "aof_no_made": 0,
                "aof_splash_seen": 4,
                "aof_splash_hit": 0,
                "aof_splash_cents": 0,
            },
        },
    )
    stats = {2: {"screen_name": "one"}, 7: {"screen_name": "two"}}

    db._merge_aof_profile_stats(stats, "aof_omaha")

    db.getAofProfileStats.assert_called_once_with(stats, "aof_omaha")
    assert stats[2]["aof_obs"] == 5
    assert stats[7]["aof_no_made"] == 0
    assert stats[2]["aof_splash_cents"] == 250
    assert stats[7]["aof_splash_seen"] == 4

    db.getAofProfileStats.reset_mock()
    plain = {2: {"screen_name": "one"}}
    db._merge_aof_profile_stats(plain, "omahahi")
    db.getAofProfileStats.assert_not_called()
    assert plain == {2: {"screen_name": "one"}}


def test_the_real_hud_stats_path_loads_the_objective_profile_once() -> None:
    db = _database()
    _import(db, 1)
    db.init_hud_stat_vars(30, 30)
    session_hud = {
        "stat_range": "S",
        "agg_bb_mult": 1000,
        "seats_style": "A",
        "seats_cust_nums_low": 1,
        "seats_cust_nums_high": 10,
        "h_stat_range": "S",
        "h_agg_bb_mult": 1000,
        "h_seats_style": "A",
        "h_seats_cust_nums_low": 1,
        "h_seats_cust_nums_high": 10,
    }
    statements = []
    db.connection.set_trace_callback(statements.append)

    stats = db.get_stats_from_hand(
        1,
        "ring",
        session_hud,
        hero_id=-1,
        num_seats=3,
        poker_game="aof_omaha",
    )

    db.connection.set_trace_callback(None)
    hero = next(values for values in stats.values() if values["screen_name"] == "hero")
    assert (hero["aof_obs"], hero["aof_made"], hero["aof_pair"]) == (1, 1, 1)
    assert len([statement for statement in statements if "from AofDecisions" in statement]) == 1


def test_the_real_hud_path_groups_splash_money_and_frequency() -> None:
    db = _database()
    hand = _hand()
    hand.splashPot = 150
    hand.splashWinnings = {"hero": Decimal("1.50")}
    _import(db, 1, hand=hand)
    db.init_hud_stat_vars(30, 30)
    session_hud = {
        "stat_range": "S",
        "agg_bb_mult": 1000,
        "seats_style": "A",
        "seats_cust_nums_low": 1,
        "seats_cust_nums_high": 10,
        "h_stat_range": "S",
        "h_agg_bb_mult": 1000,
        "h_seats_style": "A",
        "h_seats_cust_nums_low": 1,
        "h_seats_cust_nums_high": 10,
    }
    statements = []
    db.connection.set_trace_callback(statements.append)

    stats = db.get_stats_from_hand(
        1,
        "ring",
        session_hud,
        hero_id=-1,
        num_seats=3,
        poker_game="aof_omaha",
    )

    db.connection.set_trace_callback(None)
    hero = next((player_id, values) for player_id, values in stats.items() if values["screen_name"] == "hero")
    villain = next((player_id, values) for player_id, values in stats.items() if values["screen_name"] == "villain1")
    hero_id, hero_stats = hero
    villain_id, villain_stats = villain
    assert (
        hero_stats["aof_splash_seen"],
        hero_stats["aof_splash_hit"],
        hero_stats["aof_splash_cents"],
    ) == (1, 1, 150)
    assert (
        villain_stats["aof_splash_seen"],
        villain_stats["aof_splash_hit"],
        villain_stats["aof_splash_cents"],
    ) == (1, 0, 0)
    assert aof_splash_won(stats, hero_id)[1:5] == (
        "1.50",
        "Spl=1.50",
        "splash collected=1.50 over 1 of 1 splash hands",
        "(1/1)",
    )
    assert aof_splash_freq(stats, hero_id)[1:5] == (
        "100.0",
        "Spl%=100.0%",
        "splash taken=100.0%",
        "(1/1)",
    )
    assert aof_splash_won(stats, villain_id)[1] == "0.00"
    splash_reads = [statement for statement in statements if "sum(case when h.splashPot>0" in statement]
    assert len(splash_reads) == 1


@pytest.mark.qt
def test_the_replayer_restores_and_displays_the_players_splash(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration
    from fpdb_3_legacy.GuiReplayer import GuiReplayer

    QApplication.instance() or QApplication([])
    config = _config()
    config.graphics_path = Configuration.GRAPHICS_PATH
    config.ui.deck_type = "simple"
    config.ui.card_back = "back03"
    db = Database(config, Sql(db_server="sqlite"))
    hand = _hand()
    hand.splashPot = 150
    hand.splashWinnings = {"hero": Decimal("1.50")}
    _import(db, 1, hand=hand)

    restored = Hand.hand_factory(1, config, db)
    assert restored.splashWinnings == {"hero": Decimal("1.5")}

    replayer = GuiReplayer(config, db.sql, MagicMock(), [1])
    replayer.db = db
    qtbot.addWidget(replayer)
    replayer.play_hand(0)
    final_frame = replayer._frame_from_state(replayer.states[-1])
    replayer.stateSlider.setValue(len(replayer.states) - 1)

    hero = next(player for player in final_frame.players if player.name == "hero")
    assert hero.splash == Decimal("1.5")
    assert replayer._timeline_entries(50)[-1] == "hero: splash +$1.50"


def test_analysis_results_are_versioned_and_updated_idempotently() -> None:
    db = _database()
    _import(db, 1)
    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM AofDecisions WHERE cardsObservable=1")
    decision_id = cursor.fetchone()[0]
    analysis = AofDecisionAnalysis(
        decision_id=decision_id,
        backend="pypokereval",
        backend_version="1.0",
        range_model="population",
        range_version=2,
        analysis_version=1,
        equity_ppm=480_000,
        ev_chips=-12,
        ev_bb_ppm=-480_000,
        break_even_ppm=500_000,
        samples=20_000,
        stderr_ppm=6_000,
        status="uncertain",
    )

    db.storeAofDecisionAnalyses([analysis], doinsert=True)
    db.storeAofDecisionAnalyses(
        [replace(analysis, equity_ppm=530_000, ev_chips=8, status="strong")],
        doinsert=True,
    )
    db.commit()

    cursor.execute("SELECT COUNT(*), equityPpm, evChips, status FROM AofDecisionAnalyses")
    assert cursor.fetchone() == (1, 530_000, 8, "strong")


def test_equity_results_join_the_grouped_hud_read_without_a_player_query() -> None:
    db = _database()
    _import(db, 1)
    cursor = db.get_cursor()
    cursor.execute("SELECT id, playerId FROM AofDecisions WHERE cardsObservable=1")
    decision_id, player_id = cursor.fetchone()
    db.storeAofDecisionAnalyses(
        [
            AofDecisionAnalysis(
                decision_id=decision_id,
                backend="pypoker-eval",
                backend_version="engine-1",
                range_model="actual_known",
                range_version=1,
                analysis_version=1,
                equity_ppm=625_000,
                ev_chips=25,
                ev_bb_ppm=1_000_000,
                break_even_ppm=500_000,
                samples=820,
                stderr_ppm=0,
                status="complete",
            ),
            AofDecisionAnalysis(
                decision_id=decision_id,
                backend="pypoker-eval",
                backend_version="engine-1",
                range_model="population_observed",
                range_version=1,
                analysis_version=1,
                equity_ppm=550_000,
                ev_chips=None,
                ev_bb_ppm=None,
                break_even_ppm=500_000,
                samples=20_000,
                stderr_ppm=3_500,
                status="complete",
            ),
            AofDecisionAnalysis(
                decision_id=decision_id,
                backend="pypoker-eval",
                backend_version="engine-1",
                range_model="uniform_legal",
                range_version=1,
                analysis_version=1,
                equity_ppm=900_000,
                ev_chips=None,
                ev_bb_ppm=None,
                break_even_ppm=500_000,
                samples=20_000,
                stderr_ppm=2_000,
                status="complete",
            ),
            AofDecisionAnalysis(
                decision_id=decision_id,
                backend="pypoker-eval",
                backend_version="engine-1",
                range_model="population_decision_ev_prerake",
                range_version=1,
                analysis_version=1,
                equity_ppm=None,
                ev_chips=-12,
                ev_bb_ppm=-480_000,
                break_even_ppm=None,
                samples=250,
                stderr_ppm=100_000,
                status="weak",
            ),
            AofDecisionAnalysis(
                decision_id=decision_id,
                backend="pypoker-eval",
                backend_version="engine-1",
                range_model="population_decision_ev_prerake",
                range_version=2,
                analysis_version=1,
                equity_ppm=None,
                ev_chips=-99,
                ev_bb_ppm=-3_960_000,
                break_even_ppm=None,
                samples=250,
                stderr_ppm=100_000,
                status="weak",
            ),
        ],
        doinsert=True,
    )
    db.commit()

    grouped = db.getAofProfileStats([player_id], "aof_omaha")

    assert grouped[player_id]["aof_known"] == 1
    assert grouped[player_id]["aof_known_equity_ppm"] == 625_000
    assert grouped[player_id]["aof_known_ev_bb_ppm"] == 1_000_000
    assert grouped[player_id]["aof_range"] == 1
    assert grouped[player_id]["aof_range_equity_ppm"] == 550_000
    assert grouped[player_id]["aof_decision_ev"] == 1
    assert grouped[player_id]["aof_weak"] == 1
    assert grouped[player_id]["aof_decision_ev_bb_ppm"] == -480_000


def test_range_training_read_is_room_scoped_and_strictly_historical() -> None:
    db = _database()
    _import(db, 1)
    _import(db, 2, site_hand_offset=1)
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT id FROM AofDecisions WHERE handId=2 AND role='call_shove' AND cardsObservable=1",
    )
    decision_id = int(cursor.fetchone()[0])

    site_id = db.getAofDecisionSite(decision_id)
    observations = db.getAofRangeObservations(
        site_id,
        "aof_omaha",
        "call_shove",
        1,
        before_hand_id=2,
    )

    assert site_id == 30
    assert [(item.hand_id, item.site_id, item.role, item.hole_cards) for item in observations] == [
        (1, 30, "call_shove", "As Qh 8h 7c"),
    ]
    # The opener showed too, so their holding trains the open-shove range.
    assert [
        (item.role, item.hole_cards) for item in db.getAofRangeObservations(30, "aof_omaha", "open_shove", 1, 2)
    ] == [("open_shove", "Ks 9s Td 9d")]
    assert db.getAofRangeObservations(30, "aof_omaha", "call_shove", 1, 1) == ()


def test_action_training_read_includes_folds_but_never_current_or_future_hands() -> None:
    db = _database()
    _import(db, 1)
    _import(db, 2, site_hand_offset=1)
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT id FROM AofDecisions WHERE handId=2 AND role='call_shove'",
    )
    decision_id = int(cursor.fetchone()[0])
    cursor.execute(
        "UPDATE AofDecisions SET decision='fold' WHERE handId=1 AND role='call_shove'",
    )
    db.commit()
    site_id, _started_at = db.getAofDecisionScope(decision_id)

    observations = db.getAofActionObservations(
        site_id,
        "aof_omaha",
        "call_shove",
        1,
        before_hand_id=2,
    )

    assert [(item.hand_id, item.decision, item.site_id) for item in observations] == [
        (1, "fold", 30),
    ]
    assert db.getAofActionObservations(30, "aof_omaha", "call_shove", 1, 1) == ()
    assert db.getAofActionObservations(999, "aof_omaha", "call_shove", 1, 2) == ()


def test_feature_migration_creates_both_tables_on_an_existing_sqlite_database() -> None:
    db = _database()
    cursor = db.get_cursor()
    cursor.execute("DROP TABLE AofDecisionAnalyses")
    cursor.execute("DROP TABLE AofDecisions")
    db.commit()

    db.ensure_feature_tables()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('AofDecisions', 'AofDecisionAnalyses') ORDER BY name",
    )
    assert cursor.fetchall() == [("AofDecisionAnalyses",), ("AofDecisions",)]


def test_backfill_resumes_by_hand_id_and_is_safe_to_replay() -> None:
    db = _database()
    _import(db, 1)
    _import(db, 2, site_hand_offset=1)
    cursor = db.get_cursor()
    cursor.execute("DELETE FROM AofDecisionAnalyses")
    cursor.execute("DELETE FROM AofDecisions")
    db.commit()

    first = backfill_database(db=db, commit=True, batch_size=1, limit=1)
    second = backfill_database(
        db=db,
        commit=True,
        batch_size=1,
        start_after=first["last_hand_id"],
    )
    replay = backfill_database(db=db, commit=True, batch_size=2)

    assert (first["hands"], first["decisions"]) == (1, 3)
    assert (second["hands"], second["decisions"]) == (1, 3)
    assert replay["decisions"] == 6
    cursor.execute("SELECT COUNT(*) FROM AofDecisions")
    assert cursor.fetchone()[0] == 6


def test_aof_schema_is_installed_for_every_backend() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = aof_schema_queries(backend)
        assert expected.items() <= Sql(db_server=backend).query.items()


def test_aof_schema_keeps_backend_identities_relations_and_unique_versions() -> None:
    mysql = aof_schema_queries("mysql")
    postgresql = aof_schema_queries("postgresql")
    sqlite = aof_schema_queries("sqlite")

    assert "BIGINT UNSIGNED AUTO_INCREMENT" in mysql["createAofDecisionsTable"]
    assert "id BIGSERIAL" in postgresql["createAofDecisionsTable"]
    assert "id INTEGER PRIMARY KEY" in sqlite["createAofDecisionsTable"]
    for schema in (mysql, postgresql, sqlite):
        decisions = schema["createAofDecisionsTable"]
        analyses = schema["createAofDecisionAnalysesTable"]
        assert "handId, playerId, classifierVersion" in decisions
        assert "decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion" in analyses
        assert "REFERENCES Hands(id)" in decisions
        assert "REFERENCES Players(id)" in decisions
        assert "REFERENCES AofDecisions(id)" in analyses


class _MockBackend:
    """Deterministic test double for the native poker-eval backend."""

    def __init__(self, *, heads_up: int = 600, multiway: int = 300) -> None:
        self.heads_up = heads_up
        self.multiway = multiway

    def poker_eval(self, **kwargs: Any) -> dict:
        players = len(kwargs["pockets"])
        hero = self.heads_up if players == 2 else self.multiway
        other = (1000 - hero) // (players - 1)

        def result(equity: int) -> dict:
            return {"ev": equity, "winhi": equity, "tiehi": 0, "losehi": 1000 - equity}

        return {
            "info": (990, 0, 1),
            "eval": [result(hero), *[result(other) for _ in range(players - 1)]],
        }

    def best(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def card2string(self, card: Any) -> str:
        return str(card)

    def winners(self, **kwargs: Any) -> dict:
        return {}


def test_e2e_fixture_through_decisions_and_analyses_to_hud() -> None:
    """Full chain: fixture → Hand → SQLite → AofDecisions → analyses → stat_dict → HUD.

    Verifies that a real imported hand produces decisions, analyses are computed
    through the actual analysis engine (with a deterministic mock backend),
    and the HUD stat_dict surfaces the merged objective-profile aggregates.
    """
    from fpdb_3_legacy.aof_equity import analyze_known_cards_hand, build_known_cards_hand_request

    db = _database()
    hand = _import(db, 1)

    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM AofDecisions WHERE handId=1 ORDER BY id")
    decision_ids = [int(row[0]) for row in cursor.fetchall()]
    assert len(decision_ids) == 3

    hand.playerIds = {player[1]: seat for seat, player in enumerate(hand.players, start=1)}
    hand.dbid_hands = 1
    decisions = extract_decisions(hand)

    backend = _MockBackend(heads_up=717)
    engine = EquityEngine(backend)
    request = build_known_cards_hand_request(hand, decisions, decision_ids)
    assert request is not None

    result = analyze_known_cards_hand(request, engine)
    assert len(result.analyses) == 2  # two all-in players with visible cards
    db.storeAofDecisionAnalyses(result.analyses, doinsert=True)
    db.commit()

    analyses = cursor.execute(
        "SELECT decisionId, equityPpm, evChips, status FROM AofDecisionAnalyses ORDER BY decisionId",
    ).fetchall()
    assert len(analyses) == 2
    assert analyses[0][0] in decision_ids
    assert analyses[0][3] == "complete"
    assert analyses[0][1] == 717000  # hero has 717/1000 equity vs villain
    assert analyses[0][2] == 92  # 717/1000 of ~371c net pot - 175c commit
    assert analyses[1][3] == "complete"

    db.init_hud_stat_vars(30, 30)
    session_hud = {
        "stat_range": "S",
        "agg_bb_mult": 1000,
        "seats_style": "A",
        "seats_cust_nums_low": 1,
        "seats_cust_nums_high": 10,
        "h_stat_range": "S",
        "h_agg_bb_mult": 1000,
        "h_seats_style": "A",
        "h_seats_cust_nums_low": 1,
        "h_seats_cust_nums_high": 10,
    }
    stats = db.get_stats_from_hand(
        1,
        "ring",
        session_hud,
        hero_id=-1,
        num_seats=3,
        poker_game="aof_omaha",
    )

    hero = next(values for values in stats.values() if values["screen_name"] == "hero")
    assert hero["aof_obs"] == 1
    assert hero["aof_made"] == 1
    assert hero["aof_known"] == 1
    assert hero["aof_known_equity_ppm"] == 717000
    assert hero["aof_decision_ev"] >= 0
    assert hero["aof_splash_seen"] == 0


def test_backfill_aof_analyses_dry_run_counts_without_writing() -> None:
    from fpdb_3_legacy.backfill_aof_analyses import _hand_ids_with_missing_analyses

    db = _database()
    _import(db, 1)
    cursor = db.get_cursor()
    cursor.execute("SELECT handId FROM AofDecisions WHERE handId=1")
    assert cursor.fetchone() is not None

    ids = _hand_ids_with_missing_analyses(db, 0, 10)
    assert len(ids) >= 1
    assert 1 in ids

    from fpdb_3_legacy.backfill_aof_analyses import backfill_analyses

    stats = backfill_analyses(db=db, commit=False, batch_size=10, limit=10)
    assert stats["hands"] >= 1
    assert stats["hands_submitted"] == 0
    assert stats["decisions"] == 0

    cursor.execute("SELECT COUNT(*) FROM AofDecisionAnalyses")
    assert cursor.fetchone()[0] == 0


def test_backfill_missing_analyses_query_filters_by_backend_and_version() -> None:
    """Regression: analyses for a different backend must not satisfy the JOIN."""
    from fpdb_3_legacy.aof_equity import KNOWN_BACKEND, KNOWN_BACKEND_VERSION
    from fpdb_3_legacy.backfill_aof_analyses import _hand_ids_with_missing_analyses

    db = _database()
    _import(db, 1)
    cursor = db.get_cursor()

    # Check: how many decisions need analysis?
    cursor.execute(
        "SELECT id FROM AofDecisions WHERE handId=1 AND decision='allin' AND cardsObservable=1",
    )
    allin_ids = [r[0] for r in cursor.fetchall()]
    assert len(allin_ids) >= 2  # hand fixture has at least 2 allin decisions

    first_id = allin_ids[0]

    # Insert an analysis for a *different* backend -- hand must still be missing
    cursor.execute(
        "INSERT INTO AofDecisionAnalyses "
        "(decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion, status) "
        "VALUES (?, 'other-backend', '1', 'actual_known', 1, 1, 'complete')",
        (first_id,),
    )
    db.commit()

    ids = _hand_ids_with_missing_analyses(db, 0, 10)
    assert 1 in ids, "hand should still be missing (analysis was for a different backend)"

    # Now replace with the correct backend analysis for all allin decisions
    cursor.execute("DELETE FROM AofDecisionAnalyses")
    for idx, decision_id in enumerate(allin_ids):
        # Use a unique analysis version per decision to avoid unique-constraint
        # collisions; the query only checks rangeModel + rangeVersion +
        # analysisVersion against known-card defaults, so we test both match
        # and mismatch within the same model set.
        if idx == 0:
            # Insert one matching analysis
            cursor.execute(
                "INSERT INTO AofDecisionAnalyses "
                "(decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion, status) "
                "VALUES (?, ?, ?, 'actual_known', 1, 1, 'complete')",
                (decision_id, KNOWN_BACKEND, KNOWN_BACKEND_VERSION),
            )
        else:
            # Insert a non-matching analysis (different rangeModel) to verify
            # the query is not satisfied by a completely unrelated row
            cursor.execute(
                "INSERT INTO AofDecisionAnalyses "
                "(decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion, status) "
                "VALUES (?, ?, ?, 'other_model', 1, 1, 'complete')",
                (decision_id, KNOWN_BACKEND, KNOWN_BACKEND_VERSION),
            )
    db.commit()

    # Hand is still missing because other allin decisions have no matching analysis
    ids2 = _hand_ids_with_missing_analyses(db, 0, 10)
    assert 1 in ids2, "hand should still be missing (not all allin decisions have the matching analysis)"

    # Now fill every allin decision with the correct backend + model analysis
    cursor.execute("DELETE FROM AofDecisionAnalyses")
    for decision_id in allin_ids:
        cursor.execute(
            "INSERT INTO AofDecisionAnalyses "
            "(decisionId, backend, backendVersion, rangeModel, rangeVersion, analysisVersion, status) "
            "VALUES (?, ?, ?, 'actual_known', 1, 1, 'complete')",
            (decision_id, KNOWN_BACKEND, KNOWN_BACKEND_VERSION),
        )
    db.commit()

    ids3 = _hand_ids_with_missing_analyses(db, 0, 10)
    assert 1 not in ids3, "hand is complete when every allin decision has the correct backend analysis"


def test_backfill_aof_analyses_commit_persists_analyses(tmp_path: Path) -> None:
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.SQL import Sql

    db_path = str(tmp_path / "aof_backfill_test.db")
    cfg = _config()
    cfg.get_db_parameters.return_value = {
        "db-backend": 4,
        "db-server": "sqlite",
        "db-databaseName": db_path,
        "db-user": "",
        "db-password": "",
        "db-host": "",
        "db-port": "",
        "db-path": str(tmp_path),
    }
    cfg.dir_database = str(tmp_path)
    db = Database(cfg, Sql(db_server="sqlite"))
    _import(db, 1)

    cursor = db.get_cursor()
    cursor.execute("SELECT COUNT(*) FROM AofDecisionAnalyses")
    assert cursor.fetchone()[0] == 0

    from fpdb_3_legacy.backfill_aof_analyses import backfill_analyses

    class _MockPokerEval:
        def poker_eval(self, **kwargs):
            pockets = kwargs.get("pockets", [])
            return {
                "info": (1,),
                "eval": [
                    {"ev": 500, "winhi": 0, "winlo": 0, "tiehi": 0, "tielo": 0, "losehi": 0, "loselo": 1}
                    for _ in pockets
                ],
            }

        def best(self, *args, **kwargs):
            return None

        def card2string(self, card):
            return str(card)

        def winners(self, **kwargs):
            return {}

    stats = backfill_analyses(
        db=db,
        db_factory=lambda: Database(cfg, Sql(db_server="sqlite")),
        commit=True,
        batch_size=10,
        limit=10,
        engine=EquityEngine(_MockPokerEval()),
    )

    assert stats["hands"] >= 1
    assert stats["hands_submitted"] >= 1
    assert stats["decisions"] >= 1
    db.commit()

    cursor.execute("""
        SELECT status, equityPpm IS NOT NULL, errorText IS NULL
        FROM AofDecisionAnalyses
    """)
    analyses = cursor.fetchall()
    assert len(analyses) >= 1, "at least one analysis was persisted"
    for status, has_equity, no_error in analyses:
        assert status == "complete", f"analysis status is {status!r}, not 'complete'"
        assert has_equity, "analysis has no equityPpm"
        assert no_error, "analysis has errorText set"

    # Second run finds nothing to do (all allin decisions now have matching analyses)
    stats2 = backfill_analyses(
        db=db,
        db_factory=lambda: Database(cfg, Sql(db_server="sqlite")),
        commit=True,
        batch_size=10,
        limit=10,
    )
    assert stats2["hands_submitted"] == 0
