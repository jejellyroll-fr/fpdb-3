import contextlib
import importlib.machinery
import importlib.util
import os
import sys
import threading
import time
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

pytestmark = pytest.mark.qt
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from fpdb.infrastructure.platform import permissions as macos_permissions

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
        patch("HUD_main.Database.Database") as mock_database,
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
        # The focused HudMain tests exercise the legacy synchronous seam with a
        # controllable Database mock. Runtime construction uses HudReadWorker,
        # whose connection intentionally lives on its own thread.
        hm._db_worker.stop()
        app.processEvents()
        hm._db_worker = None
        hm.db_connection = mock_database.return_value
        hm._db_available = True
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


def _winamax_source_owner(enabled_sites: list[str]) -> SimpleNamespace:
    config = MagicMock()
    config.get_supported_sites.return_value = enabled_sites
    return SimpleNamespace(
        config=config,
        winamax_table_update=MagicMock(),
        _on_winamax_table_update=MagicMock(),
        _site_enabled_in_config=HUD_main.HudMain._site_enabled_in_config,
    )


def test_winamax_live_sources_are_not_constructed_when_site_is_disabled() -> None:
    owner = _winamax_source_owner(["PokerStars"])
    with (
        patch("fpdb_3_legacy.winamax_ax_seats.is_supported") as is_supported,
        patch("fpdb_3_legacy.winamax_ax_seats.WinamaxAXSeatReader") as ax_reader,
        patch("fpdb_3_legacy.winamax_pool_games.WinamaxPoolGames") as pool_games,
        patch("fpdb_3_legacy.winamax_live_log_reader.WinamaxLiveLogReader") as log_reader,
    ):
        HUD_main.HudMain._initialize_winamax_live_sources(owner)

    assert owner.winamax_ax_seats is None
    assert owner.winamax_pool_games is None
    assert owner.winamax_log_reader is None
    is_supported.assert_not_called()
    ax_reader.assert_not_called()
    pool_games.assert_not_called()
    log_reader.assert_not_called()
    owner.winamax_table_update.connect.assert_not_called()


def test_winamax_live_sources_start_when_site_is_enabled() -> None:
    owner = _winamax_source_owner(["PokerStars", "Winamax"])
    ax_instance = MagicMock()
    pool_instance = MagicMock()
    log_instance = MagicMock()
    with (
        patch("fpdb_3_legacy.winamax_ax_seats.is_supported", return_value=True),
        patch("fpdb_3_legacy.winamax_ax_seats.WinamaxAXSeatReader", return_value=ax_instance) as ax_reader,
        patch("fpdb_3_legacy.winamax_pool_games.WinamaxPoolGames", return_value=pool_instance) as pool_games,
        patch(
            "fpdb_3_legacy.winamax_live_log_reader.WinamaxLiveLogReader",
            return_value=log_instance,
        ) as log_reader,
    ):
        HUD_main.HudMain._initialize_winamax_live_sources(owner)

    assert owner.winamax_ax_seats is ax_instance
    assert owner.winamax_pool_games is pool_instance
    assert owner.winamax_log_reader is log_instance
    ax_reader.assert_called_once_with()
    pool_games.assert_called_once()
    log_reader.assert_called_once_with(on_table_update=owner.winamax_table_update.emit)
    log_instance.start.assert_called_once_with()
    owner.winamax_table_update.connect.assert_called_once_with(owner._on_winamax_table_update)


@pytest.mark.parametrize(
    "status",
    [
        macos_permissions.PermissionStatus(screen_recording=False, accessibility=False),
        macos_permissions.PermissionStatus(screen_recording=True, accessibility=False),
        macos_permissions.PermissionStatus(screen_recording=True, accessibility=True),
    ],
)
def test_hud_main_startup_permission_preflight_is_diagnostic_only(
    status: macos_permissions.PermissionStatus,
) -> None:
    """Frozen startup and the legacy opt-in never prompt or open Settings."""
    owner = SimpleNamespace()

    with (
        patch.dict(os.environ, {"FPDB_REQUEST_MACOS_PERMISSIONS": "1"}, clear=True),
        patch.object(HUD_main.sys, "frozen", True, create=True),
        patch.object(macos_permissions, "get_status", return_value=status),
        patch.object(macos_permissions, "describe_missing", return_value=[]),
        patch.object(macos_permissions, "request_screen_recording_permission") as request_screen,
        patch.object(macos_permissions, "open_screen_recording_settings") as open_screen,
        patch.object(macos_permissions, "request_accessibility_permission") as request_accessibility,
        patch.object(macos_permissions, "open_accessibility_settings") as open_accessibility,
    ):
        HUD_main.HudMain._check_macos_permissions(owner)

    assert owner._macos_permission_status is status
    request_screen.assert_not_called()
    open_screen.assert_not_called()
    request_accessibility.assert_not_called()
    open_accessibility.assert_not_called()


def test_macos_permission_dialog_refresh_is_diagnostic_only(app) -> None:
    status = macos_permissions.PermissionStatus(False, True, app_data=None)
    with (
        patch.object(macos_permissions, "get_status", return_value=status),
        patch.object(macos_permissions, "request_screen_recording_permission") as request_screen,
        patch.object(macos_permissions, "request_accessibility_permission") as request_accessibility,
        patch.object(macos_permissions, "open_screen_recording_settings") as open_screen,
        patch.object(macos_permissions, "open_accessibility_settings") as open_accessibility,
    ):
        dialog = HUD_main.MacOSPermissionsDialog()
        dialog.refresh_status()

        assert dialog.screen_status_label.text() == "Missing"
        assert dialog.accessibility_status_label.text() == "Granted"
        assert dialog.app_data_status_label.text() == "Not preflightable"
        assert "NSAppDataUsageDescription" in dialog.app_data_info_label.text()
        assert not hasattr(dialog, "app_data_settings_button")
        assert not hasattr(dialog, "_open_app_data_settings")
        request_screen.assert_not_called()
        request_accessibility.assert_not_called()
        open_screen.assert_not_called()
        open_accessibility.assert_not_called()
        dialog.close()


def test_macos_permission_dialog_request_buttons_are_isolated(app) -> None:
    status = macos_permissions.PermissionStatus(False, False)
    with (
        patch.object(macos_permissions, "get_status", return_value=status),
        patch.object(macos_permissions, "request_screen_recording_permission") as request_screen,
        patch.object(macos_permissions, "request_accessibility_permission") as request_accessibility,
        patch.object(macos_permissions, "open_screen_recording_settings") as open_screen,
        patch.object(macos_permissions, "open_accessibility_settings") as open_accessibility,
    ):
        dialog = HUD_main.MacOSPermissionsDialog()
        dialog.set_status(status)

        dialog.screen_request_button.click()
        request_screen.assert_called_once_with()
        request_accessibility.assert_not_called()
        open_screen.assert_not_called()
        open_accessibility.assert_not_called()

        request_screen.reset_mock()
        dialog.accessibility_request_button.click()
        request_accessibility.assert_called_once_with(prompt=True)
        request_screen.assert_not_called()
        open_screen.assert_not_called()
        open_accessibility.assert_not_called()
        dialog.close()


def test_macos_permission_dialog_settings_buttons_open_only_their_pane(app) -> None:
    status = macos_permissions.PermissionStatus(False, False)
    with (
        patch.object(macos_permissions, "open_screen_recording_settings") as open_screen,
        patch.object(macos_permissions, "open_accessibility_settings") as open_accessibility,
    ):
        dialog = HUD_main.MacOSPermissionsDialog()
        dialog.set_status(status)

        dialog.screen_settings_button.click()
        open_screen.assert_called_once_with()
        open_accessibility.assert_not_called()

        open_screen.reset_mock()
        dialog.accessibility_settings_button.click()
        open_accessibility.assert_called_once_with()
        open_screen.assert_not_called()
        assert not hasattr(dialog, "app_data_settings_button")
        dialog.close()


def test_macos_permission_dialog_rechecks_without_prompt_on_app_activation() -> None:
    dialog = MagicMock()
    dialog.isVisible.return_value = True
    owner = SimpleNamespace(_macos_permissions_dialog=dialog)

    HUD_main.HudMain._on_application_state_changed(owner, Qt.ApplicationState.ApplicationInactive)
    dialog.refresh_status.assert_not_called()

    HUD_main.HudMain._on_application_state_changed(owner, Qt.ApplicationState.ApplicationActive)
    dialog.refresh_status.assert_called_once_with()


def test_macos_permission_action_exists_before_any_table_without_auto_show(tmp_path) -> None:
    """The HUD main window exposes onboarding without needing a detected table."""
    owner = SimpleNamespace(
        options=SimpleNamespace(xloc=None, yloc=None),
        config=SimpleNamespace(os_family="Mac", graphics_path=str(tmp_path)),
        close_event_handler=MagicMock(),
        destroy=MagicMock(),
        check_tables=MagicMock(),
        show_macos_permissions=MagicMock(),
        _on_application_state_changed=MagicMock(),
    )
    main_window = MagicMock()
    layout = MagicMock()
    permissions_button = MagicMock()
    timer = MagicMock()
    app_instance = MagicMock()

    with (
        patch.object(HUD_main, "HudMainWindow", return_value=main_window),
        patch.object(HUD_main, "QVBoxLayout", return_value=layout),
        patch.object(HUD_main, "QLabel"),
        patch.object(HUD_main, "QPushButton", return_value=permissions_button),
        patch.object(HUD_main, "QTimer", return_value=timer),
        patch.object(HUD_main.QApplication, "instance", return_value=app_instance),
        patch.object(HUD_main, "MacOSPermissionsDialog") as permissions_dialog,
    ):
        HUD_main.HudMain.init_main_window(owner)

    assert owner._macos_permissions_dialog is None
    permissions_dialog.assert_not_called()
    permissions_button.clicked.connect.assert_called_once_with(owner.show_macos_permissions)
    layout.addWidget.assert_any_call(permissions_button)
    main_window.show.assert_called_once_with()


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


def test_async_drain_only_submits_work_to_the_database_thread(hud_main) -> None:
    worker = MagicMock()
    hud_main._db_worker = worker
    hud_main._pending_hands = ["101", "102"]

    with patch.object(hud_main, "_build_batch_request") as build_request:
        request = HUD_main.HudBatchReadRequest(1, ("101", "102"), {})
        build_request.return_value = request
        hud_main._drain_pending_hands()

    worker.submit.assert_called_once_with(request)
    assert hud_main._pending_hands == []
    assert hud_main._db_batch_inflight is True
    assert not hud_main.db_connection.get_table_info.called


def test_slow_database_worker_does_not_block_the_qt_event_loop(qtbot) -> None:
    main_thread = threading.get_ident()
    factory_threads: list[int] = []
    database = MagicMock(backend=0)

    def database_factory(_config):
        factory_threads.append(threading.get_ident())
        return database

    class SlowService:
        def __init__(self, _config, _database) -> None:
            pass

        def read_batch(self, request, progress_callback=None):
            time.sleep(0.35)
            return HUD_main.HudBatchSnapshot(
                request.sequence,
                request.hand_ids,
                (),
                {},
                {},
                {},
                {},
                {},
            )

    worker = HUD_main.HudReadWorker(MagicMock(), db_factory=database_factory)
    ticks: list[float] = []
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(time.monotonic()))

    try:
        with patch("HUD_main.HudReadService", SlowService):
            with qtbot.waitSignal(worker.ready, timeout=1000):
                worker.start()
            heartbeat.start()
            started = time.monotonic()
            with qtbot.waitSignal(worker.snapshot_ready, timeout=1500):
                worker.submit(HUD_main.HudBatchReadRequest(1, ("101",), {}))
            elapsed = time.monotonic() - started
    finally:
        heartbeat.stop()
        worker.stop()

    assert factory_threads and factory_threads[0] != main_thread
    assert elapsed >= 0.3
    assert len(ticks) >= 15
    assert max(b - a for a, b in zip(ticks, ticks[1:], strict=False)) < 0.15


def test_postgresql_worker_bounds_its_own_session_queries() -> None:
    database = MagicMock(backend=HUD_main.Database.Database.PGSQL)
    cursor = database.connection.cursor.return_value

    HUD_main.HudReadWorker._configure_session(database)

    assert cursor.execute.call_args_list == [
        call("SET statement_timeout = 10000"),
        call("SET lock_timeout = 2000"),
        call("SET idle_in_transaction_session_timeout = 30000"),
    ]
    database.connection.commit.assert_called_once_with()
    cursor.close.assert_called_once_with()


def test_partial_snapshot_keeps_batch_inflight_until_final_snapshot(hud_main) -> None:
    hud_main._db_worker = MagicMock()
    hud_main._db_batch_inflight = True
    partial = HUD_main.HudBatchSnapshot(
        5,
        ("101",),
        ("101",),
        {},
        {},
        {},
        {},
        {},
        revision=1,
        final=False,
    )
    final = HUD_main.HudBatchSnapshot(
        5,
        ("101",),
        (),
        {},
        {},
        {},
        {},
        {},
        revision=2,
    )

    with (
        patch.object(hud_main, "read_stdin", return_value="table-a"),
        patch.object(hud_main, "_refresh_other_huds") as refresh_other,
    ):
        hud_main._on_db_snapshot(partial)
        assert hud_main._db_batch_inflight is True
        refresh_other.assert_not_called()

        hud_main._on_db_snapshot(final)

    assert hud_main._db_batch_inflight is False
    refresh_other.assert_called_once()


def test_identity_snapshot_requests_a_loading_hud_before_stats_arrive(hud_main) -> None:
    prepared = MagicMock()
    prepared.hand_id = "101"
    prepared.table_info = ("table-a", 6, "holdem", "ring", False, 1, "site", 6, None, None, None)
    prepared.positions = {}
    prepared.seat_players = {}
    snapshot = HUD_main.HudBatchSnapshot(
        6,
        ("101",),
        ("101",),
        {"101": prepared},
        {},
        {},
        {},
        {},
        revision=1,
        final=False,
        identity_only=True,
    )
    hud_main._db_worker = MagicMock()
    hud_main._db_batch_inflight = True

    with patch.object(hud_main, "_show_loading_hud") as show_loading:
        hud_main._on_db_snapshot(snapshot)

    show_loading.assert_called_once_with("101")
    assert hud_main._db_batch_inflight is True


def test_loading_hud_creation_does_not_require_statistics(hud_main) -> None:
    # Extended table identity includes limitType after the 11 legacy fields.
    table_info = ("table-a", 6, "holdem", "ring", False, 1, "site", 6, None, None, None, "nl")
    hud_main._prepared_hands = {"101": MagicMock(table_info=table_info)}
    hud_main.config.get_supported_sites.return_value = ["site"]
    hud_main.config.get_site_parameters.return_value = {"aux_enabled": True}

    with patch.object(hud_main, "_create_new_hud") as create_new_hud:
        hud_main._show_loading_hud("101")

    create_new_hud.assert_called_once_with(
        "101",
        "table-a",
        table_info,
        1,
        6,
        "site",
        loading=True,
    )


def test_loading_hud_builds_empty_creation_args_without_querying_stats(hud_main) -> None:
    table_info = ("table-a", 6, "holdem", "ring", False, 1, "site", 6, None, None, None)
    prepared = MagicMock(cards={}, hand_instance=None)
    hud_main._prepared_hands = {"101": prepared}
    hud_main.config.get_supported_games_parameters.return_value = {"aux": ""}
    hud_main.Tables = MagicMock()
    hud_main.Tables.Table.return_value = MagicMock(
        number=12,
        title="table-a",
        x=0,
        y=0,
        width=800,
        height=600,
    )
    resolved_window = SimpleNamespace(window_id=12, title="Winamax table-a")

    with (
        patch.object(hud_main.db_connection, "get_stats_from_hand") as get_stats,
        patch.object(hud_main, "create_HUD") as create_hud,
        patch.object(hud_main, "_seat_players") as seat_players,
        patch.object(hud_main, "_set_table_stats") as set_table_stats,
    ):
        create_hud.side_effect = lambda args: hud_main.hud_dict.__setitem__(args.temp_key, MagicMock())
        hud_main._create_new_hud(
            "101",
            "table-a",
            table_info,
            1,
            6,
            "site",
            loading=True,
            resolved_window=resolved_window,
        )

    get_stats.assert_not_called()
    args = create_hud.call_args.args[0]
    assert args.stat_dict == {}
    assert args.cards == {}
    assert args.loading is True
    hud_main.Tables.Table.assert_called_once_with(
        hud_main.config,
        "site",
        table_name="table-a",
        tournament=None,
        table_number=None,
        tourney_name=None,
        resolved_window=resolved_window,
    )
    seat_players.assert_not_called()
    set_table_stats.assert_not_called()


def test_complete_snapshot_recreates_loading_hud_with_player_seat_mapping(hud_main) -> None:
    """An identity-only HUD cannot be upgraded in place after seats arrive."""
    hand_id = "101"
    table_info = ("table-a", 6, "holdem", "ring", False, 1, "site", 6, None, None, None, "nl")
    hud_main.cache[hand_id] = table_info
    hud_main.hud_dict["table-a"] = MagicMock(is_loading=True)
    hud_main.config.get_supported_sites.return_value = ["site"]
    hud_main.config.get_site_parameters.return_value = {"aux_enabled": True}

    def kill_loading_hud(_event, temp_key):
        del hud_main.hud_dict[temp_key]

    def create_complete_hud(_hand_id, temp_key, *_args, **_kwargs):
        hud_main.hud_dict[temp_key] = MagicMock(is_loading=False)

    with (
        patch.object(hud_main, "_initialize_hero_data"),
        patch.object(hud_main, "_handle_tournament_table_changes", return_value=False),
        patch.object(hud_main, "_handle_hud_reconfiguration", return_value=("holdem", None)),
        patch.object(hud_main, "kill_hud", side_effect=kill_loading_hud) as kill_hud,
        patch.object(hud_main, "_create_new_hud", side_effect=create_complete_hud) as create_hud,
        patch.object(hud_main, "_update_existing_hud") as update_hud,
    ):
        assert hud_main.read_stdin(hand_id) == "table-a"

    kill_hud.assert_called_once_with(None, "table-a")
    create_hud.assert_called_once_with(hand_id, "table-a", table_info, 1, 6, "site")
    update_hud.assert_not_called()
    assert hud_main._last_processed_hands["table-a"] == hand_id


def test_runtime_replay_error_cannot_start_the_legacy_recovery_worker(hud_main) -> None:
    hud_main._db_worker = MagicMock()

    with patch.object(hud_main, "_start_db_recovery") as start_recovery:
        assert hud_main.note_db_error(RuntimeError("connection reset by peer")) is False

    start_recovery.assert_not_called()


def test_pending_hand_queue_keeps_only_its_bounded_latest_tail(hud_main) -> None:
    saved = HUD_main.MAX_PENDING_HANDS
    HUD_main.MAX_PENDING_HANDS = 3
    try:
        for hand_id in ("1", "2", "3", "4"):
            hud_main._enqueue_hand(hand_id)
    finally:
        HUD_main.MAX_PENDING_HANDS = saved

    assert hud_main._pending_hands == ["2", "3", "4"]


def test_repeated_batch_timeouts_are_counted_and_reported(hud_main) -> None:
    request = HUD_main.HudBatchReadRequest(7, ("101",), {})

    with (
        patch("HUD_main.QTimer.singleShot"),
        patch("HUD_main.log.warning") as warning,
    ):
        hud_main._on_db_batch_failed(request, "statement timeout")
        hud_main._on_db_batch_failed(request, "statement timeout")

    assert hud_main._db_consecutive_failures == 2
    assert warning.call_args_list[-1].args[2] == 2


def test_batch_retry_backs_off_once_after_five_consecutive_failures(hud_main) -> None:
    request = HUD_main.HudBatchReadRequest(8, ("101",), {})

    with (
        patch("HUD_main.QTimer.singleShot") as single_shot,
        patch("HUD_main.log.error") as error,
    ):
        for _ in range(7):
            hud_main._on_db_batch_failed(request, "statement timeout")

    assert [item.args[0] for item in single_shot.call_args_list] == [5000] * 5 + [30000] * 2
    error.assert_called_once()


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

    assert not hud_main._cleanup_timer.isActive()
    assert not hud_main.check_tables_timer.isActive()


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


def test_check_tables_skipped_during_drag(hud_main, monkeypatch) -> None:
    """While a HUD window is dragged, check_tables must not poll geometry or
    re-raise windows (that stutters the drag on macOS).

    A held mouse button is part of what makes a drag real now: the flag alone is
    no longer believed, because the release that clears it is not guaranteed to
    arrive and a stuck flag used to stop every HUD from ever being taken down.
    See test_hud_drag_flag.py for that half.
    """
    from fpdb_3_legacy import Aux_Base

    mock_hud = MagicMock()
    mock_hud.table.check_table.return_value = "client_moved"
    hud_main.hud_dict = {"test_table": mock_hud}

    monkeypatch.setattr(Aux_Base, "_a_mouse_button_is_down", lambda: True)
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


def test_check_tables_ignores_preview_hud_without_live_table(hud_main) -> None:
    """Preview/lightweight HUDs must not crash the periodic table poll."""
    hud_main.hud_dict = {"preview": SimpleNamespace()}

    hud_main.check_tables()


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


def test_batched_stats_failure_rolls_back_before_per_table_fallback(hud_main) -> None:
    """PostgreSQL must leave the connection usable for the promised fallback."""
    hud = MagicMock()
    hud.hud_params = {"hud_days": 30, "h_hud_days": 90}
    hud.poker_game = "holdem"
    hud_main.hud_dict = {"table": hud}
    hud_main.hero_ids = {1: 42}
    hud_main.db_connection.get_stats_from_hands.side_effect = RuntimeError("bad batched query")
    hud_main.db_connection.connection.rollback.reset_mock()
    pending = [("table", "hand", "ring", 1, 6)]

    with patch.object(hud_main, "note_db_error", return_value=False):
        result = hud_main._batch_secondary_stats(pending)

    assert result == {}
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
    mock_hud.loading_window = None
    hud_main.idle_move(mock_hud)

    mock_hud.move_table_position.assert_called_once()
    for aw in mock_hud.aux_windows:
        aw.move_windows.assert_called_once()


# Verifies that idle_resize resizes the table and auxiliary windows.
def test_idle_resize(hud_main) -> None:
    mock_hud = MagicMock()
    mock_hud.aux_windows = [MagicMock()]
    mock_hud.loading_window = None
    hud_main.idle_resize(mock_hud)

    mock_hud.resize_windows.assert_called_once()
    for aw in mock_hud.aux_windows:
        aw.resize_windows.assert_called_once()


@pytest.mark.parametrize("geometry_callback", ["idle_move", "idle_resize"])
def test_table_geometry_change_recenters_loading_indicator(hud_main, geometry_callback) -> None:
    mock_hud = MagicMock(loading_window=MagicMock())
    mock_hud.aux_windows = []

    with patch.object(hud_main, "_position_loading_indicator") as position_indicator:
        getattr(hud_main, geometry_callback)(mock_hud)

    position_indicator.assert_called_once_with(mock_hud)


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


def test_idle_create_builds_and_updates_each_auxiliary_once(hud_main) -> None:
    mock_hud = MagicMock()
    first_aux = MagicMock()
    second_aux = MagicMock()
    mock_hud.aux_windows = [first_aux, second_aux]
    hud_main.hud_dict = {"test_table": mock_hud}
    hud_main.vb = MagicMock()
    table = MagicMock(site="test_site", number=123)
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

    hud_main.idle_create(args)

    first_aux.create.assert_called_once_with()
    first_aux.update_gui.assert_called_once_with(args.new_hand_id)
    second_aux.create.assert_called_once_with()
    second_aux.update_gui.assert_called_once_with(args.new_hand_id)


def test_idle_create_loading_uses_one_indicator_without_building_auxiliaries(hud_main) -> None:
    mock_hud = MagicMock()
    auxiliary = MagicMock()
    mock_hud.aux_windows = [auxiliary]
    hud_main.hud_dict = {"test_table": mock_hud}
    hud_main.vb = MagicMock()
    table = MagicMock(site="test_site", number=123)
    args = HUD_main.HUDCreationArgs(
        new_hand_id="new_hand_id",
        table=table,
        temp_key="test_table",
        max_seats=9,
        poker_game="holdem",
        game_type="cash",
        stat_dict={},
        cards={},
        loading=True,
    )

    with patch.object(hud_main, "_create_loading_indicator") as create_indicator:
        hud_main.idle_create(args)

    create_indicator.assert_called_once_with(mock_hud)
    auxiliary.create.assert_not_called()
    auxiliary.update_gui.assert_not_called()


def test_loading_indicator_is_topified_over_the_table(hud_main) -> None:
    table = MagicMock(x=100, y=50, width=800, height=600)
    mock_hud = MagicMock(table=table, table_name="test_table", loading_window=None)

    hud_main._create_loading_indicator(mock_hud)

    indicator = mock_hud.loading_window
    assert indicator is not None
    assert indicator.objectName() == "hud-loading-indicator"
    assert indicator.isVisible()
    table.topify.assert_called_once_with(indicator)
    indicator.hide()
    indicator.close()
    indicator.deleteLater()


def test_loading_indicator_position_uses_current_table_geometry(hud_main) -> None:
    indicator = MagicMock()
    indicator.width.return_value = 120
    indicator.height.return_value = 30
    table = MagicMock(x=200, y=100, width=800, height=600)
    mock_hud = MagicMock(table=table, loading_window=indicator)

    with patch.object(HUD_main.Aux_Base, "clamp_to_screen", side_effect=lambda x, y: (x, y)):
        hud_main._position_loading_indicator(mock_hud)

    indicator.move.assert_called_once_with(540, 385)


def test_idle_create_continues_after_one_auxiliary_fails(hud_main) -> None:
    mock_hud = MagicMock()
    failing_aux = MagicMock()
    failing_aux.create.side_effect = RuntimeError("broken auxiliary")
    healthy_aux = MagicMock()
    mock_hud.aux_windows = [failing_aux, healthy_aux]
    hud_main.hud_dict = {"test_table": mock_hud}
    hud_main.vb = MagicMock()
    table = MagicMock(site="test_site", number=123)
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

    hud_main.idle_create(args)

    failing_aux.create.assert_called_once_with()
    failing_aux.update_gui.assert_not_called()
    healthy_aux.create.assert_called_once_with()
    healthy_aux.update_gui.assert_called_once_with(args.new_hand_id)


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


def test_loading_hud_does_not_overwrite_persisted_stats_when_killed(hud_main) -> None:
    mock_hud = MagicMock(is_loading=True)
    hud_main.hud_dict["test_table"] = mock_hud
    hud_main.vb = MagicMock()

    with patch.object(hud_main.stats_persistence, "save_hud_stats") as save_stats:
        hud_main.idle_kill("test_table")

    save_stats.assert_not_called()


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
    # Once to clear the ordinary statement error before continuing, then once
    # to release the successful read transaction at the end of the batch.
    assert hud_main.db_connection.connection.rollback.call_count == 2
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


# --- Applying saved profile rules to tables that are already open ------------
# HUD Preferences runs in the fpdb process; this one is a subprocess, so a rule
# saved with Apply reaches the open tables only by way of the file.


def _named_stat_set(profile_name: str) -> MagicMock:
    # ``name`` is reserved by the MagicMock constructor, so it is set after.
    stat_set = MagicMock()
    stat_set.name = profile_name
    return stat_set


def _profile_hud(profile_name: str, *, game: str = "aof_omaha", table_key: str = "table-a") -> MagicMock:
    hud = MagicMock()
    hud.poker_game = game
    hud.game_type = "ring"
    hud.table.key = table_key
    hud.table_name = table_key
    hud.hud_context = HUD_main.HudContext(site="CoinPoker", game=game, game_type="ring", max_seats=6)
    hud.supported_games_parameters = {"game_stat_set": _named_stat_set(profile_name)}
    hud.aux_windows = []
    hud.stat_dict = {}
    return hud


def _config_file(hud_main, tmp_path, contents: str = "<config/>") -> Path:
    path = tmp_path / "HUD_config.xml"
    path.write_text(contents, encoding="utf-8")
    hud_main.config.file = str(path)
    hud_main._config_fingerprint = hud_main._read_config_fingerprint()
    return path


def _resolves_to(hud_main, profile_name: str) -> MagicMock:
    stat_set = _named_stat_set(profile_name)
    hud_main.config.get_supported_games_parameters.return_value = {"game_stat_set": stat_set}
    return stat_set


def test_an_unchanged_config_file_is_not_reloaded(hud_main, tmp_path) -> None:
    _config_file(hud_main, tmp_path)

    assert hud_main.refresh_profiles_from_config() == 0
    hud_main.config.reload.assert_not_called()


def test_a_saved_rule_rebuilds_only_the_tables_whose_profile_changed(hud_main, tmp_path) -> None:
    path = _config_file(hud_main, tmp_path)
    changed = _profile_hud("aof_default", table_key="table-a")
    unchanged = _profile_hud("plo4_6max_pro", game="omahahi", table_key="table-b")
    hud_main.hud_dict = {"table-a": changed, "table-b": unchanged}

    def resolve(poker_game, _game_type, _context=None):
        return {"game_stat_set": _named_stat_set("aof_advanced" if poker_game == "aof_omaha" else "plo4_6max_pro")}

    hud_main.config.get_supported_games_parameters.side_effect = resolve
    hud_main.config.reload.return_value = True
    path.write_text('<config changed="1"/>', encoding="utf-8")
    os.utime(path, (time.time() + 5, time.time() + 5))

    assert hud_main.refresh_profiles_from_config() == 1
    assert changed.supported_games_parameters["game_stat_set"].name == "aof_advanced"
    assert unchanged.supported_games_parameters["game_stat_set"].name == "plo4_6max_pro"


def test_a_table_local_profile_choice_survives_a_config_change(hud_main, tmp_path) -> None:
    """The table menu is the player's explicit, session-only decision."""
    path = _config_file(hud_main, tmp_path)
    hud = _profile_hud("aof_default")
    hud_main.hud_dict = {"table-a": hud}
    hud_main.config.stat_sets = {"aof_default": MagicMock()}
    hud_main.set_table_stat_set_override("table-a", "aof_omaha", "ring", "aof_default")
    _resolves_to(hud_main, "aof_advanced")
    hud_main.config.reload.return_value = True
    os.utime(path, (time.time() + 5, time.time() + 5))

    assert hud_main.refresh_profiles_from_config() == 0
    assert hud.supported_games_parameters["game_stat_set"].name == "aof_default"


def test_a_config_that_will_not_parse_leaves_the_profiles_in_use(hud_main, tmp_path) -> None:
    path = _config_file(hud_main, tmp_path)
    hud = _profile_hud("aof_default")
    hud_main.hud_dict = {"table-a": hud}
    hud_main.config.reload.return_value = False
    _resolves_to(hud_main, "aof_advanced")
    os.utime(path, (time.time() + 5, time.time() + 5))

    assert hud_main.refresh_profiles_from_config() == 0
    assert hud.supported_games_parameters["game_stat_set"].name == "aof_default"


def test_the_change_is_detected_only_once(hud_main, tmp_path) -> None:
    path = _config_file(hud_main, tmp_path)
    hud_main.config.reload.return_value = True
    os.utime(path, (time.time() + 5, time.time() + 5))

    hud_main.refresh_profiles_from_config()
    hud_main.refresh_profiles_from_config()

    assert hud_main.config.reload.call_count == 1


def test_a_rebuild_recomputes_the_scope_so_positions_follow_the_profile() -> None:
    """Saved positions are filed under the profile, so the scope must move."""
    hud = _profile_hud("aof_default")
    hud.site = "CoinPoker"
    hud.max = 6
    hud.layout_set = SimpleNamespace(name="default")
    hud.aux_windows = []
    HUD_main.HudMain._rebuild_hud_with_stat_set(hud, _named_stat_set("aof_advanced"))

    assert hud.position_scope.profile == "aof_advanced"
    assert hud.position_scope.game == "aof_omaha"


def test_a_failed_rebuild_restarts_the_table_instead_of_orphaning_windows(hud_main, tmp_path) -> None:
    path = _config_file(hud_main, tmp_path)
    hud = _profile_hud("aof_default")
    hud_main.hud_dict = {"table-a": hud}
    hud_main.config.reload.return_value = True
    _resolves_to(hud_main, "aof_advanced")
    os.utime(path, (time.time() + 5, time.time() + 5))

    with (
        patch.object(HUD_main.HudMain, "_rebuild_hud_with_stat_set", side_effect=RuntimeError("boom")),
        patch.object(hud_main, "kill_hud") as kill_hud,
    ):
        assert hud_main.refresh_profiles_from_config() == 1

    kill_hud.assert_called_once_with(None, "table-a")


def test_update_hud_forwards_config_and_cards_to_idle_update(hud_main) -> None:
    """Dropping any of these raises TypeError on every hand, on every site."""
    cards = {"player": ["As", "Kd"]}
    hand_instance = object()

    with patch.object(hud_main, "idle_update") as idle_update:
        hud_main.update_HUD("hand-1", "table-a", hud_main.config, cards=cards, hand_instance=hand_instance)

    idle_update.assert_called_once_with(
        "hand-1",
        "table-a",
        hud_main.config,
        cards=cards,
        hand_instance=hand_instance,
    )


def test_hud_is_fast_fold_trusts_the_flag_set_from_the_winamax_log(hud_main) -> None:
    # An Escape window is titled "Winamax Casablanca 3": nothing in the name says
    # Fast-Fold, so only the log-derived flag can identify it.
    hud = SimpleNamespace(table_name="Casablanca", game_type="ring", is_fast_fold=False)
    assert hud_main._hud_is_fast_fold(hud, "Casablanca") is False

    hud.is_fast_fold = True
    assert hud_main._hud_is_fast_fold(hud, "Casablanca") is True


def _log_update(pool="gf.cgmatchmaker.gf_1.t22754010.0", table_no="1"):
    return SimpleNamespace(pool=pool, table_no=table_no, hand_id="22754010-6356-1786128858", table_id="22754010")


def test_find_fast_fold_hud_ignores_non_go_fast_pools(hud_main) -> None:
    hud_main.hud_dict = {"t": SimpleNamespace(site="Winamax", table=SimpleNamespace(title="Winamax Casablanca 1"))}
    try:
        assert hud_main._find_fast_fold_hud(_log_update(pool="cash.table.1")) is None
    finally:
        hud_main.hud_dict = {}


def test_find_fast_fold_hud_matches_single_table_and_marks_it(hud_main) -> None:
    # Title index 1 matches the default update's [table] 1.
    hud = SimpleNamespace(site="Winamax", table=SimpleNamespace(title="Winamax Casablanca 1"))
    hud_main.hud_dict = {"casablanca": hud}
    try:
        assert hud_main._find_fast_fold_hud(_log_update()) == ("casablanca", hud)
        assert hud.is_fast_fold is True
    finally:
        hud_main.hud_dict = {}


def test_find_fast_fold_hud_pairs_multiple_tables_by_title_index(hud_main) -> None:
    """The trailing number in the window title is the client's [table] N index."""
    hud1 = SimpleNamespace(site="Winamax", table=SimpleNamespace(title="Winamax Casablanca 1"))
    hud2 = SimpleNamespace(site="Winamax", table=SimpleNamespace(title="Winamax Casablanca 2"))
    hud_main.hud_dict = {"a": hud1, "b": hud2}
    try:
        assert hud_main._find_fast_fold_hud(_log_update(table_no="2")) == ("b", hud2)
        assert hud_main._find_fast_fold_hud(_log_update(table_no="1")) == ("a", hud1)
    finally:
        hud_main.hud_dict = {}


def test_fast_fold_hud_is_created_when_a_live_seat_source_exists(hud_main) -> None:
    """Escape tables used to be skipped outright; the log reader now feeds them."""
    hud_main.winamax_log_reader = SimpleNamespace(is_tailing=True)
    assert hud_main._has_live_seat_source("Winamax") is True

    # No tailing log (client absent, or logs elsewhere) => no live data to show.
    hud_main.winamax_log_reader = SimpleNamespace(is_tailing=False)
    assert hud_main._has_live_seat_source("Winamax") is False

    # Other sites have no such source at all, so their Fast-Fold tables stay skipped.
    hud_main.winamax_log_reader = SimpleNamespace(is_tailing=True)
    assert hud_main._has_live_seat_source("PokerStars") is False


def test_hud_is_fast_fold_remembers_tables_flagged_at_import(hud_main) -> None:
    hud = SimpleNamespace(table_name="Casablanca", game_type="ring", is_fast_fold=False)
    assert hud_main._hud_is_fast_fold(hud, "Casablanca") is False

    hud_main._fast_fold_tables.add("Casablanca")
    assert hud_main._hud_is_fast_fold(hud, "Casablanca") is True


def test_a_second_pool_sharing_one_hud_is_left_alone(hud_main) -> None:
    """Two Escape windows on a pool import under one table name and one HUD."""
    hud = SimpleNamespace(site="Winamax", table=SimpleNamespace(title="Winamax Casablanca 1"))
    hud_main.hud_dict = {"casablanca": hud}
    try:
        first = hud_main._find_fast_fold_hud(_log_update(pool="gf.p.t1.0", table_no="1"))
        assert first == ("casablanca", hud)

        # A different pool would otherwise overwrite the same HUD's seats.
        assert hud_main._find_fast_fold_hud(_log_update(pool="gf.p.t1.1", table_no="2")) is None
        # The pool that got there first keeps driving it.
        assert hud_main._find_fast_fold_hud(_log_update(pool="gf.p.t1.0", table_no="1")) == ("casablanca", hud)
    finally:
        hud_main.hud_dict = {}


def _fast_info(hud_main, table_name="Casablanca"):
    from fpdb_3_legacy.table_info import TableInfo

    return TableInfo(table_name=table_name, fast=True, site_name="Winamax", game_type="ring")


def _prepared_with_site_id(site_hand_no):
    """A snapshot entry carrying the hand's site id, as the worker prepares it."""
    return SimpleNamespace(hand_instance=SimpleNamespace(handid=site_hand_no))


def test_fast_fold_table_name_is_qualified_by_its_window(hud_main) -> None:
    """Two Escape windows write hands under one pool name; the log separates them."""
    hud_main.winamax_log_reader = SimpleNamespace(
        is_tailing=True,
        table_no_for_hand=lambda site_hand_no: {"227540101": "5", "227540102": "6"}.get(site_hand_no),
    )
    hud_main._prepared_hands = {
        "101": _prepared_with_site_id("227540101"),
        "102": _prepared_with_site_id("227540102"),
    }

    assert hud_main._qualify_fast_fold_table(_fast_info(hud_main), 101).info.table_name == "Casablanca 5"
    assert hud_main._qualify_fast_fold_table(_fast_info(hud_main), 102).info.table_name == "Casablanca 6"


def test_unmappable_fast_fold_hand_is_skipped_not_keyed_on_the_pool_name(hud_main) -> None:
    """A bare pool name would claim whichever window matched first, mis-numbering it."""
    hud_main.winamax_log_reader = SimpleNamespace(is_tailing=True, table_no_for_hand=lambda _h: None)
    hud_main._prepared_hands = {"999": _prepared_with_site_id("227540109")}

    assert hud_main._qualify_fast_fold_table(_fast_info(hud_main), 999) is None


def test_unmappable_fast_fold_hand_is_skipped_without_a_hand_instance(hud_main) -> None:
    """Identity-only snapshots carry no Hand object to read the site id from."""
    hud_main.winamax_log_reader = SimpleNamespace(is_tailing=True, table_no_for_hand=lambda _h: "5")
    hud_main._prepared_hands = {}

    assert hud_main._qualify_fast_fold_table(_fast_info(hud_main), 1) is None


def test_non_fast_tables_are_never_qualified(hud_main) -> None:
    from fpdb_3_legacy.table_info import TableInfo

    info = TableInfo(table_name="Casablanca", fast=False, site_name="Winamax", game_type="ring")
    hud_main.winamax_log_reader = SimpleNamespace(is_tailing=True, table_no_for_hand=lambda _h: "5")

    assert hud_main._qualify_fast_fold_table(info, 1).info.table_name == "Casablanca"


def _ff_hud(title):
    return SimpleNamespace(site="Winamax", table=SimpleNamespace(title=title))


def test_a_pool_with_no_hud_of_its_own_does_not_borrow_another(hud_main) -> None:
    """Once titles carry an index, an unmatched pool has no HUD yet -- not this one."""
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.hud_dict = {"Casablanca 6": hud}
    # No window reader, so the unmatched pool cannot get a HUD of its own here;
    # this is about not handing it somebody else's.
    hud_main.winamax_ax_seats = None
    try:
        assert hud_main._find_fast_fold_hud(_log_update(table_no="6")) == ("Casablanca 6", hud)
        # Pool for window 5, whose HUD has not been created yet.
        assert hud_main._find_fast_fold_hud(_log_update(pool="gf.p.t1.4", table_no="5")) is None
    finally:
        hud_main.hud_dict = {}


def test_unindexed_title_still_falls_back_to_the_only_table(hud_main) -> None:
    hud = _ff_hud("Winamax Casablanca")
    hud_main.hud_dict = {"Casablanca": hud}
    try:
        assert hud_main._find_fast_fold_hud(_log_update(table_no="5")) == ("Casablanca", hud)
    finally:
        hud_main.hud_dict = {}


def test_window_reads_are_kept_per_window_not_globally(hud_main) -> None:
    """Two tables must not evict each other's seats; each read is a ~20ms IPC walk."""
    reads = []
    full = {slot: f"p{slot}" for slot in range(6)}

    def read_window(title, max_seats=6, **_kwargs):
        reads.append(title)
        return full

    hud_main.winamax_ax_seats = SimpleNamespace(read_window=read_window)
    hud5, hud6 = _ff_hud("Winamax Casablanca 5"), _ff_hud("Winamax Casablanca 6")

    hud_main._ax_slots(hud5, "hand-1", 6)
    hud_main._ax_slots(hud6, "hand-1", 6)
    hud_main._ax_slots(hud5, "hand-1", 6)
    assert reads == ["Winamax Casablanca 5", "Winamax Casablanca 6"]

    # A new hand is a new table, so it must be read again.
    hud_main._ax_slots(hud5, "hand-2", 6)
    assert reads[-1] == "Winamax Casablanca 5"
    assert len(reads) == 3


def test_an_empty_window_read_is_not_cached(hud_main) -> None:
    """The window may not be drawn yet; the next line of the same hand retries."""
    reads = []

    def read_window(title, max_seats=6, **_kwargs):
        reads.append(title)
        return {}

    hud_main.winamax_ax_seats = SimpleNamespace(read_window=read_window)
    hud = _ff_hud("Winamax Casablanca 5")

    hud_main._ax_slots(hud, "hand-1", 6)
    hud_main._ax_slots(hud, "hand-1", 6)
    assert len(reads) == 2


def test_stats_reference_hand_falls_back_to_the_same_pool(hud_main) -> None:
    """Without a gametypeId the stats aggregate is skipped and every seat reads NA."""
    hud_main._last_processed_hands = {"Casablanca 6": "hand-99"}

    assert hud_main._stats_reference_hand("Casablanca 6") == "hand-99"
    # Window 5 has had no hand imported yet, but shares the pool and its stakes.
    assert hud_main._stats_reference_hand("Casablanca 5") == "hand-99"
    # A different pool must not be borrowed from.
    assert hud_main._stats_reference_hand("Marbella 2") is None


def test_stats_reference_hand_resolves_a_window_discriminator_alias(hud_main) -> None:
    """A live window key can reuse the hand imported under its human key."""
    hud_main._last_processed_hands = {"Casablanca 6": "hand-99"}
    hud_main._fast_fold_aliases = {"Casablanca 6": "Casablanca 6 #48782"}

    assert hud_main._stats_reference_hand("Casablanca 6 #48782") == "hand-99"


def test_live_stats_read_always_ends_its_transaction() -> None:
    """A SELECT opens a transaction on PostgreSQL; leaving it open stalls the importer."""
    from fpdb_3_legacy.fast_fold_engine import FastFoldStatsRequest

    database = MagicMock()
    database.get_gameinfo_from_hid.return_value = {"gametypeId": 7}
    database.get_player_id_by_name.return_value = 55
    database.get_stats_for_players.return_value = {55: {"player_id": 55, "screen_name": "A", "n": 9}}

    request = FastFoldStatsRequest(temp_key="Casablanca 5", seat_map={1: "A"}, hand_id=101)
    result = HUD_main.HudReadWorker._read_fast_fold_stats(database, request)

    assert result.temp_key == "Casablanca 5"
    assert 55 in result.stat_dict
    database.connection.rollback.assert_called_once()


def test_live_stats_read_ends_its_transaction_even_when_it_fails() -> None:
    from fpdb_3_legacy.fast_fold_engine import FastFoldStatsRequest

    database = MagicMock()
    database.get_gameinfo_from_hid.side_effect = RuntimeError("boom")

    request = FastFoldStatsRequest(temp_key="Casablanca 5", seat_map={1: "A"}, hand_id=101)
    with pytest.raises(RuntimeError):
        HUD_main.HudReadWorker._read_fast_fold_stats(database, request)

    database.connection.rollback.assert_called_once()


def test_window_is_resolved_from_the_identity_snapshot(hud_main) -> None:
    """The identity snapshot arrives a hand before the Hand object, so use it."""
    hud_main.winamax_log_reader = SimpleNamespace(
        is_tailing=True,
        table_no_for_hand=lambda site_hand_no: "5" if site_hand_no == "227540101" else None,
    )
    hud_main._prepared_hands = {"101": SimpleNamespace(site_hand_no="227540101", hand_instance=None)}

    assert hud_main._qualify_fast_fold_table(_fast_info(hud_main), 101).info.table_name == "Casablanca 5"


def test_a_partial_window_read_is_not_frozen_for_the_whole_hand(hud_main) -> None:
    """The hand-start line beats the client to drawing the table."""
    answers = [
        {0: "Hero"},  # read at hand start: only the hero is drawn yet
        {0: "Hero", 2: "Player17", 5: "player09"},
        {0: "Hero", 2: "Player17", 5: "player09"},
    ]
    reads = []

    def read_window(title, max_seats=6, **_kwargs):
        reads.append(title)
        return answers[min(len(reads) - 1, len(answers) - 1)]

    hud_main.winamax_ax_seats = SimpleNamespace(read_window=read_window)
    hud = _ff_hud("Winamax Casablanca 5")

    assert hud_main._ax_slots(hud, "hand-1", 6) == {0: "Hero"}
    # The next look at the window must not be served from that partial answer.
    assert len(hud_main._ax_slots(hud, "hand-1", 6)) == 3
    assert len(reads) == 2


def test_window_rereads_are_bounded_within_a_hand(hud_main) -> None:
    reads = []

    def read_window(title, max_seats=6, **_kwargs):
        reads.append(title)
        return {0: "Hero"}

    hud_main.winamax_ax_seats = SimpleNamespace(read_window=read_window)
    hud = _ff_hud("Winamax Casablanca 5")

    for _ in range(20):
        hud_main._ax_slots(hud, "hand-1", 6)

    assert len(reads) == hud_main.AX_READS_PER_HAND


def test_a_full_table_stops_being_re_read(hud_main) -> None:
    reads = []
    full = {slot: f"p{slot}" for slot in range(6)}

    def read_window(title, max_seats=6, **_kwargs):
        reads.append(title)
        return full

    hud_main.winamax_ax_seats = SimpleNamespace(read_window=read_window)
    hud = _ff_hud("Winamax Casablanca 5")

    for _ in range(5):
        assert hud_main._ax_slots(hud, "hand-1", 6) == full

    assert len(reads) == 1


def test_recheck_replays_the_readers_current_state_for_a_pool(hud_main) -> None:
    """The window is looked at again on a timer, not on the next log line."""
    table = SimpleNamespace(pool="gf.p.t1.0", hand_id="h1", table_no="1", ring=[], hero=None, logged_at_ms=0)
    hud_main.winamax_log_reader = SimpleNamespace(get_table=lambda pool: table if pool == "gf.p.t1.0" else None)

    with patch.object(hud_main, "_on_winamax_table_update") as applied:
        hud_main._recheck_window("gf.p.t1.0")
        hud_main._recheck_window("gf.p.other")

    applied.assert_called_once_with(table)


def _ax_window(
    title="Winamax Casablanca 6",
    description="ESCAPE - 0,01-0,02 € - Pot Limit Omaha",
    window_id=None,
):
    from fpdb_3_legacy.winamax_ax_seats import AXTableWindow

    return AXTableWindow(title=title, description=description, window_id=window_id)


def test_a_hud_is_created_from_the_log_without_waiting_for_an_import(hud_main) -> None:
    """Display follows the log; hand histories only bring statistics."""
    hud_main.winamax_ax_seats = SimpleNamespace(find_table_window=lambda table_no: _ax_window())
    hud_main.hud_dict = {}
    created = {}

    def fake_create(hand_id, temp_key, info, site_id, num_seats, site, *, loading=False, stats=None):
        created.update(temp_key=temp_key, info=info, loading=loading, stats=stats, hand_id=hand_id)
        hud_main.hud_dict[temp_key] = SimpleNamespace(site="Winamax", table=SimpleNamespace(title=info.table_name))

    try:
        with patch.object(hud_main, "_create_new_hud", side_effect=fake_create):
            found = hud_main._find_fast_fold_hud(_log_update(table_no="6"))

        assert found is not None
        assert found[0] == "Casablanca 6"
        # A full HUD, not the placeholder: that one has no seat windows.
        assert created["loading"] is False
        assert created["stats"] == {}
        assert created["info"].poker_game == "omahahi"
        assert created["info"].fast is True
        assert created["info"].game_type == "ring"
        assert created["info"].max_seats == hud_main.FAST_FOLD_MAX_SEATS
        # No real hand exists, so a stand-in keeps the loading HUD off the database.
        assert created["hand_id"].startswith("live:")
        assert hud_main.hud_dict["Casablanca 6"].is_fast_fold is True
    finally:
        hud_main.hud_dict = {}


def test_fast_fold_reuses_the_window_resolved_at_hand_start(hud_main) -> None:
    """HUD construction must not perform a second macOS window lookup."""
    resolved = _ax_window(window_id=48_782)
    hud_main.winamax_ax_seats = SimpleNamespace(find_table_window=lambda table_no: resolved)
    hud_main.hud_dict = {}
    created = {}

    def fake_create(
        hand_id,
        temp_key,
        info,
        site_id,
        num_seats,
        site,
        *,
        loading=False,
        stats=None,
        resolved_window=None,
    ):
        created.update(resolved_window=resolved_window)
        hud_main.hud_dict[temp_key] = SimpleNamespace(site="Winamax", table=SimpleNamespace(title=info.table_name))

    try:
        with patch.object(hud_main, "_create_new_hud", side_effect=fake_create):
            assert hud_main._find_fast_fold_hud(_log_update(table_no="6")) is not None
        assert created["resolved_window"] is resolved
    finally:
        hud_main.hud_dict = {}


def test_no_hud_is_created_when_the_window_does_not_say_what_is_played(hud_main) -> None:
    hud_main.winamax_ax_seats = SimpleNamespace(
        find_table_window=lambda table_no: _ax_window(description="ESCAPE - 0,01-0,02 €")
    )
    hud_main.hud_dict = {}

    with patch.object(hud_main, "_create_new_hud") as create:
        assert hud_main._find_fast_fold_hud(_log_update(table_no="6")) is None
    create.assert_not_called()


def test_a_hud_is_created_from_the_title_alone_once_the_pool_game_is_known(hud_main) -> None:
    """A packaged build reads no window header, so the game comes from an import.

    Without this the Fast-Fold HUD waits for the hand history on every hand,
    which is the multi-second delay seen in the PyInstaller and PyOxidizer
    bundles but never in a source run.
    """
    from fpdb_3_legacy.winamax_pool_games import WinamaxPoolGames

    hud_main.winamax_pool_games = WinamaxPoolGames(None)
    hud_main.winamax_pool_games.remember("Casablanca", "omahahi")
    # System Events gives the title but cannot read the client's own header.
    hud_main.winamax_ax_seats = SimpleNamespace(find_table_window=lambda table_no: _ax_window(description=""))
    hud_main.hud_dict = {}
    created = {}

    def fake_create(hand_id, temp_key, info, site_id, num_seats, site, *, loading=False, stats=None):
        created.update(info=info)
        hud_main.hud_dict[temp_key] = SimpleNamespace(site="Winamax", table=SimpleNamespace(title=info.table_name))

    try:
        with patch.object(hud_main, "_create_new_hud", side_effect=fake_create):
            found = hud_main._find_fast_fold_hud(_log_update(table_no="6"))

        assert found is not None
        assert found[0] == "Casablanca 6"
        assert created["info"].poker_game == "omahahi"
    finally:
        hud_main.hud_dict = {}


def test_the_window_header_wins_over_what_was_remembered(hud_main) -> None:
    """A pool that changed game must not be built from a stale memory."""
    from fpdb_3_legacy.winamax_pool_games import WinamaxPoolGames

    hud_main.winamax_pool_games = WinamaxPoolGames(None)
    hud_main.winamax_pool_games.remember("Casablanca", "holdem")
    hud_main.winamax_ax_seats = SimpleNamespace(find_table_window=lambda table_no: _ax_window())
    hud_main.hud_dict = {}
    created = {}

    def fake_create(hand_id, temp_key, info, site_id, num_seats, site, *, loading=False, stats=None):
        created.update(info=info)
        hud_main.hud_dict[temp_key] = SimpleNamespace(site="Winamax", table=SimpleNamespace(title=info.table_name))

    try:
        with patch.object(hud_main, "_create_new_hud", side_effect=fake_create):
            hud_main._find_fast_fold_hud(_log_update(table_no="6"))
        assert created["info"].poker_game == "omahahi"
    finally:
        hud_main.hud_dict = {}


def test_an_imported_hand_records_what_its_pool_deals(hud_main) -> None:
    """That record is what lets every later hand skip the wait."""
    from fpdb_3_legacy.table_info import TableInfo
    from fpdb_3_legacy.winamax_pool_games import WinamaxPoolGames

    hud_main.winamax_pool_games = WinamaxPoolGames(None)
    hud_main._prepared_hands = {"42": SimpleNamespace(site_hand_no="22753788-426918-1786200400")}
    hud_main.winamax_log_reader = SimpleNamespace(table_no_for_hand=lambda _hand: "4", is_tailing=True)
    info = TableInfo(
        table_name="Colorado",
        max_seats=6,
        poker_game="omahahi",
        game_type="ring",
        fast=True,
        site_id=15,
        site_name="Winamax",
        num_seats=6,
    )

    qualified = hud_main._qualify_fast_fold_table(info, "42")

    assert qualified.info.table_name == "Colorado 4"
    assert qualified.table_no == "4"
    assert hud_main.winamax_pool_games.get("Colorado 2") == "omahahi"


def test_no_hud_is_created_when_the_window_is_gone(hud_main) -> None:
    hud_main.winamax_ax_seats = SimpleNamespace(find_table_window=lambda table_no: None)
    hud_main.hud_dict = {}

    with patch.object(hud_main, "_create_new_hud") as create:
        assert hud_main._find_fast_fold_hud(_log_update(table_no="9")) is None
    create.assert_not_called()


def test_an_existing_hud_is_reused_rather_than_recreated(hud_main) -> None:
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.winamax_ax_seats = SimpleNamespace(find_table_window=lambda table_no: _ax_window())
    hud_main.hud_dict = {"Casablanca 6": hud}
    try:
        with patch.object(hud_main, "_create_new_hud") as create:
            assert hud_main._find_fast_fold_hud(_log_update(table_no="6")) == ("Casablanca 6", hud)
        create.assert_not_called()
    finally:
        hud_main.hud_dict = {}


def _live_update(**kw):
    base = {
        "pool": "gf.p.t1.0",
        "table_no": "6",
        "hand_id": "h1",
        "table_id": "t1",
        "ring": ["Hero"],
        "hero": "Hero",
        "hero_left": False,
        "hand_over": False,
        "finished": False,
        "logged_at_ms": 0,
    }
    base.update(kw)
    base["finished"] = base["hero_left"] or base["hand_over"]
    return SimpleNamespace(**base)


def test_the_overlay_is_cleared_when_the_hero_fast_folds(hud_main) -> None:
    """Those players are no longer the ones in front of the hero."""
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.hud_dict = {"Casablanca 6": hud}
    hud_main._fast_fold_pending["Casablanca 6"] = {1: "Hero"}
    try:
        with patch.object(HUD_main.FastFoldEngine, "clear_seats") as cleared:
            hud_main._on_winamax_table_update(_live_update(hero_left=True))

        cleared.assert_called_once_with(hud)
        assert "Casablanca 6" not in hud_main._fast_fold_pending
    finally:
        hud_main.hud_dict = {}


def test_the_blocks_come_down_when_the_hand_is_over(hud_main) -> None:
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.hud_dict = {"Casablanca 6": hud}
    hud_main._fast_fold_pending["Casablanca 6"] = {1: "Hero"}
    try:
        with patch.object(HUD_main.FastFoldEngine, "clear_seats") as cleared:
            hud_main._on_winamax_table_update(_live_update(hand_over=True))
        cleared.assert_called_once_with(hud)
    finally:
        hud_main.hud_dict = {}


def test_a_table_holding_only_the_hero_is_not_worth_showing(hud_main) -> None:
    """Between hands the window still draws the hero, and nobody else."""
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.hud_dict = {"Casablanca 6": hud}
    hud_main._fast_fold_pending["Casablanca 6"] = {1: "Hero"}
    hud_main.winamax_ax_seats = SimpleNamespace(read_window=lambda t, max_seats=6, **_kwargs: {0: "Hero"})
    try:
        with patch.object(HUD_main.FastFoldEngine, "clear_seats") as cleared:
            hud_main._on_winamax_table_update(_live_update(ring=[], hero=None))
        cleared.assert_called_once_with(hud)
    finally:
        hud_main.hud_dict = {}


def test_clearing_an_already_empty_table_does_nothing(hud_main) -> None:
    hud = SimpleNamespace(stat_dict={})
    with patch.object(HUD_main.FastFoldEngine, "clear_seats") as cleared:
        hud_main._clear_fast_fold_table("Casablanca 6", hud, "h1", "hand over")
    cleared.assert_not_called()


def test_fast_fold_tables_are_left_out_of_the_secondary_refresh(hud_main) -> None:
    """That refresh swaps in the players of the last imported hand.

    On a Fast-Fold table those left long ago while the seats still point at the
    live players, so every block looks up a player id the statistics no longer
    hold -- a nameless column of NA.
    """
    fast = _ff_hud("Winamax Casablanca 3")
    slow = SimpleNamespace(site="Winamax", table=SimpleNamespace(title="Winamax Casablanca"), game_type="ring")
    hud_main.hud_dict = {"Casablanca 3": fast, "Casablanca": slow}
    hud_main._fast_fold_tables = {"Casablanca 3"}
    hud_main._last_processed_hands = {"Casablanca 3": 10, "Casablanca": 11}
    try:
        with patch.object(hud_main, "_get_table_info", return_value=None) as table_info:
            hud_main._tables_to_refresh(set())
        # Only the ordinary table was even looked up.
        assert [c.args[0] for c in table_info.call_args_list] == [11]
    finally:
        hud_main.hud_dict = {}


def test_a_half_drawn_window_is_not_acted_on(hud_main) -> None:
    """The client always draws the hero, so a read without them caught a redraw."""
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.hud_dict = {"Casablanca 6": hud}
    hud_main._fast_fold_tables = {"Casablanca 6"}
    # The table is currently showing players, so there is something to take down.
    hud_main._fast_fold_pending["Casablanca 6"] = {1: "Player01"}
    # Three players, none of them in the hero's chair.
    hud_main.winamax_ax_seats = SimpleNamespace(
        read_window=lambda t, max_seats=6, **_kwargs: {3: "Player01", 4: "Player04", 5: "Player06"}
    )
    try:
        with patch.object(HUD_main.FastFoldEngine, "clear_seats") as cleared:
            hud_main._on_winamax_table_update(_live_update(table_no="6"))
        cleared.assert_called_once_with(hud)
    finally:
        hud_main.hud_dict = {}


def test_the_log_ring_takes_over_when_the_window_never_shows_a_dealt_table(hud_main) -> None:
    """A client that will not answer properly must not leave the overlay blank.

    The window read is the better source and a partial one is not acted on --
    but once this hand's reads are spent, "partial" is the final answer, and the
    log-derived ring describes the table better than nothing does.
    """
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.hud_dict = {"Casablanca 6": hud}
    hud_main._fast_fold_tables = {"Casablanca 6"}
    # A read that names one player and never the hero's chair.
    hud_main.winamax_ax_seats = SimpleNamespace(read_window=lambda t, max_seats=6, **_kwargs: {3: "Player01"})
    # This hand's reads are already spent (the table is keyed by its title here).
    hud_main._ax_rings["Winamax Casablanca 6"] = ("h1", {3: "Player01"}, hud_main.AX_READS_PER_HAND)
    # A log line from later in the hand: the ring has had its chance to fill.
    hud_main._ff_started["h1"] = time.monotonic() - 1.0
    try:
        with patch.object(HUD_main.FastFoldEngine, "clear_seats") as cleared, patch.object(
            hud_main, "_request_fast_fold_stats"
        ) as requested:
            hud_main._on_winamax_table_update(_live_update(ring=["Hero", "Player01"], hero="Hero"))
        cleared.assert_not_called()
        assert set(requested.call_args.args[2].values()) == {"Hero", "Player01"}
    finally:
        hud_main.hud_dict = {}


def test_a_partial_read_is_still_not_acted_on_while_reads_remain(hud_main) -> None:
    hud = _ff_hud("Winamax Casablanca 6")
    hud_main.hud_dict = {"Casablanca 6": hud}
    hud_main._fast_fold_tables = {"Casablanca 6"}
    hud_main._fast_fold_pending["Casablanca 6"] = {1: "Player01"}
    hud_main.winamax_ax_seats = SimpleNamespace(read_window=lambda t, max_seats=6, **_kwargs: {3: "Player01"})
    try:
        with patch.object(HUD_main.FastFoldEngine, "clear_seats") as cleared:
            hud_main._on_winamax_table_update(_live_update(ring=["Hero", "Player01"], hero="Hero"))
        cleared.assert_called_once_with(hud)
    finally:
        hud_main.hud_dict = {}


def test_a_read_holding_the_hero_beats_a_bigger_one_without(hud_main) -> None:
    answers = [
        {1: "a", 2: "b", 3: "c", 4: "d"},  # half-drawn: no hero chair
        {0: "Hero", 2: "b", 3: "c"},  # drawn, and smaller
    ]
    reads = []

    def read_window(title, max_seats=6, **_kwargs):
        reads.append(title)
        return answers[min(len(reads) - 1, len(answers) - 1)]

    hud_main.winamax_ax_seats = SimpleNamespace(read_window=read_window)
    hud = _ff_hud("Winamax Casablanca 5")

    hud_main._ax_slots(hud, "hand-1", 6)
    assert hud_main._ax_slots(hud, "hand-1", 6) == {0: "Hero", 2: "b", 3: "c"}


def test_read_fast_fold_stats_does_not_guess_a_gametype() -> None:
    """A live table without a reference hand must not borrow a global gametype."""
    from fpdb_3_legacy.fast_fold_engine import FastFoldStatsRequest

    db = MagicMock()
    db.get_gameinfo_from_hid.return_value = None
    req = FastFoldStatsRequest(
        temp_key="Winamax Escape 1",
        seat_map={3: "Hero"},
        hand_id=None,
        num_seats=6,
    )

    with patch.object(HUD_main.FastFoldEngine, "get_player_stats_for_seat_map") as get_stats:
        get_stats.return_value = {1: {"screen_name": "Hero", "seat": 3, "n": 100}}
        res = HUD_main.HudReadWorker._read_fast_fold_stats(db, req)

    assert res.stat_dict[1]["n"] == 100
    assert get_stats.call_args.kwargs["gametype_id"] is None
    db.connection.cursor.assert_not_called()


def test_late_fast_fold_stats_are_dropped(hud_main) -> None:
    """A result from an older seat read cannot overwrite the current hand."""
    from fpdb_3_legacy.fast_fold_engine import FastFoldStatsResult

    hud = SimpleNamespace(stat_dict={}, seat_players={})
    hud_main.hud_dict = {"Escape 1": hud}
    hud_main._ff_pending_hand["Escape 1"] = "hand-new"
    hud_main._ff_pending_request["Escape 1"] = 2

    stale = FastFoldStatsResult(
        temp_key="Escape 1",
        seat_map={3: "old-player"},
        stat_dict={1: {"screen_name": "old-player", "seat": 3, "n": 1}},
        request_id=1,
    )
    with patch.object(HUD_main.FastFoldEngine, "apply_seats") as applied:
        hud_main._on_fast_fold_stats(stale)

    applied.assert_not_called()


def test_clearing_a_fast_fold_table_invalidates_inflight_stats(hud_main) -> None:
    """Clearing a table must also invalidate a worker result already in flight."""
    from fpdb_3_legacy.fast_fold_engine import FastFoldStatsResult

    hud = SimpleNamespace(stat_dict={1: {"screen_name": "old"}}, seat_players={1: "old"})
    hud_main.hud_dict = {"Escape 1": hud}
    hud_main._fast_fold_pending["Escape 1"] = {3: "old"}
    hud_main._ff_pending_request["Escape 1"] = 7

    hud_main._clear_fast_fold_table("Escape 1", hud, "hand-old", "new hand")
    stale = FastFoldStatsResult(temp_key="Escape 1", request_id=7)

    with patch.object(HUD_main.FastFoldEngine, "apply_seats") as applied:
        hud_main._on_fast_fold_stats(stale)

    applied.assert_not_called()


def test_an_import_never_repopulates_a_cleared_fast_fold_table(hud_main) -> None:
    """This is what put a finished table's players back after the hero sat out.

    The overlay is cleared, then a hand imported seconds later fell through to
    the ordinary path and seated its own -- long gone -- players, with no
    further hand coming to clear them again.
    """
    hud = SimpleNamespace(
        site="Winamax",
        table=SimpleNamespace(title="Winamax Casablanca 6"),
        stat_dict={},
        fast_fold_seats={},
        fast_fold_seat_players={},
        aux_windows=[],
        poker_game="holdem",
        max=6,
        is_loading=False,
        cards={},
        hud_params={"hud_days": 30, "h_hud_days": 90},
    )
    hud_main.hud_dict = {"Casablanca 6": hud}
    hud_main._fast_fold_tables = {"Casablanca 6"}
    hud_main.hero_ids = {1: 7}
    hud_main.hero = {1: "Hero"}
    imported = {77: {"screen_name": "Player01", "seat": 1, "n": 50}}
    hud_main.db_connection.get_stats_from_hand.return_value = imported

    try:
        with (
            patch.object(hud_main, "_seat_players", return_value={1: {"player_id": 77}}) as seat_players,
            patch.object(hud_main, "_merge_positions") as merge_positions,
            patch.object(hud_main, "_set_table_stats"),
            patch.object(hud_main, "get_cards", return_value={}),
            patch.object(hud_main, "update_HUD"),
        ):
            hud_main._update_existing_hud("hand-1", "Casablanca 6", "ring", 1, 6)

        # The live map owns the overlay, and it is empty.
        assert hud.stat_dict == {}
        assert hud.seat_players == {}
        seat_players.assert_not_called()
        merge_positions.assert_not_called()
    finally:
        hud_main.hud_dict = {}


def test_ordinary_pools_do_not_enter_the_fast_fold_path(hud_main) -> None:
    """A cash table has its own import-driven HUD; tracing it does nothing useful."""
    hud_main.hud_dict = {}
    with (
        patch.object(hud_main, "_ff_trace") as traced,
        patch.object(HUD_main.QTimer, "singleShot") as scheduled,
    ):
        hud_main._on_winamax_table_update(_live_update(pool="cg.tamgr.cg_4.t5228", table_no="9"))

    traced.assert_not_called()
    scheduled.assert_not_called()


def test_hud_is_fast_fold_matches_base_name_and_sets_flag(hud_main) -> None:
    """_hud_is_fast_fold matches base table names and sets is_fast_fold = True on the HUD."""
    hud = SimpleNamespace(table_name="Winamax - Bucarest 1", is_fast_fold=False)
    hud_main._fast_fold_tables = {"Winamax - Bucarest 1 #2410"}

    assert hud_main._hud_is_fast_fold(hud, "Bucarest 1") is True
    assert hud.is_fast_fold is True


def _tour_table(numbers: list[int | bool]) -> SimpleNamespace:
    """A tournament table window whose title reports `numbers` in turn."""
    reads = iter(numbers)
    return SimpleNamespace(
        type="tour",
        number=19310,
        key="1200531182 Table 1200531183",
        title_table_no=None,
        get_table_no=lambda: next(reads),
    )


def test_a_window_staying_on_its_table_keeps_its_hud(hud_main) -> None:
    """The poll must not disturb a table that is simply still being played."""
    table = _tour_table([1200531183, 1200531183])
    hud = SimpleNamespace(table=table)

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tour_table_switch(hud, table)  # attaches the baseline
        hud_main._handle_tour_table_switch(hud, table)

    stale.assert_not_called()
    assert table.title_table_no == 1200531183


def test_a_window_taken_over_by_the_next_match_drops_its_hud(hud_main) -> None:
    """A Twister client reuses the window for the next match of the series.

    Without this the finished tournament's HUD stayed on screen -- previous
    opponents and all -- until a hand of the new match was imported.
    """
    table = _tour_table([1200531183, 1200533055])
    hud = SimpleNamespace(table=table)

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tour_table_switch(hud, table)
        hud_main._handle_tour_table_switch(hud, table)

    stale.assert_called_once_with(hud)


def test_a_title_without_a_table_id_never_signals_a_switch(hud_main) -> None:
    """Sites whose title omits the table id must not have their HUD killed."""
    table = _tour_table([False, False])
    hud = SimpleNamespace(table=table)

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tour_table_switch(hud, table)
        hud_main._handle_tour_table_switch(hud, table)

    stale.assert_not_called()
    assert table.title_table_no is None


def test_a_table_that_was_never_found_is_an_error_once(hud_main) -> None:
    """A table open on screen that never gets a HUD is the case worth shouting about."""
    window = SimpleNamespace(search_string="Sea Lake")

    with patch.object(HUD_main.log, "error") as error, patch.object(HUD_main.log, "debug") as debug:
        hud_main._log_table_not_found("Sea Lake, 1", "Sea Lake, 1", "Bwin.fr Poker", "Bwin.fr Poker", window)
        hud_main._log_table_not_found("Sea Lake, 1", "Sea Lake, 1", "Bwin.fr Poker", "Bwin.fr Poker", window)

    assert error.call_count == 1
    assert debug.call_count == 1  # the repeat, not a second error


def test_a_closed_table_is_not_reported_as_an_error(hud_main) -> None:
    """Hands reach the HUD seconds late, so a just-closed table has no window left."""
    window = SimpleNamespace(search_string="Sea Lake")
    hud_main._tables_attached.add("Sea Lake, 1")

    with patch.object(HUD_main.log, "error") as error, patch.object(HUD_main.log, "info") as info:
        hud_main._log_table_not_found("Sea Lake, 1", "Sea Lake, 1", "Bwin.fr Poker", "Bwin.fr Poker", window)

    error.assert_not_called()
    assert info.call_count == 1


def test_the_baseline_is_the_table_the_hud_was_built_on(hud_main) -> None:
    """A window handed to the next match before the first poll must not set it.

    Seeding at attach is what makes the poll compare against the table this HUD
    was actually built on; taking the first poll's read as the baseline would
    adopt the replacement table and leave the stale HUD in place for good.
    """
    table = _tour_table([1200533055, 1200533055])  # window already moved on
    table.title_table_no = 1200531183  # what seed_title_table_no() recorded
    hud = SimpleNamespace(table=table)

    with patch.object(hud_main, "table_is_stale") as stale:
        hud_main._handle_tour_table_switch(hud, table)

    stale.assert_called_once_with(hud)


def test_a_seeded_table_window_reads_its_number_from_the_matched_title() -> None:
    """seed_title_table_no() uses the title the window search already captured."""
    from fpdb_3_legacy.TableWindow import Table_Window

    table = Table_Window.__new__(Table_Window)
    table.tableno_re = r"^[^|]*?(?<!\d)(\d{6,})\s*(?:\||$)"
    table.title = "Twister 0.25€ 1200531183 | NL Hold'em | Niveau 1 | 10/20"
    table.title_table_no = None

    table.seed_title_table_no()

    assert table.title_table_no == 1200531183


def test_a_title_the_pattern_cannot_read_leaves_no_baseline() -> None:
    """No baseline means the poll leaves that HUD alone, which is the safe end."""
    from fpdb_3_legacy.TableWindow import Table_Window

    table = Table_Window.__new__(Table_Window)
    table.tableno_re = r"(?:Twister|Spins)"  # no capturing group
    table.title = "Twister 0.25€ | NL Hold'em"
    table.title_table_no = None

    table.seed_title_table_no()

    assert table.title_table_no is None
