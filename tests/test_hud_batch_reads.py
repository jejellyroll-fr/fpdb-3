"""The batched HUD reads must return exactly what the per-hand reads return (#680).

`HudReadService` used to issue get_table_info/get_site_hand_no/positions/seat
players/cards/min-stack once per hand; at eight tables that is ~16+ round trips
per batch round on a remote database. The `*_many` variants must produce the
same data in one statement each, and `_read_hand` must fall back to the per-hand
read whenever the batched value is missing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.hud_read_service import HudBatchReadRequest, HudReadService, HudTableReadContext
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

REPO = Path(__file__).resolve().parent.parent
FILES = (
    REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt",
    REPO / "regression-test-files/cash/Stars/Flop/5-Card-PLO-6max-USD-3.00-6.00-201303.txt",
)


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    directory = tmp_path_factory.mktemp("batchreads680")
    config = golden.build_config(directory)
    Database(config).recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = Database(config)
    importer.setCallHud(True)
    for path in FILES:
        importer.addImportFile(str(path), "auto")
    stored, *_rest = importer.runImport()
    assert stored >= 2
    importer.close()
    database = Database(config)
    yield database
    database.disconnect()


@pytest.fixture(scope="module")
def hand_ids(db):
    c = db.connection.cursor()
    c.execute("SELECT id FROM Hands ORDER BY id LIMIT 3")
    ids = [row[0] for row in c.fetchall()]
    c.close()
    assert len(ids) >= 2
    return ids


def test_get_table_info_many_matches_the_per_hand_read(db, hand_ids) -> None:
    many = db.get_table_info_many(hand_ids)
    assert set(many) == {str(h) for h in hand_ids}
    for hand_id in hand_ids:
        assert many[str(hand_id)] == db.get_table_info(hand_id)


def test_get_site_hand_no_many_matches_the_per_hand_read(db, hand_ids) -> None:
    many = db.get_site_hand_no_many(hand_ids)
    assert set(many) == {str(h) for h in hand_ids}
    for hand_id in hand_ids:
        assert many[str(hand_id)] == db.get_site_hand_no(hand_id)


def test_get_hand_positions_many_matches_the_per_hand_read(db, hand_ids) -> None:
    many = db.get_hand_positions_many(hand_ids)
    assert set(many) == {str(h) for h in hand_ids}
    for hand_id in hand_ids:
        assert many[str(hand_id)] == db.get_hand_positions(hand_id)


def test_get_seat_players_many_matches_the_per_hand_read(db, hand_ids) -> None:
    many = db.get_seat_players_many(hand_ids)
    assert set(many) == {str(h) for h in hand_ids}
    for hand_id in hand_ids:
        assert many[str(hand_id)] == db.get_seat_players(hand_id)


def test_get_cards_many_matches_the_per_hand_read(db, hand_ids) -> None:
    many = db.get_cards_many(hand_ids)
    assert set(many) == {str(h) for h in hand_ids}
    for hand_id in hand_ids:
        assert many[str(hand_id)] == db.get_cards(hand_id)


def test_get_common_cards_many_matches_the_per_hand_read(db, hand_ids) -> None:
    many = db.get_common_cards_many(hand_ids)
    assert set(many) == {str(h) for h in hand_ids}
    for hand_id in hand_ids:
        assert many[str(hand_id)] == list(db.get_common_cards(hand_id)["common"])


def test_get_table_min_stack_bb_many_matches_the_per_hand_read(db, hand_ids) -> None:
    many = db.get_table_min_stack_bb_many(hand_ids)
    assert set(many) == {str(h) for h in hand_ids}
    for hand_id in hand_ids:
        assert many[str(hand_id)] == db.get_table_min_stack_bb(hand_id)


def _service_with_mock_db() -> tuple[HudReadService, MagicMock]:
    config = MagicMock()
    config.get_supported_sites.return_value = []
    config.get_supported_games_parameters.return_value = {}
    database = MagicMock()
    database.backend = 0
    database.get_hand_positions.side_effect = lambda hand_id: {hand_id: "pos"}
    database.get_seat_players.side_effect = lambda hand_id: {1: {"player_id": hand_id}}
    database.get_table_min_stack_bb.return_value = 42
    database.get_cards.side_effect = lambda hand_id: {1: (hand_id,)}
    database.get_common_cards.return_value = {"common": (9, 9, 9)}
    database.get_stats_from_hand.side_effect = lambda hand_id, *_a, **_k: {"hand": hand_id}
    database.get_table_info.side_effect = lambda hand_id: (
        "table-a",
        6,
        "holdem",
        "ring",
        False,
        1,
        "site",
        6,
        None,
        None,
        None,
    )
    return HudReadService(config, database, hand_factory=lambda hand_id, *_a: f"hand-{hand_id}"), database


def test_prefetch_loads_each_detail_once_for_the_whole_batch() -> None:
    service, database = _service_with_mock_db()
    database.get_hand_positions_many.return_value = {"1": {"1": "pos"}, "2": {"2": "pos"}}
    database.get_seat_players_many.return_value = {"1": {}, "2": {}}
    database.get_cards_many.return_value = {"1": {1: (1,)}, "2": {1: (2,)}}
    database.get_common_cards_many.return_value = {"1": [9, 9, 9], "2": [9, 9, 9]}
    database.get_table_min_stack_bb_many.return_value = {"1": 42.0, "2": 43.0}

    prefetched = service._prefetch_primary_details(["1", "2"])

    assert prefetched["positions"] == {"1": {"1": "pos"}, "2": {"2": "pos"}}
    database.get_hand_positions_many.assert_called_once_with(["1", "2"])
    database.get_seat_players_many.assert_called_once()
    database.get_cards_many.assert_called_once()
    database.get_common_cards_many.assert_called_once()
    database.get_table_min_stack_bb_many.assert_called_once()
    # The per-hand reads were not used at all.
    database.get_hand_positions.assert_not_called()
    database.get_cards.assert_not_called()
    database.get_table_min_stack_bb.assert_not_called()


def test_read_hand_falls_back_to_per_hand_reads_when_the_batch_misses() -> None:
    service, database = _service_with_mock_db()
    # No *_many methods on this mock beyond autospec MagicMock: force the
    # fallback path by passing an empty prefetch.
    table_info = database.get_table_info("1")
    prepared = service._read_hand("1", table_info, {"hud_days": 30, "h_hud_days": 90}, "holdem", -1, False, {})

    assert prepared.positions == {"1": "pos"}
    assert prepared.table_stats["live_min_stack_bb"] == 42
    database.get_hand_positions.assert_called_once_with("1")
    database.get_table_min_stack_bb.assert_called_once_with("1")


def test_secondary_refresh_is_bounded_when_configured() -> None:
    service, database = _service_with_mock_db()
    database.get_stats_from_hands.return_value = {}
    contexts = tuple(
        HudTableReadContext(
            temp_key=f"table-{i}",
            last_hand_id=str(100 + i),
            hud_params={"hud_days": 30, "h_hud_days": 90},
            poker_game="holdem",
            game_type="ring",
            site_id=1,
            num_seats=6,
        )
        for i in range(3)
    )
    database.get_table_info.side_effect = lambda hand_id: (
        f"table-{hand_id}",
        6,
        "holdem",
        "ring",
        False,
        1,
        "site",
        6,
        None,
        None,
        None,
    )

    snapshot = service.read_batch(
        HudBatchReadRequest(
            sequence=1,
            hand_ids=(),
            hud_params={"hud_days": 30, "h_hud_days": 90, "max_secondary_tables_per_batch": 1},
            tables=contexts,
        ),
    )

    # Only one secondary table was refreshed; get_stats_from_hands ran once.
    database.get_stats_from_hands.assert_called_once()
    assert len(database.get_stats_from_hands.call_args[0][0]) == 1
    assert len(snapshot.hands) == 1


def test_secondary_refresh_is_unbounded_by_default() -> None:
    service, database = _service_with_mock_db()
    database.get_stats_from_hands.return_value = {}
    contexts = tuple(
        HudTableReadContext(
            temp_key=f"table-{i}",
            last_hand_id=str(100 + i),
            hud_params={"hud_days": 30, "h_hud_days": 90},
            poker_game="holdem",
            game_type="ring",
            site_id=1,
            num_seats=6,
        )
        for i in range(3)
    )
    database.get_table_info.side_effect = lambda hand_id: (
        f"table-{hand_id}",
        6,
        "holdem",
        "ring",
        False,
        1,
        "site",
        6,
        None,
        None,
        None,
    )

    snapshot = service.read_batch(
        HudBatchReadRequest(sequence=1, hand_ids=(), hud_params={"hud_days": 30, "h_hud_days": 90}, tables=contexts),
    )

    database.get_stats_from_hands.assert_called_once()
    assert len(database.get_stats_from_hands.call_args[0][0]) == 3
    assert len(snapshot.hands) == 3


def test_primary_hands_are_read_most_recent_first() -> None:
    """The active table's HUD should be painted first in a multi-table burst (#680)."""
    service, database = _service_with_mock_db()
    database.get_table_info.side_effect = lambda hand_id: (
        f"table-{hand_id}",
        6,
        "holdem",
        "ring",
        False,
        1,
        "site",
        6,
        None,
        None,
        None,
    )
    progress = []
    service.read_batch(
        HudBatchReadRequest(
            sequence=1,
            hand_ids=("101", "102", "103"),
            hud_params={"hud_days": 30, "h_hud_days": 90},
        ),
        progress_callback=progress.append,
    )
    published = [s.primary_order for s in progress if not s.identity_only]
    # 103 (last notified) is published before 102 before 101.
    assert published[0] == ("103",)
    assert published[-1] == ("101",)


def test_hand_batch_interval_is_configurable_with_default_200() -> None:
    """hud ui hand_batch_interval_ms overrides the 200 ms default (#680)."""
    from unittest.mock import MagicMock

    from fpdb_3_legacy.config_hud_ui import ConfigHudUiMixin

    host = ConfigHudUiMixin.__new__(ConfigHudUiMixin)
    host.ui = MagicMock()
    del host.ui.hand_batch_interval_ms  # attribute error path -> default
    host.ui.hand_batch_interval_ms = AttributeError  # ensure AttributeError
    try:
        del host.ui.hand_batch_interval_ms
    except AttributeError:
        pass
    params = host.get_hud_ui_parameters()
    assert params["hand_batch_interval_ms"] == 200

    host.ui = MagicMock()
    host.ui.hand_batch_interval_ms = "350"
    params = host.get_hud_ui_parameters()
    assert params["hand_batch_interval_ms"] == 350


def test_many_reads_canonicalise_string_hand_ids(db, hand_ids) -> None:
    """The HUD speaks string hand ids; SQL returns ints. The *_many reads must
    key their results by str(hand_id) so lookups never miss (#680 P0)."""
    str_ids = [str(h) for h in hand_ids]
    assert set(db.get_table_info_many(str_ids)) == set(str_ids)
    assert set(db.get_site_hand_no_many(str_ids)) == set(str_ids)
    for h in hand_ids:
        s = str(h)
        assert db.get_table_info_many(str_ids)[s] == db.get_table_info(h)
        assert db.get_site_hand_no_many(str_ids)[s] == db.get_site_hand_no(h)
        assert db.get_hand_positions_many(str_ids)[s] == db.get_hand_positions(h)
        assert db.get_seat_players_many(str_ids)[s] == db.get_seat_players(h)
        assert db.get_cards_many(str_ids)[s] == db.get_cards(h)
        assert db.get_common_cards_many(str_ids)[s] == list(db.get_common_cards(h)["common"])
        assert db.get_table_min_stack_bb_many(str_ids)[s] == db.get_table_min_stack_bb(h)


def test_read_batch_with_string_hand_ids_loads_full_stats(db, hand_ids) -> None:
    """End to end: string hand ids (as the ZMQ notifications carry) must produce
    fully loaded snapshots, not silently empty ones (#680 P0)."""
    from fpdb_3_legacy.hud_read_service import HudBatchReadRequest, HudReadService

    service = HudReadService(db.config, db)
    c = db.connection.cursor()
    c.execute("SELECT MIN(id) FROM Hands GROUP BY tableName")
    str_ids = [str(r[0]) for r in c.fetchall()[:3]]
    c.close()
    snapshot = service.read_batch(
        HudBatchReadRequest(
            sequence=1,
            hand_ids=tuple(str_ids),
            hud_params={
                "hud_days": 30,
                "h_hud_days": 90,
                "stat_range": "A",
                "h_stat_range": "A",
                "agg_bb_mult": 1000,
                "h_agg_bb_mult": 1000,
                "seats_style": "A",
                "seats_cust_nums_low": 1,
                "seats_cust_nums_high": 10,
                "h_seats_style": "A",
                "h_seats_cust_nums_low": 1,
                "h_seats_cust_nums_high": 10,
            },
        )
    )
    assert snapshot.failed_hand_ids == ()
    for hand_id in str_ids:
        prepared = snapshot.hands[hand_id]
        assert prepared.stat_dict, f"stat_dict empty for {hand_id}"
        assert prepared.positions, f"positions empty for {hand_id}"
        assert prepared.seat_players, f"seat_players empty for {hand_id}"
