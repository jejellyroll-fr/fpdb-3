import contextlib
import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

pytestmark = pytest.mark.qt
from PySide6.QtWidgets import QApplication

# import zmq

# Add parent directory to path before imports
sys.path.insert(0, str(Path(__file__).parent.parent))

source_file = Path(__file__).parent.parent / "fpdb_3_legacy" / "HUD_main.pyw"

# Create a mock 'WinTables' module
win_tables_module = types.ModuleType("WinTables")
win_tables_module.Table = MagicMock()

sys.modules["WinTables"] = win_tables_module
loader = importlib.machinery.SourceFileLoader("HUD_main", str(source_file))
spec = importlib.util.spec_from_loader(loader.name, loader)
HUD_main = importlib.util.module_from_spec(spec)
sys.modules["HUD_main"] = HUD_main
try:
    loader.exec_module(HUD_main)
except (ImportError, ModuleNotFoundError) as _e:
    pytest.skip(
        f"HUD_main eager-load failed (likely qt_material/PySide6 sub-module conflict "
        f"poisoned by another conftest mock): {_e}",
        allow_module_level=True,
    )


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture
def hud_main(app):
    # Crate mock
    options = MagicMock()
    options.dbname = "test_db"
    options.config = None
    options.errorsToConsole = False
    options.log_level = "INFO"
    options.xloc = None
    options.yloc = None

    import tempfile

    with (
        patch("HUD_main.Configuration.Config") as mock_config,
        patch("HUD_main.Configuration.set_logfile"),
        patch("HUD_main.Database.Database"),
        patch("HUD_main.Deck.Deck"),
        patch("HUD_main.ZMQReceiver"),
        patch("HUD_main.ZMQWorker"),
        patch("sys.exit"),
        patch("HUD_main.QCoreApplication.quit"),
    ):
        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance

        mock_config_instance.dir_log = tempfile.gettempdir()
        mock_config_instance.os_family = "Win7"
        mock_config_instance.get_hud_ui_parameters.return_value = {
            "deck_type": "default",
            "card_back": "blue",
            "card_wd": 72,
            "card_ht": 96,
            "hud_days": 30,
            "h_hud_days": 90,
        }
        mock_config_instance.graphics_path = tempfile.gettempdir()
        mock_config_instance.hhcs = {"test_site": MagicMock(converter="some_converter")}
        mock_config_instance.get_site_parameters.return_value = {
            "layout_set": "some_layout",
            "param1": "value1",
        }
        mock_config_instance.get_layout.return_value = "some_layout"

        hm = HUD_main.HudMain(options, db_name=options.dbname)
        yield hm

        hm.main_window.close()


# Verifies that all necessary attributes of the HUD_main instance are correctly initialized.
def test_hud_main_initialization(hud_main) -> None:
    assert hud_main.db_name == "test_db"
    assert hasattr(hud_main, "config")
    assert hasattr(hud_main, "db_connection")
    assert hasattr(hud_main, "hud_dict")
    assert hasattr(hud_main, "blacklist")
    assert hasattr(hud_main, "hud_params")
    assert hasattr(hud_main, "deck")
    assert hasattr(hud_main, "cache")
    assert hasattr(hud_main, "zmq_receiver")
    assert hasattr(hud_main, "zmq_worker")
    assert hasattr(hud_main, "main_window")
    assert hud_main._table_stat_set_overrides == {}


def test_table_stat_set_override_is_scoped_by_table_and_game(hud_main) -> None:
    hud_main.config.stat_sets = {"omaha_cg_expert": MagicMock()}

    hud_main.set_table_stat_set_override("table-a", "omahahi", "ring", "omaha_cg_expert")

    assert hud_main.get_table_stat_set_override("table-a", "omahahi", "ring") == "omaha_cg_expert"
    assert hud_main.get_table_stat_set_override("table-b", "omahahi", "ring") is None
    assert hud_main.get_table_stat_set_override("table-a", "holdem", "ring") is None

    hud_main.clear_table_stat_set_override("table-a")
    assert hud_main.get_table_stat_set_override("table-a", "omahahi", "ring") is None


# Ensures that the handle_message method correctly calls read_stdin when provided with a hand ID.
def test_handle_message(hud_main) -> None:
    """A hand is held for the batch rather than processed where it arrives."""
    with patch.object(hud_main, "read_stdin") as mock_read_stdin:
        hud_main.handle_message("test_hand_id")

    assert not mock_read_stdin.called
    assert hud_main._pending_hands == ["test_hand_id"]
    assert hud_main._hand_batch_timer.isActive()


# Checks that the destroy method properly closes connections and stops processes.
def test_destroy(hud_main) -> None:
    with (
        patch.object(hud_main.zmq_receiver, "close") as mock_close,
        patch.object(hud_main.zmq_worker, "stop") as mock_stop,
        patch("HUD_main.QCoreApplication.quit") as mock_quit,
    ):
        hud_main.destroy()
        hud_main.destroy()
        mock_close.assert_called_once()
        mock_stop.assert_called_once()
        mock_quit.assert_called_once()


# Verifies that check_tables calls the correct methods (client_destroyed, client_moved, client_resized) based on the table's status.
@pytest.mark.parametrize(
    ("status", "expected_method"),
    [
        ("client_destroyed", "client_destroyed"),
        ("client_moved", "client_moved"),
        ("client_resized", "client_resized"),
    ],
)
def test_check_tables(hud_main, status, expected_method) -> None:
    mock_hud = MagicMock()
    mock_hud.table.check_table.return_value = status
    hud_main.hud_dict = {"test_table": mock_hud}

    with patch.object(hud_main, expected_method) as mock_method:
        hud_main.check_tables()
        mock_method.assert_called_once_with(None, mock_hud)


def test_check_tables_skipped_during_drag(hud_main) -> None:
    """While a HUD window is dragged, check_tables must not poll geometry or
    re-raise windows (that stutters the drag on macOS)."""
    from fpdb_3_legacy import Aux_Base

    mock_hud = MagicMock()
    mock_hud.table.check_table.return_value = "client_moved"
    hud_main.hud_dict = {"test_table": mock_hud}

    Aux_Base.set_drag_active(True)
    try:
        with (
            patch.object(hud_main, "_handle_table_status") as mock_status,
            patch.object(hud_main, "_topify_mac_windows") as mock_topify,
        ):
            hud_main.check_tables()
            mock_status.assert_not_called()
            mock_topify.assert_not_called()
    finally:
        Aux_Base.set_drag_active(False)


# Ensures that create_HUD creates a new HUD and adds it to the hud_dict.
def test_create_hud(hud_main) -> None:
    with (
        patch.object(HUD_main.Hud, "Hud") as mock_hud,
        patch.object(hud_main, "idle_create") as mock_idle_create,
        patch.object(
            hud_main.config,
            "get_site_parameters",
            return_value={"layout_set": "some_layout", "param1": "value1"},
        ),
        patch.object(hud_main.config, "get_layout", return_value="some_layout"),
    ):
        mock_table = MagicMock()
        mock_table.site = "test_site"
        args = HUD_main.HUDCreationArgs(
            new_hand_id="new_hand_id",
            table=mock_table,
            temp_key="temp_key",
            max_seats=9,
            poker_game="poker_game",
            game_type="cash",
            stat_dict={},
            cards={},
        )

        hud_main.create_HUD(args)

        assert "temp_key" in hud_main.hud_dict
        mock_hud.assert_called_once()
        mock_idle_create.assert_called_once()


# Verifies that update_HUD properly calls idle_update.
def test_update_hud(hud_main) -> None:
    with patch.object(hud_main, "idle_update") as mock_idle_update:
        hud_main.update_HUD("new_hand_id", "table_name", hud_main.config)
        mock_idle_update.assert_called_once_with(
            "new_hand_id",
            "table_name",
            hud_main.config,
        )


#  Ensures that cached data is processed correctly in read_stdin and calls update_HUD.
def test_read_stdin_cached(hud_main) -> None:
    # Configuration env
    hud_main.config = MagicMock()
    hud_main.config.get_supported_sites.return_value = ["test_site"]
    hud_main.config.supported_sites = {"test_site": MagicMock(screen_name="test_hero")}
    test_hand_id = "test_hand_id"
    hud_main.cache[test_hand_id] = (
        "table_name",
        9,
        "poker_game",
        "cash",
        False,
        1,
        "test_site",
        9,
        "tour_number",
        "tab_number",
        None,  # tourney_name: unset for a cash table
    )
    temp_key = "table_name"
    hud_main.hud_dict[temp_key] = MagicMock()
    hud_main.hud_dict[temp_key].hud_params = {"hud_days": 30, "h_hud_days": 90}
    hud_main.hud_dict[temp_key].poker_game = "poker_game"
    hud_main.hud_dict[temp_key].max = 9
    hud_main.hud_dict[temp_key].aux_windows = []

    with (
        patch.object(hud_main.db_connection, "get_site_id", return_value=[(1,)]),
        patch.object(hud_main.db_connection, "get_player_id", return_value=123),
        patch.object(hud_main.db_connection, "init_hud_stat_vars"),
        patch.object(
            hud_main.db_connection,
            "get_stats_from_hand",
            return_value={"player1": {"screen_name": "test_hero"}},
        ),
        patch.object(hud_main, "get_cards", return_value={}),
        patch.object(hud_main, "update_HUD") as mock_update_hud,
        patch.object(hud_main, "_refresh_other_huds") as mock_refresh_other_huds,
    ):
        hud_main.read_stdin(test_hand_id)
        assert mock_update_hud.called, "update_HUD n'a pas été appelé"
        # The batch refreshes the other tables once, not each processed hand.
        assert not mock_refresh_other_huds.called


def test_refresh_other_huds_uses_each_tables_last_hand(hud_main) -> None:
    """A global refresh keeps every secondary HUD on its own table context."""
    hud_main.hud_dict = {
        "table-a": MagicMock(),
        "table-b": MagicMock(),
        "table-c": MagicMock(),
        "table-without-hand": MagicMock(),
        "table-without-info": MagicMock(),
    }
    hud_main._last_processed_hands = {
        "table-a": "hand-a",
        "table-b": "hand-b",
        "table-c": "hand-c",
        "table-without-info": "hand-missing",
    }
    table_infos = {
        "hand-b": ("table-b", 6, "holdem", "ring", False, 2, "SiteB", 5, None, None, None),
        "hand-c": ("table-c", 9, "omahahi", "tour", False, 3, "SiteC", 8, "T1", "1", "MTT"),
    }

    with (
        patch.object(hud_main, "_get_table_info", side_effect=table_infos.get) as get_table_info,
        patch.object(hud_main, "_refresh_secondary_hud") as update_existing_hud,
    ):
        hud_main._refresh_other_huds("table-a")

    assert get_table_info.call_args_list == [call("hand-b"), call("hand-c"), call("hand-missing")]
    assert update_existing_hud.call_args_list == [
        # stat_dict=None: with no hero known yet there is nothing to batch, so
        # each table fetches its own statistics, as this path always did.
        call("hand-b", "table-b", "ring", 2, 5, stat_dict=None),
        call("hand-c", "table-c", "tour", 3, 8, stat_dict=None),
    ]


def test_refresh_other_huds_isolates_secondary_table_failure(hud_main) -> None:
    """Regression: a broken secondary HUD must not block later HUD refreshes."""
    hud_main.hud_dict = {
        "source": MagicMock(),
        "broken": MagicMock(),
        "healthy": MagicMock(),
    }
    hud_main._last_processed_hands = {
        "source": "hand-source",
        "broken": "hand-broken",
        "healthy": "hand-healthy",
    }
    table_infos = {
        "hand-broken": ("broken", 6, "holdem", "ring", False, 1, "Site", 6, None, None, None),
        "hand-healthy": ("healthy", 6, "holdem", "ring", False, 1, "Site", 6, None, None, None),
    }
    hud_main.db_connection.connection.rollback.reset_mock()

    with (
        patch.object(hud_main, "_get_table_info", side_effect=table_infos.get),
        patch.object(
            hud_main,
            "_refresh_secondary_hud",
            side_effect=[RuntimeError("secondary HUD failed"), None],
        ) as update_existing_hud,
    ):
        hud_main._refresh_other_huds("source")

    assert update_existing_hud.call_args_list == [
        call("hand-broken", "broken", "ring", 1, 6, stat_dict=None),
        call("hand-healthy", "healthy", "ring", 1, 6, stat_dict=None),
    ]
    hud_main.db_connection.connection.rollback.assert_called_once_with()


def test_refresh_secondary_hud_only_rereads_the_statistics(hud_main) -> None:
    """A table with no new hand of its own is refreshed with one query, not six.

    Its seats, cards and table stats all describe the hand it already holds, so
    re-reading them returns what the HUD has. This runs once per open table per
    hand dealt anywhere, so the full update would cost a number of queries
    growing with the square of the number of tables.
    """
    hud = MagicMock()
    hud.hud_params = {"hud_days": 90, "h_hud_days": 30}
    hud_main.hud_dict = {"table-b": hud}
    hud_main.hero_ids = {2: 7}
    db = hud_main.db_connection
    for query in ("get_seat_players", "get_cards", "get_table_min_stack_bb"):
        getattr(db, query).reset_mock()

    aux = MagicMock()
    hud.aux_windows = [aux]

    with (
        patch.object(hud_main, "_merge_positions") as merge_positions,
        patch.object(hud_main, "update_HUD") as update_hud,
    ):
        hud_main._refresh_secondary_hud("hand-b", "table-b", "ring", 2, 5)

    db.get_stats_from_hand.assert_called_once_with(
        "hand-b",
        "ring",
        hud.hud_params,
        7,
        5,
        poker_game=hud.poker_game,
    )
    assert hud.stat_dict is db.get_stats_from_hand.return_value
    merge_positions.assert_called_once_with(db.get_stats_from_hand.return_value, "hand-b")

    # Redraw from the new stat_dict, without the path that rebuilds the hand
    # through hand_factory, re-reads the cards and updates the aux windows a
    # second time.
    aux.refresh_stats.assert_called_once_with("hand-b")
    assert not aux.update_gui.called
    assert not update_hud.called
    assert not hud.update.called

    # The four lookups that describe the unchanged hand.
    assert not db.get_seat_players.called
    assert not db.get_cards.called
    assert not db.get_table_min_stack_bb.called
    assert not any(aux.update_data.called for aux in hud.aux_windows)


def test_a_hands_seats_are_read_from_the_database_once(hud_main) -> None:
    """HandsPlayers is written with the hand and never rewritten afterwards.

    read_stdin only gets past _get_table_info for a hand whose own query
    already joined HandsPlayers, so by the time anything here asks, the rows
    are committed and settled. Reading them once per hand instead of once per
    caller matters because every open table asks again for the same hand.
    """
    db = hud_main.db_connection
    db.get_seat_players.reset_mock()
    db.get_seat_players.return_value = {1: {"player_id": 7, "screen_name": "hero"}}

    first = hud_main._seat_players("hand-a")
    second = hud_main._seat_players("hand-a")

    assert first is second
    db.get_seat_players.assert_called_once_with("hand-a")


def test_a_different_hand_is_read_on_its_own(hud_main) -> None:
    db = hud_main.db_connection
    db.get_seat_players.reset_mock()

    hud_main._seat_players("hand-a")
    hud_main._seat_players("hand-b")

    assert db.get_seat_players.call_args_list == [call("hand-a"), call("hand-b")]


def test_a_hands_positions_are_read_from_the_database_once(hud_main) -> None:
    db = hud_main.db_connection
    db.get_hand_positions.reset_mock()
    db.get_hand_positions.return_value = {7: "SB"}

    first = hud_main._hand_positions("hand-a")
    second = hud_main._hand_positions("hand-a")

    assert first is second
    db.get_hand_positions.assert_called_once_with("hand-a")


def test_seats_and_positions_do_not_answer_for_each_other(hud_main) -> None:
    # They are cached under one store, so the hand id alone cannot be the key.
    db = hud_main.db_connection
    db.get_seat_players.reset_mock()
    db.get_hand_positions.reset_mock()
    db.get_seat_players.return_value = {1: {"player_id": 7}}
    db.get_hand_positions.return_value = {7: "BB"}

    assert hud_main._seat_players("hand-a") == {1: {"player_id": 7}}
    assert hud_main._hand_positions("hand-a") == {7: "BB"}
    db.get_seat_players.assert_called_once_with("hand-a")
    db.get_hand_positions.assert_called_once_with("hand-a")


# Confirms that cached data is used if available when calling read_stdin.
# def test_read_stdin_cache_used(hud_main):
#     hud_main.cache = {"test_hand_id": ("table_name", 9, "poker_game", "cash", False, 1, "test_site", 9, 123, "tab")}
#     with patch("HUD_main.log.debug") as mock_log_debug:
#         hud_main.read_stdin("test_hand_id")
#         mock_log_debug.assert_any_call("Using cached data for hand test_hand_id")


# Tests the behavior of read_stdin when no cached data is available, ensuring it calls create_HUD
def test_read_stdin_not_cached(hud_main) -> None:
    hud_main.config = MagicMock()
    hud_main.config.get_supported_sites.return_value = ["test_site"]
    hud_main.config.supported_sites = {"test_site": MagicMock(screen_name="test_hero")}
    hud_main.config.get_site_parameters.return_value = {"aux_enabled": True}

    hud_main.Tables = MagicMock()
    hud_main.Tables.Table.return_value = MagicMock()
    test_hand_id = "test_hand_id"

    hud_main.cache = {}

    table_info = (
        "table_name",
        9,
        "poker_game",
        "tour",
        False,
        1,
        "test_site",
        9,
        123456,
        "Table 789",
        "tourney_name",
    )

    with (
        patch.object(hud_main.db_connection, "get_site_id", return_value=[(1,)]),
        patch.object(hud_main.db_connection, "get_player_id", return_value=123),
        patch.object(hud_main.db_connection, "get_table_info", return_value=table_info),
        patch.object(hud_main.db_connection, "init_hud_stat_vars"),
        patch.object(
            hud_main.db_connection,
            "get_stats_from_hand",
            return_value={"player1": {"screen_name": "test_hero"}},
        ),
        patch.object(hud_main, "get_cards", return_value={}),
        patch.object(hud_main.Tables, "Table", return_value=MagicMock()),
        patch.object(hud_main, "create_HUD") as mock_create_hud,
    ):
        hud_main.read_stdin(test_hand_id)
        assert mock_create_hud.called, "create_HUD n'a pas été appelé"


@pytest.mark.parametrize("table_name", ["", "   ", None])
def test_read_stdin_skips_hands_without_table_name(hud_main, table_name) -> None:
    table_info = (
        table_name,
        9,
        "holdem",
        "ring",
        False,
        1,
        "CoinPoker",
        6,
        None,
        None,
        None,
    )

    with (
        patch.object(hud_main, "_initialize_hero_data"),
        patch.object(hud_main, "_get_table_info", return_value=table_info),
        patch.object(hud_main, "_create_new_hud") as create_hud,
        patch.object(hud_main, "_update_existing_hud") as update_hud,
    ):
        hud_main.read_stdin("27827")

    create_hud.assert_not_called()
    update_hud.assert_not_called()
    assert "" not in hud_main.hud_dict


# Ensures that get_cards retrieves both player and community cards correctly.
def test_get_cards(hud_main) -> None:
    mock_db = MagicMock()
    mock_db.get_cards.return_value = {"player1": ["As", "Kh"]}
    mock_db.get_common_cards.return_value = {"common": ["Jd", "Qc", "Tc"]}
    hud_main.db_connection = mock_db

    cards = hud_main.get_cards("test_hand_id", "holdem")
    assert "player1" in cards
    assert "common" in cards


# Verifies that idle_kill removes the HUD from hud_dict and cleans up widgets.
def test_idle_kill(hud_main) -> None:
    mock_hud = MagicMock()
    hud_main.hud_dict["test_table"] = mock_hud
    hud_main.vb = MagicMock()

    hud_main.idle_kill("test_table")

    assert "test_table" not in hud_main.hud_dict
    mock_hud.kill.assert_called_once()
    hud_main.vb.removeWidget.assert_called_once()


# Checks exception handling in read_stdin when an error occurs in get_table_info.
def test_read_stdin_exception_handling(hud_main) -> None:
    hud_main.config = MagicMock()
    hud_main.config.get_supported_sites.return_value = ["test_site"]
    hud_main.config.get_site_parameters.return_value = {"aux_enabled": True}
    hud_main.hero = {}
    hud_main.hero_ids = {}

    hud_main.cache = {}

    test_hand_id = "test_hand_id"

    with (
        patch.object(
            hud_main.db_connection,
            "get_table_info",
            side_effect=Exception("Database error"),
        ),
        patch.object(hud_main, "destroy") as mock_destroy,
    ):
        hud_main.read_stdin(test_hand_id)

    mock_destroy.assert_not_called()


# Ensures that ZMQWorker.stop stops the worker properly.
def test_zmqworker_stop() -> None:
    zmq_receiver = MagicMock()
    worker = HUD_main.ZMQWorker(zmq_receiver)
    worker.wait = MagicMock()
    worker.is_running = True

    worker.stop()
    assert not worker.is_running
    worker.wait.assert_called_once()


# Verifies that a heartbeat log is generated when no messages are received.
# def test_process_message_heartbeat(hud_main):
#     zmq_receiver = HUD_main.ZMQReceiver()
#     zmq_receiver.socket = MagicMock()
#     zmq_receiver.poller = MagicMock()

#     zmq_receiver.poller.poll.return_value = {}

#     with patch("HUD_main.log.debug") as mock_log_debug:
#         zmq_receiver.process_message()
#         mock_log_debug.assert_called_with("Heartbeat: No message received")


# Tests the run loop of ZMQWorker, ensuring it stops after processing a message.
def test_zmqworker_run() -> None:
    zmq_receiver = MagicMock()
    worker = HUD_main.ZMQWorker(zmq_receiver)

    # Limit the loop to avoid an infinite blockage
    worker.is_running = True

    # Use of `side_effect` to stop the loop after the first call to `process_message`.
    def stop_after_one_iteration(*args, **kwargs) -> None:
        worker.is_running = False

    with (
        patch("time.sleep", return_value=None),
        patch.object(
            zmq_receiver,
            "process_message",
            side_effect=stop_after_one_iteration,
        ) as mock_process_message,
    ):
        worker.run()
        mock_process_message.assert_called_once()


# Ensures that process_message logs the correct hand ID received from the socket.
# def test_process_message(hud_main):
#     zmq_receiver = HUD_main.ZMQReceiver()
#     zmq_receiver.socket = MagicMock()
#     zmq_receiver.poller = MagicMock()

#     zmq_receiver.poller.poll.return_value = {zmq_receiver.socket: zmq.POLLIN}
#     zmq_receiver.socket.recv_string.return_value = "hand_id"

#     with patch("HUD_main.log.debug") as mock_log_debug:
#         zmq_receiver.process_message()
#         mock_log_debug.assert_called_with("Received hand ID: hand_id")


# Verifies that table_title_changed calls kill_hud when the table's title changes significantly.
def test_table_title_changed_calls_kill_hud(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.table.key = "test_table"
    mock_hud.table.title = "new_title"
    hud_main.hud_dict["test_table"] = mock_hud

    # Mock the smart_hud_manager to return that title changed and should restart
    hud_main.smart_hud_manager = MagicMock()
    hud_main.smart_hud_manager.has_table_title_changed.return_value = True
    hud_main.smart_hud_manager.should_restart_hud.return_value = (True, "Title changed significantly")
    hud_main.smart_hud_manager.record_restart = MagicMock()

    with patch.object(hud_main, "kill_hud") as mock_kill_hud:
        hud_main.table_title_changed(None, mock_hud)
        mock_kill_hud.assert_called_once_with(None, "test_table")


# Ensures that table_is_stale calls kill_hud for stale tables.
def test_table_is_stale_calls_kill_hud(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.table.key = "test_table"
    hud_main.hud_dict["test_table"] = mock_hud

    with patch.object(hud_main, "kill_hud") as mock_kill_hud:
        hud_main.table_is_stale(mock_hud)
        mock_kill_hud.assert_called_once_with(None, "test_table")


# Verifies that blacklist_hud correctly removes a HUD from hud_dict and adds it to the blacklist.
def test_blacklist_hud(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.tablenumber = 123
    hud_main.hud_dict["test_table"] = mock_hud
    hud_main.vb = MagicMock()

    hud_main.blacklist_hud(None, "test_table")

    assert 123 in hud_main.blacklist
    assert "test_table" not in hud_main.hud_dict
    mock_hud.kill.assert_called_once()
    hud_main.vb.removeWidget.assert_called_once()


# Ensures that handle_worker_error logs an error message.
# def test_handle_worker_error(hud_main):
#     with patch("HUD_main.log.error") as mock_log_error:
#         hud_main.handle_worker_error("Test error message")
#         mock_log_error.assert_called_once_with("ZMQWorker encountered an error: Test error message")


# Verifies that close_event_handler calls destroy and accepts the event.
def test_close_event_handler(hud_main) -> None:
    mock_event = MagicMock()
    with patch.object(hud_main, "destroy") as mock_destroy:
        hud_main.close_event_handler(mock_event)
        mock_destroy.assert_called_once()
        mock_event.accept.assert_called_once()


# Ensures that idle_move moves the table and auxiliary windows.
def test_idle_move(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.aux_windows = [MagicMock()]
    hud_main.idle_move(mock_hud)

    mock_hud.move_table_position.assert_called_once()
    for aw in mock_hud.aux_windows:
        aw.move_windows.assert_called_once()


# Verifies that idle_resize resizes the table and auxiliary windows.
def test_idle_resize(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.aux_windows = [MagicMock()]
    hud_main.idle_resize(mock_hud)

    mock_hud.resize_windows.assert_called_once()
    for aw in mock_hud.aux_windows:
        aw.resize_windows.assert_called_once()


# Checks that kill_hud removes the HUD from hud_dict and cleans up associated widgets.
def test_kill_hud(hud_main) -> None:
    mock_hud = MagicMock()
    hud_main.hud_dict["test_table"] = mock_hud
    hud_main.vb = MagicMock()

    hud_main.kill_hud(None, "test_table")

    assert "test_table" not in hud_main.hud_dict
    mock_hud.kill.assert_called_once()
    hud_main.vb.removeWidget.assert_called_once()


# Verifies that client_moved calls idle_move for the given HUD.
def test_client_moved(hud_main) -> None:
    mock_hud = MagicMock()
    with patch.object(hud_main, "idle_move") as mock_idle_move:
        hud_main.client_moved(None, mock_hud)
        mock_idle_move.assert_called_once_with(mock_hud)


# Ensures that client_resized calls idle_resize for the given HUD.
def test_client_resized(hud_main) -> None:
    mock_hud = MagicMock()
    with patch.object(hud_main, "idle_resize") as mock_idle_resize:
        hud_main.client_resized(None, mock_hud)
        mock_idle_resize.assert_called_once_with(mock_hud)


# Checks that client_destroyed calls kill_hud for the appropriate HUD.
def test_client_destroyed(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.table.key = "test_table"
    with patch.object(hud_main, "kill_hud") as mock_kill_hud:
        hud_main.client_destroyed(None, mock_hud)
        mock_kill_hud.assert_called_once_with(None, "test_table")


# Verifies that idle_create creates a new HUD and adds it to hud_dict, along with logging.
def test_idle_create(hud_main) -> None:
    with patch.object(HUD_main, "log") as mock_log:
        # Configuration
        mock_hud = MagicMock()
        mock_hud.tablehudlabel = MagicMock()
        hud_main.hud_dict = {"test_table": mock_hud}
        hud_main.vb = MagicMock()

        table = MagicMock()
        table.site = "test_site"
        table.number = 123

        args = HUD_main.HUDCreationArgs(
            new_hand_id="new_hand_id",
            table=table,
            temp_key="test_table",
            max_seats=9,
            poker_game="holdem",
            game_type="cash",
            stat_dict={},
            cards={},
        )

        with (
            patch.object(hud_main, "get_cards", return_value=args.cards),
            patch.object(hud_main.hud_dict["test_table"], "create") as mock_create,
            patch.object(hud_main.hud_dict["test_table"], "aux_windows", []),
        ):
            # Call idle_create
            hud_main.idle_create(args)

            # Checks
            hud_main.hud_dict[args.temp_key].tablehudlabel

            # Check that vb.addWidget is called
            with contextlib.suppress(AssertionError):
                hud_main.vb.addWidget.assert_called_once()

            # Check attributes
            assert hud_main.hud_dict[args.temp_key].tablehudlabel is not None, "tablehudlabel is None"
            assert hud_main.hud_dict[args.temp_key].tablenumber == table.number, "tablenumber mismatch"

            # Check call
            with contextlib.suppress(AssertionError):
                mock_create.assert_called_once_with(
                    args.new_hand_id,
                    hud_main.config,
                    args.stat_dict,
                )

        # Check logs - the method creates a label with site and temp_key
        mock_log.debug.assert_any_call("adding label %s", f"{table.site} - {args.temp_key}")


def test_idle_update_hands_the_new_hand_to_the_hud(hud_main) -> None:
    temp_key = "table_name"
    mock_hud = MagicMock()
    hud_main.hud_dict[temp_key] = mock_hud
    mock_hud.aux_windows = [MagicMock()]

    hud_main.idle_update("new_hand_id", temp_key, hud_main.config)

    mock_hud.update.assert_called_once_with("new_hand_id", hud_main.config)


def test_idle_update_leaves_the_aux_windows_to_the_hud(hud_main) -> None:
    """Hud.update owns the new-hand cycle, and owns it alone.

    Refreshing them here as well drew each window twice per hand. For the
    mucked-cards windows that is not merely wasted work: theirs appends a row
    to the list and re-shows the cards, so every hand was replayed.
    """
    temp_key = "table_name"
    mock_hud = MagicMock()
    aux = MagicMock()
    mock_hud.aux_windows = [aux]
    hud_main.hud_dict[temp_key] = mock_hud

    hud_main.idle_update("new_hand_id", temp_key, hud_main.config)

    assert not aux.update_gui.called


def test_idle_update_survives_a_hud_that_cannot_update(hud_main) -> None:
    temp_key = "table_name"
    mock_hud = MagicMock()
    mock_hud.aux_windows = []
    mock_hud.update.side_effect = RuntimeError("update failed")
    hud_main.hud_dict[temp_key] = mock_hud

    hud_main.idle_update("new_hand_id", temp_key, hud_main.config)


# Confirms that idle_kill removes widgets from the layout and calls the HUD's kill method.
def test_idle_kill_widget_removal(hud_main) -> None:
    mock_hud = MagicMock()
    hud_main.hud_dict["test_table"] = mock_hud
    hud_main.vb = MagicMock()
    # Grab the label now: idle_kill clears the attribute once the label is gone.
    label = mock_hud.tablehudlabel

    # Call idle_kill
    hud_main.idle_kill("test_table")

    # Assert widget was removed from layout, then destroyed rather than detached
    hud_main.vb.removeWidget.assert_called_once_with(label)
    label.deleteLater.assert_called_once()
    label.setParent.assert_not_called()
    assert mock_hud.tablehudlabel is None

    # Assert kill method on HUD was called
    mock_hud.kill.assert_called_once()

    # Assert HUD is removed from the dictionary
    assert "test_table" not in hud_main.hud_dict


# Ensures that check_tables calls the correct methods for different table statuses.
@pytest.mark.parametrize(
    "status",
    ["client_destroyed", "client_moved", "client_resized"],
)
def test_check_tables_full_coverage(hud_main, status) -> None:
    mock_hud = MagicMock()
    mock_hud.table.check_table.return_value = status
    hud_main.hud_dict = {"test_table": mock_hud}

    # Map status to expected method
    method_map = {
        "client_destroyed": "client_destroyed",
        "client_moved": "client_moved",
        "client_resized": "client_resized",
    }

    with patch.object(hud_main, method_map[status]) as mock_method:
        hud_main.check_tables()
        mock_method.assert_called_once_with(None, mock_hud)


#  Verifies that the appropriate idle methods (idle_move, idle_resize, kill_hud) are called for different client actions.
@pytest.mark.parametrize(
    ("method_name", "expected_args"),
    [
        ("client_moved", (MagicMock(),)),
        ("client_resized", (MagicMock(),)),
        ("client_destroyed", (None, MagicMock().table.key)),
    ],
)
def test_client_methods(hud_main, method_name, expected_args) -> None:
    mock_hud = MagicMock()

    # Map method to expected idle method
    idle_method = {
        "client_moved": "idle_move",
        "client_resized": "idle_resize",
        "client_destroyed": "kill_hud",
    }[method_name]

    with patch.object(hud_main, idle_method) as mock_idle_method:
        getattr(hud_main, method_name)(None, mock_hud)
        if method_name == "client_destroyed":
            mock_idle_method.assert_called_once_with(
                expected_args[0],
                mock_hud.table.key,
            )
        else:
            mock_idle_method.assert_called_once_with(mock_hud)


# Ensures that auxiliary windows are created and updated properly.
# def test_aux_windows_creation_and_update(hud_main):
#     mock_aux_window = MagicMock()
#     hud_main.hud_dict["test_key"] = MagicMock()
#     hud_main.hud_dict["test_key"].aux_windows = [mock_aux_window]

#     with patch("HUD_main.log.debug") as mock_log_debug:
#         hud_main.idle_create("new_hand_id", MagicMock(), "test_key", 9, "poker_game", "cash", {}, {})

#         mock_aux_window.create.assert_called_once()
#         mock_aux_window.update_gui.assert_called_once_with("new_hand_id")
#         mock_log_debug.assert_called_with("idle_create new_hand_id new_hand_id")


#  Verifies that ZMQReceiver.close properly closes the socket and context, and logs the closure.
# def test_zmqreceiver_close(hud_main):
#     zmq_receiver = HUD_main.ZMQReceiver(port="5555")

#     with (
#         patch.object(zmq_receiver.socket, "close") as mock_socket_close,
#         patch.object(zmq_receiver.context, "term") as mock_context_term,
#         patch("HUD_main.log.info") as mock_log_info,
#     ):
#         zmq_receiver.close()

#         # Ensure socket.close and context.term were called
#         mock_socket_close.assert_called_once()
#         mock_context_term.assert_called_once()

#         # Ensure the closure was logged
#         mock_log_info.assert_called_with("ZMQ receiver closed")


# Ensures that process_message returns early and does not poll if the socket is already closed.
def test_process_message_closed_socket() -> None:
    with patch("zmq.Context"), patch("zmq.Poller") as mock_poller_cls:
        receiver = HUD_main.ZMQReceiver()
        receiver.socket.closed = True

        receiver.process_message()

        mock_poller_cls.return_value.poll.assert_not_called()


# Ensures that ENOTSOCK ZMQErrors are handled gracefully without raising traceback exceptions.
def test_process_message_enotsock_handling() -> None:
    import zmq

    with patch("zmq.Context"), patch("zmq.Poller") as mock_poller_cls:
        receiver = HUD_main.ZMQReceiver()
        receiver.socket.closed = False

        error = zmq.ZMQError()
        if hasattr(zmq, "ENOTSOCK"):
            error.errno = zmq.ENOTSOCK
        else:
            error.errno = 88  # Fallback for standard Unix ENOTSOCK

        mock_poller_cls.return_value.poll.side_effect = error

        with patch("HUD_main.log") as mock_log:
            receiver.process_message()
            mock_log.info.assert_any_call("ZMQ socket closed during poll")
            mock_log.exception.assert_not_called()


def test_advance_live_positions_rotates_button(hud_main) -> None:
    """Positional panels need the CURRENT hand's position; _advance_live_positions
    moves the button one seat from the last imported hand (works even when a
    player is sitting out, since they are still seated)."""
    # 3 seated players; last hand seat1=BTN, seat2=SB, seat3=BB (seat3 could be
    # an absent hero -- still seated, still in the rotation).
    hud_main.db_connection.get_seat_players.return_value = {
        1: {"player_id": 11},
        2: {"player_id": 12},
        3: {"player_id": 13},
    }
    stat_dict = {
        11: {"position": "0"},  # BTN last hand
        12: {"position": "S"},  # SB
        13: {"position": "B"},  # BB
    }
    hud_main._advance_live_positions(stat_dict, "H1")
    # button advances to seat2: seat2=BTN, seat3=SB, seat1=BB
    assert stat_dict[12]["live_position"] == "0"
    assert stat_dict[13]["live_position"] == "S"
    assert stat_dict[11]["live_position"] == "B"


def test_advance_live_positions_no_button_is_noop(hud_main) -> None:
    """If no button can be identified, leave live_position unset so callers fall
    back to the imported position."""
    hud_main.db_connection.get_seat_players.return_value = {
        1: {"player_id": 11},
        2: {"player_id": 12},
    }
    stat_dict = {11: {"position": "S"}, 12: {"position": "B"}}
    hud_main._advance_live_positions(stat_dict, "H1")
    assert "live_position" not in stat_dict[11]
    assert "live_position" not in stat_dict[12]


# --- batching -----------------------------------------------------------------
#
# A round of twelve tables arrives as twelve notifications a few milliseconds
# apart. Processing each on arrival meant refreshing twelve HUDs twelve times.


def _table_info(table_name: str) -> tuple:
    return (table_name, 6, "holdem", "ring", False, 1, "Site", 6, None, None, None)


def test_hands_arriving_together_are_processed_as_one_batch(hud_main) -> None:
    hands = {"h-a": _table_info("table-a"), "h-b": _table_info("table-b")}
    for hand_id in hands:
        hud_main._enqueue_hand(hand_id)

    with (
        patch.object(hud_main, "_get_table_info", side_effect=hands.get),
        patch.object(hud_main, "read_stdin", side_effect=["table-a", "table-b"]) as read_stdin,
        patch.object(hud_main, "_refresh_other_huds") as refresh_other,
    ):
        hud_main._drain_pending_hands()

    assert read_stdin.call_args_list == [call("h-a"), call("h-b")]
    # One refresh for the whole batch, naming both tables as already done.
    refresh_other.assert_called_once_with({"table-a", "table-b"})


def test_only_the_last_hand_of_a_table_is_processed(hud_main) -> None:
    """An earlier hand would only be overwritten by the next one."""
    hands = {"h-1": _table_info("table-a"), "h-2": _table_info("table-a"), "h-3": _table_info("table-b")}
    for hand_id in hands:
        hud_main._enqueue_hand(hand_id)

    with (
        patch.object(hud_main, "_get_table_info", side_effect=hands.get),
        patch.object(hud_main, "read_stdin") as read_stdin,
        patch.object(hud_main, "_refresh_other_huds"),
    ):
        hud_main._drain_pending_hands()

    assert read_stdin.call_args_list == [call("h-2"), call("h-3")]


def test_a_hand_whose_table_is_unknown_still_takes_the_normal_path(hud_main) -> None:
    # Not yet committed to the database: it keeps the behaviour it had, which
    # is to be looked at and logged rather than silently dropped here.
    hud_main._enqueue_hand("h-known")
    hud_main._enqueue_hand("h-uncommitted")

    with (
        patch.object(hud_main, "_get_table_info", side_effect={"h-known": _table_info("table-a")}.get),
        patch.object(hud_main, "read_stdin", side_effect=["table-a", None]) as read_stdin,
        patch.object(hud_main, "_refresh_other_huds") as refresh_other,
    ):
        hud_main._drain_pending_hands()

    assert read_stdin.call_args_list == [call("h-known"), call("h-uncommitted")]
    refresh_other.assert_called_once_with({"table-a"})


def test_the_queue_is_emptied_by_the_batch(hud_main) -> None:
    hud_main._enqueue_hand("h-a")

    with (
        patch.object(hud_main, "_get_table_info", side_effect={"h-a": _table_info("table-a")}.get),
        patch.object(hud_main, "read_stdin"),
        patch.object(hud_main, "_refresh_other_huds"),
    ):
        hud_main._drain_pending_hands()

    assert hud_main._pending_hands == []


def test_an_empty_batch_does_nothing(hud_main) -> None:
    with patch.object(hud_main, "_refresh_other_huds") as refresh_other:
        hud_main._drain_pending_hands()

    assert not refresh_other.called


def test_the_window_starts_at_the_first_hand_rather_than_the_last(hud_main) -> None:
    """A sliding window would let continuous traffic postpone the batch."""
    hud_main._enqueue_hand("h-a")

    with patch.object(hud_main._hand_batch_timer, "start") as start:
        hud_main._enqueue_hand("h-b")

    assert not start.called
    assert hud_main._pending_hands == ["h-a", "h-b"]


def test_one_failing_hand_does_not_stop_the_batch(hud_main) -> None:
    hands = {"h-bad": _table_info("table-a"), "h-good": _table_info("table-b")}
    for hand_id in hands:
        hud_main._enqueue_hand(hand_id)
    hud_main.db_connection.connection.rollback.reset_mock()

    with (
        patch.object(hud_main, "_get_table_info", side_effect=hands.get),
        patch.object(hud_main, "read_stdin", side_effect=[RuntimeError("boom"), "table-b"]) as read_stdin,
        patch.object(hud_main, "_refresh_other_huds") as refresh_other,
    ):
        hud_main._drain_pending_hands()

    assert read_stdin.call_args_list == [call("h-bad"), call("h-good")]
    hud_main.db_connection.connection.rollback.assert_called_once_with()
    # The table that failed is *not* excluded: it never got its new hand, so
    # it still needs the statistics refresh.
    refresh_other.assert_called_once_with({"table-b"})


def test_shutting_down_drops_a_waiting_batch(hud_main) -> None:
    # It would otherwise fire against a closed database connection.
    hud_main._enqueue_hand("h-a")

    with (
        patch.object(hud_main.zmq_receiver, "close"),
        patch.object(hud_main.zmq_worker, "stop"),
        patch("HUD_main.QCoreApplication.quit"),
    ):
        hud_main.destroy()

    assert not hud_main._hand_batch_timer.isActive()
    assert hud_main._pending_hands == []


def test_a_round_of_twelve_tables_costs_twelve_refreshes(hud_main) -> None:
    """The whole point of the batch, measured rather than asserted.

    Twelve tables each dealing one hand used to mean twelve passes over twelve
    HUDs: twelve full updates plus a hundred and thirty-two secondary ones, all
    of them aggregated queries on the thread that has to finish before the
    player acts. Batched, every table has a hand of its own, so none of them
    needs the secondary path at all.
    """
    tables = [f"table-{index:02d}" for index in range(12)]
    hands = {f"h-{table}": _table_info(table) for table in tables}
    hud_main.hud_dict = dict.fromkeys(tables, MagicMock())
    for hand_id in hands:
        hud_main._enqueue_hand(hand_id)

    with (
        patch.object(hud_main, "_get_table_info", side_effect=hands.get),
        patch.object(hud_main, "read_stdin") as read_stdin,
        patch.object(hud_main, "_refresh_secondary_hud") as secondary,
    ):
        hud_main._drain_pending_hands()

    assert read_stdin.call_count == 12
    assert secondary.call_count == 0


def test_a_table_that_missed_the_round_is_refreshed_once(hud_main) -> None:
    # The secondary path is for tables that dealt nothing this batch, and it
    # runs once for them however many hands the batch carried.
    hands = {"h-a": _table_info("table-a"), "h-b": _table_info("table-b")}
    hud_main.hud_dict = {"table-a": MagicMock(), "table-b": MagicMock(), "table-idle": MagicMock()}
    hud_main._last_processed_hands = {"table-idle": "h-idle"}
    for hand_id in hands:
        hud_main._enqueue_hand(hand_id)

    with (
        patch.object(hud_main, "_get_table_info", side_effect={**hands, "h-idle": _table_info("table-idle")}.get),
        patch.object(hud_main, "read_stdin"),
        patch.object(hud_main, "_refresh_secondary_hud") as secondary,
    ):
        hud_main._drain_pending_hands()

    secondary.assert_called_once_with("h-idle", "table-idle", "ring", 1, 6, stat_dict=None)


# --- the two aux families -----------------------------------------------------
#
# A table's aux windows are not all statistics windows. The mucked-cards ones
# react to a *new* hand: theirs appends a row to a list and re-shows the cards.
# A statistics refresh happens when some *other* table dealt, so anything that
# replays a hand here shows the player something they already saw.


def _stats_aux() -> MagicMock:
    from fpdb_3_legacy.Aux_Hud import SimpleHUD

    return MagicMock(spec=SimpleHUD)


def _mucked_aux() -> MagicMock:
    from fpdb_3_legacy.Mucked import Flop_Mucked

    return MagicMock(spec=Flop_Mucked)


def test_only_the_statistics_windows_redraw_on_a_secondary_refresh(hud_main) -> None:
    hud = MagicMock()
    hud.hud_params = {"hud_days": 90, "h_hud_days": 30}
    stats, mucked = _stats_aux(), _mucked_aux()
    hud.aux_windows = [stats, mucked]
    hud_main.hud_dict = {"table-b": hud}
    hud_main.hero_ids = {2: 7}

    with patch.object(hud_main, "_merge_positions"):
        hud_main._refresh_secondary_hud("hand-b", "table-b", "ring", 2, 5)

    # Both are asked; only the statistics one has anything to do, and neither
    # is sent down the new-hand path.
    stats.refresh_stats.assert_called_once_with("hand-b")
    mucked.refresh_stats.assert_called_once_with("hand-b")
    assert not stats.update_gui.called
    assert not mucked.update_gui.called


def test_the_mucked_windows_do_nothing_on_a_statistics_refresh() -> None:
    """The contract itself: only a statistics HUD implements refresh_stats."""
    from fpdb_3_legacy.Aux_Base import AuxWindow
    from fpdb_3_legacy.Aux_Hud import SimpleHUD
    from fpdb_3_legacy.Mucked import Flop_Mucked, Stud_mucked

    assert AuxWindow.refresh_stats is Flop_Mucked.refresh_stats
    assert AuxWindow.refresh_stats is Stud_mucked.refresh_stats
    assert SimpleHUD.refresh_stats is not AuxWindow.refresh_stats


def test_a_mucked_window_does_not_replay_a_hand_when_asked_for_statistics() -> None:
    # Stud_list.update_gui appends a row per call, which is what a statistics
    # refresh must never trigger. The no-op is what keeps it from happening.
    from fpdb_3_legacy.Mucked import Stud_mucked

    aux = MagicMock(spec=Stud_mucked)
    aux.refresh_stats = Stud_mucked.refresh_stats.__get__(aux)

    assert aux.refresh_stats("hand-b") is None
    assert not aux.update_gui.called


def test_one_broken_aux_window_does_not_stop_the_others(hud_main) -> None:
    hud = MagicMock()
    hud.hud_params = {"hud_days": 90, "h_hud_days": 30}
    broken, healthy = _stats_aux(), _stats_aux()
    broken.refresh_stats.side_effect = RuntimeError("aux failed")
    hud.aux_windows = [broken, healthy]
    hud_main.hud_dict = {"table-b": hud}
    hud_main.hero_ids = {2: 7}

    with patch.object(hud_main, "_merge_positions"):
        hud_main._refresh_secondary_hud("hand-b", "table-b", "ring", 2, 5)

    healthy.refresh_stats.assert_called_once_with("hand-b")


def test_a_table_whose_hand_failed_is_still_refreshed(hud_main) -> None:
    """It never received its new hand, so it is as stale as an idle table."""
    hands = {"h-bad": _table_info("table-bad"), "h-ok": _table_info("table-ok")}
    hud_main.hud_dict = {"table-bad": MagicMock(), "table-ok": MagicMock()}
    hud_main._last_processed_hands = {"table-bad": "h-earlier"}
    for hand_id in hands:
        hud_main._enqueue_hand(hand_id)

    with (
        patch.object(hud_main, "_get_table_info", side_effect={**hands, "h-earlier": _table_info("table-bad")}.get),
        patch.object(hud_main, "read_stdin", side_effect=[RuntimeError("boom"), "table-ok"]),
        patch.object(hud_main, "_refresh_secondary_hud") as secondary,
    ):
        hud_main._drain_pending_hands()

    secondary.assert_called_once_with("h-earlier", "table-bad", "ring", 1, 6, stat_dict=None)


def test_a_table_skipped_rather_than_updated_is_still_refreshed(hud_main) -> None:
    # read_stdin answers None when it decided not to touch the HUD at all.
    hud_main.hud_dict = {"table-a": MagicMock()}
    hud_main._last_processed_hands = {"table-a": "h-earlier"}
    hud_main._enqueue_hand("h-a")

    with (
        patch.object(
            hud_main,
            "_get_table_info",
            side_effect={"h-a": _table_info("table-a"), "h-earlier": _table_info("table-a")}.get,
        ),
        patch.object(hud_main, "read_stdin", return_value=None),
        patch.object(hud_main, "_refresh_secondary_hud") as secondary,
    ):
        hud_main._drain_pending_hands()

    secondary.assert_called_once_with("h-earlier", "table-a", "ring", 1, 6, stat_dict=None)


# --- a tournament table the player was moved away from ------------------------


def _tour_hud(table_key: str) -> MagicMock:
    hud = MagicMock()
    hud.table.key = table_key
    return hud


def test_the_window_of_the_table_left_behind_is_taken_down(hud_main) -> None:
    hud_main.hud_dict = {"1160377 Table 4": _tour_hud("1160377 Table 4")}

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tournament_table_changes("tour", "1160377 Table 9", "1160377")

    stale.assert_called_once_with(hud_main.hud_dict["1160377 Table 4"])


def test_another_tournament_is_left_where_it_is(hud_main) -> None:
    hud_main.hud_dict = {"81498 Table 4": _tour_hud("81498 Table 4")}

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tournament_table_changes("tour", "1160377 Table 9", "1160377")

    assert not stale.called


def test_a_tournament_whose_number_merely_starts_the_same_is_left_alone(hud_main) -> None:
    """A prefix match made tournament 116 the same as 1160391."""
    hud_main.hud_dict = {"1160391 Table 4": _tour_hud("1160391 Table 4")}

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tournament_table_changes("tour", "116 Table 9", "116")

    assert not stale.called


def test_every_table_of_the_tournament_left_behind_is_taken_down(hud_main) -> None:
    # Re-entry tournaments can leave more than one behind.
    hud_main.hud_dict = {
        "1160377 Table 4": _tour_hud("1160377 Table 4"),
        "1160377 Table 7": _tour_hud("1160377 Table 7"),
        "81498 Table 1": _tour_hud("81498 Table 1"),
    }

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tournament_table_changes("tour", "1160377 Table 9", "1160377")

    assert stale.call_count == 2


def test_a_ring_table_is_never_treated_as_a_move(hud_main) -> None:
    hud_main.hud_dict = {"some table": _tour_hud("some table")}

    with patch.object(hud_main, "table_is_stale") as stale:
        assert hud_main._handle_tournament_table_changes("ring", "some other table", "") is False

    assert not stale.called
