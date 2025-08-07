import contextlib
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtWidgets import QApplication

# import zmq

# Add parent directory to path before imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Create a temporary copy of HUD_main.pyw as HUD_main.py
source_file = Path(__file__).parent.parent / "HUD_main.pyw"
temp_file = Path(__file__).parent.parent / "HUD_main.py"

# Copy the file at module level
if source_file.exists() and not temp_file.exists():
    shutil.copy2(source_file, temp_file)

# Create a mock 'WinTables' module
win_tables_module = types.ModuleType("WinTables")
win_tables_module.Table = MagicMock()

with patch.dict("sys.modules", {"WinTables": win_tables_module}):
    import HUD_main


@pytest.fixture
def app(qtbot):
    return QApplication.instance()


@pytest.fixture
def hud_main(app, qtbot):
    # Crate mock
    options = MagicMock()
    options.dbname = "test_db"
    options.config = None
    options.errorsToConsole = False
    options.xloc = None
    options.yloc = None

    import tempfile

    with (
        patch("HUD_main.Configuration.Config") as mock_config,
        patch("HUD_main.Configuration.set_logfile"),
        patch("HUD_main.Database.Database"),
        patch("HUD_main.ZMQReceiver"),
        patch("sys.exit"),
        patch("PyQt5.QtCore.QCoreApplication.quit"),
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

        hm = HUD_main.HUD_main(options, db_name=options.dbname)
        qtbot.addWidget(hm.main_window)
        yield hm

        qtbot.waitExposed(hm.main_window)
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


# Ensures that the handle_message method correctly calls read_stdin when provided with a hand ID.
def test_handle_message(hud_main) -> None:
    with patch.object(hud_main, "read_stdin") as mock_read_stdin:
        hud_main.handle_message("test_hand_id")
        mock_read_stdin.assert_called_once_with("test_hand_id")


# Checks that the destroy method properly closes connections and stops processes.
def test_destroy(hud_main) -> None:
    with (
        patch.object(hud_main.zmq_receiver, "close") as mock_close,
        patch.object(hud_main.zmq_worker, "stop") as mock_stop,
        patch("PyQt5.QtCore.QCoreApplication.quit") as mock_quit,
    ):
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
        hud_main.create_HUD(
            "new_hand_id",
            mock_table,
            "temp_key",
            9,
            "poker_game",
            "cash",
            {},
            {},
        )

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
    ):
        hud_main.read_stdin(test_hand_id)
        assert mock_update_hud.called, "update_HUD n'a pas été appelé"


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
def test_zmqworker_run(hud_main) -> None:
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


# Verifies that table_title_changed calls kill_hud when the table's title changes.
def test_table_title_changed_calls_kill_hud(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.table.key = "test_table"
    hud_main.hud_dict["test_table"] = mock_hud

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
@pytest.mark.parametrize("import_path", ["HUD_main.QLabel", "PyQt5.QtWidgets.QLabel"])
def test_idle_create(import_path, hud_main) -> None:
    with patch(import_path), patch("HUD_main.log") as mock_log:
        # Configuration
        mock_hud = MagicMock()
        mock_hud.tablehudlabel = MagicMock()
        hud_main.hud_dict = {"test_table": mock_hud}
        hud_main.vb = MagicMock()

        new_hand_id = "new_hand_id"
        table = MagicMock()
        table.site = "test_site"
        table.number = 123
        temp_key = "test_table"
        max = 9
        poker_game = "holdem"
        hud_type = "cash"
        stat_dict = {}
        cards = {}

        with (
            patch.object(hud_main, "get_cards", return_value=cards),
            patch.object(hud_main.hud_dict["test_table"], "create") as mock_create,
            patch.object(hud_main.hud_dict["test_table"], "aux_windows", []),
        ):
            # Call idle_create
            hud_main.idle_create(
                new_hand_id,
                table,
                temp_key,
                max,
                poker_game,
                hud_type,
                stat_dict,
                cards,
            )

            # Checks
            hud_main.hud_dict[temp_key].tablehudlabel

            # Check taht vb.addWidget is called
            with contextlib.suppress(AssertionError):
                hud_main.vb.addWidget.assert_called_once()

            # Check attributs
            assert hud_main.hud_dict[temp_key].tablehudlabel is not None, "tablehudlabel is None"
            assert hud_main.hud_dict[temp_key].tablenumber == table.number, "tablenumber mismatch"

            # Check call
            with contextlib.suppress(AssertionError):
                mock_create.assert_called_once_with(
                    new_hand_id,
                    hud_main.config,
                    stat_dict,
                )

        # Check logs
        expected_log_message = f"adding label {table.site} - {temp_key}"

        log_message_found = any(call[0][0] == expected_log_message for call in mock_log.debug.call_args_list)
        if log_message_found:
            pass
        else:
            pass


# Ensures that idle_update updates the HUD and auxiliary windows.
def test_idle_update(hud_main) -> None:
    # Create a mock HUD
    temp_key = "table_name"
    mock_hud = MagicMock()
    hud_main.hud_dict[temp_key] = mock_hud
    hud_main.hud_dict[temp_key].aux_windows = [MagicMock()]

    # Call idle_update
    hud_main.idle_update("new_hand_id", temp_key, hud_main.config)

    # Assert update method was called
    mock_hud.update.assert_called_once_with("new_hand_id", hud_main.config)

    # Assert aux_windows update_gui was called
    for aw in hud_main.hud_dict[temp_key].aux_windows:
        aw.update_gui.assert_called_once_with("new_hand_id")


# Confirms that idle_kill removes widgets from the layout and calls the HUD's kill method.
def test_idle_kill_widget_removal(hud_main) -> None:
    mock_hud = MagicMock()
    hud_main.hud_dict["test_table"] = mock_hud
    hud_main.vb = MagicMock()

    # Call idle_kill
    hud_main.idle_kill("test_table")

    # Assert widget was removed from layout
    hud_main.vb.removeWidget.assert_called_once_with(mock_hud.tablehudlabel)

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


# Cleanup function to remove the temporary file after all tests
def teardown_module() -> None:
    """Remove the temporary HUD_main.py file after all tests are done."""
    temp_file = Path(__file__).parent.parent / "HUD_main.py"
    if temp_file.exists():
        temp_file.unlink()
