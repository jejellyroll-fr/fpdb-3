from unittest.mock import MagicMock, patch

import pytest

from fpdb_3_legacy import hud_read_service
from fpdb_3_legacy.hud_read_service import (
    HudBatchReadRequest,
    HudBatchSnapshot,
    HudPreparedHand,
    HudReadService,
    HudReplayDatabase,
    HudTableReadContext,
)


def _table_info(table: str, site_id: int = 1) -> tuple:
    return (table, 6, "holdem", "ring", False, site_id, "site", 6, None, None, None)


def _config() -> MagicMock:
    config = MagicMock()
    config.get_supported_sites.return_value = []
    config.get_supported_games_parameters.return_value = {}
    return config


def _database() -> MagicMock:
    database = MagicMock()
    database.backend = 0
    database.get_hand_positions.side_effect = lambda hand_id: {"position": str(hand_id)}
    database.get_seat_players.side_effect = lambda hand_id: {"seat": str(hand_id)}
    database.get_table_min_stack_bb.return_value = 25
    database.get_cards.return_value = {"hero": [1, 2]}
    database.get_common_cards.return_value = {"common": [3, 4, 5]}
    database.get_stats_from_hand.side_effect = lambda hand_id, *_args, **_kwargs: {"hand": str(hand_id)}
    return database


def test_read_batch_keeps_only_latest_primary_hand_and_finishes_transaction() -> None:
    database = _database()
    database.get_table_info.side_effect = lambda hand_id: _table_info("table-a")
    service = HudReadService(_config(), database, hand_factory=lambda hand_id, *_args: f"hand-{hand_id}")

    snapshot = service.read_batch(
        HudBatchReadRequest(
            sequence=7,
            hand_ids=("101", "102"),
            hud_params={"hud_days": 30, "h_hud_days": 90},
        ),
    )

    assert snapshot.primary_order == ("102",)
    assert snapshot.hands["102"].hand_instance == "hand-102"
    assert snapshot.hands["102"].cards["common"] == [3, 4, 5]
    database.get_stats_from_hand.assert_called_once()
    database.connection.rollback.assert_called_once()


def test_secondary_huds_share_one_batched_stats_query_and_normalize_ids() -> None:
    database = _database()
    database.get_table_info.side_effect = lambda hand_id: _table_info(f"table-{hand_id}")
    database.get_stats_from_hands.return_value = {
        201: {"value": "a"},
        202: {"value": "b"},
    }
    service = HudReadService(_config(), database)
    params = {"hud_days": 30, "h_hud_days": 90}
    contexts = tuple(
        HudTableReadContext(
            temp_key=f"table-{hand_id}",
            last_hand_id=str(hand_id),
            hud_params=params,
            poker_game="holdem",
            game_type="ring",
            site_id=1,
            num_seats=6,
        )
        for hand_id in (201, 202)
    )

    snapshot = service.read_batch(HudBatchReadRequest(3, (), params, contexts))

    database.get_stats_from_hands.assert_called_once()
    assert snapshot.hands["201"].stat_dict == {"value": "a"}
    assert snapshot.hands["202"].stat_dict == {"value": "b"}


def test_worker_can_publish_each_primary_table_before_the_batch_is_complete() -> None:
    database = _database()
    database.get_table_info.side_effect = lambda hand_id: _table_info(f"table-{hand_id}")
    service = HudReadService(_config(), database, hand_factory=lambda *_args: None)
    progress = []

    final = service.read_batch(
        HudBatchReadRequest(
            sequence=8,
            hand_ids=("211", "212"),
            hud_params={"hud_days": 30, "h_hud_days": 90},
        ),
        progress_callback=progress.append,
    )

    assert [snapshot.primary_order for snapshot in progress] == [
        ("211",),
        ("212",),
        ("211",),
        ("212",),
    ]
    assert [snapshot.identity_only for snapshot in progress] == [True, True, False, False]
    assert [snapshot.final for snapshot in progress] == [False, False, False, False]
    assert final.final is True
    assert final.revision == 5
    assert database.connection.rollback.call_count == 5


def test_table_identity_is_emitted_before_hero_or_statistics_queries() -> None:
    order: list[str] = []
    database = _database()
    database.get_table_info.side_effect = lambda _hand_id: (order.append("table_info") or _table_info("table-a"))
    database.get_stats_from_hand.side_effect = lambda *_args, **_kwargs: (order.append("stats") or {})
    config = _config()
    config.get_supported_sites.side_effect = lambda: (order.append("hero") or [])
    service = HudReadService(config, database, hand_factory=lambda *_args: None)

    def on_progress(snapshot: HudBatchSnapshot) -> None:
        if snapshot.identity_only:
            order.append("identity")

    service.read_batch(
        HudBatchReadRequest(10, ("601",), {"hud_days": 30, "h_hud_days": 90}),
        progress_callback=on_progress,
    )

    assert order[:4] == ["table_info", "identity", "hero", "stats"]


def test_progress_snapshot_does_not_deepcopy_the_opaque_hand_instance() -> None:
    class OpaqueHand:
        def __deepcopy__(self, _memo):
            raise AssertionError("Hand instances are not required to support deepcopy")

    opaque_hand = OpaqueHand()
    database = _database()
    database.get_table_info.return_value = _table_info("table-a")
    service = HudReadService(_config(), database, hand_factory=lambda *_args: opaque_hand)
    progress = []

    service.read_batch(
        HudBatchReadRequest(11, ("701",), {"hud_days": 30, "h_hud_days": 90}),
        progress_callback=progress.append,
    )

    full_snapshot = next(snapshot for snapshot in progress if not snapshot.identity_only)
    assert full_snapshot.hands["701"].hand_instance is opaque_hand


def test_hero_lookup_is_cached_across_worker_batches() -> None:
    database = _database()
    config = _config()
    service = HudReadService(config, database)
    request = HudBatchReadRequest(1, (), {"hud_days": 30, "h_hud_days": 90})

    service.read_batch(request)
    service.read_batch(request)

    config.get_supported_sites.assert_called_once()
    assert database.connection.rollback.call_count == 2


def test_missing_hero_is_retried_instead_of_cached_forever() -> None:
    database = _database()
    database.get_site_id.return_value = [(1,)]
    database.get_player_id.side_effect = [None, 42]
    config = _config()
    config.get_supported_sites.return_value = ["Site"]
    config.supported_sites = {"Site": MagicMock(screen_name="hero")}
    service = HudReadService(config, database)
    request = HudBatchReadRequest(1, (), {"hud_days": 30, "h_hud_days": 90})

    first = service.read_batch(request)
    second = service.read_batch(request)

    assert first.hero_ids == {1: -1}
    assert second.hero_ids == {1: 42}
    assert database.get_player_id.call_count == 2


def test_failed_primary_read_preloads_its_previous_secondary_hand() -> None:
    database = _database()
    database.get_table_info.side_effect = lambda hand_id: _table_info("table-a")
    database.get_stats_from_hand.side_effect = RuntimeError("primary failed")
    database.get_stats_from_hands.return_value = {401: {"old": True}}
    service = HudReadService(_config(), database)
    params = {"hud_days": 30, "h_hud_days": 90}
    context = HudTableReadContext(
        temp_key="table-a",
        last_hand_id="401",
        hud_params=params,
        poker_game="holdem",
        game_type="ring",
        site_id=1,
        num_seats=6,
    )

    snapshot = service.read_batch(HudBatchReadRequest(4, ("402",), params, (context,)))

    assert snapshot.failed_hand_ids == ("402",)
    assert snapshot.hands["401"].stat_dict == {"old": True}


def test_statement_timeout_aborts_the_batch_instead_of_timing_out_every_table() -> None:
    class StatementTimeout(RuntimeError):
        sqlstate = "57014"

    database = _database()
    database.get_table_info.return_value = _table_info("table-a")
    database.get_stats_from_hand.side_effect = StatementTimeout("statement timeout")
    service = HudReadService(_config(), database)

    progress = []
    with pytest.raises(StatementTimeout):
        service.read_batch(
            HudBatchReadRequest(
                9,
                ("501", "502"),
                {"hud_days": 30, "h_hud_days": 90},
            ),
            progress_callback=progress.append,
        )

    database.get_stats_from_hand.assert_called_once()
    assert len(progress) == 2
    assert all(snapshot.identity_only for snapshot in progress)


def test_replay_database_accepts_string_input_for_integer_database_ids() -> None:
    prepared = HudPreparedHand(
        hand_id="301",
        stat_dict={"value": 9},
        loaded_fields=frozenset({"stat_dict"}),
    )
    snapshot = HudBatchSnapshot(1, (), (), {"301": prepared}, {}, {}, {}, {})
    replay = HudReplayDatabase(snapshot, backend=0)

    assert replay.get_stats_from_hand(301) == {"value": 9}
    assert replay.get_stats_from_hands([301]) == {301: {"value": 9}}


def test_replay_database_logs_a_missing_preload_instead_of_failing_silently() -> None:
    prepared = HudPreparedHand(
        hand_id="302",
        table_info=_table_info("table-a"),
        loaded_fields=frozenset({"table_info"}),
    )
    replay = HudReplayDatabase(HudBatchSnapshot(1, (), (), {"302": prepared}, {}, {}, {}, {}), backend=0)

    with patch.object(hud_read_service.log, "debug") as debug:
        assert replay.get_action_from_hand("302") == []

    debug.assert_called_once()


def test_expected_identity_misses_are_not_logged() -> None:
    prepared = HudPreparedHand(
        hand_id="303",
        table_info=_table_info("table-a"),
        loaded_fields=frozenset({"table_info"}),
    )
    snapshot = HudBatchSnapshot(
        1,
        (),
        (),
        {"303": prepared},
        {},
        {},
        {},
        {},
        identity_only=True,
    )
    replay = HudReplayDatabase(snapshot, backend=0)

    with patch.object(hud_read_service.log, "debug") as debug:
        assert replay.get_seat_players("303") == {}
        assert replay.get_table_min_stack_bb("303") is None

    debug.assert_not_called()
