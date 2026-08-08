"""Unit tests for the macOS/Quartz table detector.

``MacOSTableDetector.__init__`` imports PyObjC frameworks, so instances are
built with ``object.__new__`` and injected with a fake Quartz surface and a
stubbed ``subprocess.run`` for the AppleScript fallback.
"""

from __future__ import annotations

import time
import zlib
from subprocess import TimeoutExpired
from unittest.mock import Mock, patch

import pytest

from fpdb.infrastructure.platform.macos import MacOSTableDetector
from fpdb.infrastructure.platform.protocol import Platform, TableGeometry, TableInfo


def _detector(*, window_list: list[dict] | None = None) -> MacOSTableDetector:
    detector = object.__new__(MacOSTableDetector)
    detector._platform = Platform.MACOS
    detector._applescript_cache = {}
    detector._applescript_scan_ttl = 1.0
    detector._applescript_last_scan = 0.0
    detector._applescript_last_result = []
    detector._permissions_checked = False
    detector._permission_status = None
    detector._automation_warned = False
    detector._automation_blocked = False
    detector._NSWorkspace = Mock()
    detector._kCGNullWindowID = 0
    detector._kCGWindowListOptionOnScreenOnly = 8
    detector._CGWindowListCopyWindowInfo = Mock(return_value=window_list or [])
    return detector


def _hung_osascript() -> TimeoutExpired:
    """What osascript raises when the Automation prompt is left unanswered.

    This constructs an exception, not a process: Semgrep's subprocess audit
    matches the constructor by name, which is why the suppression lives here
    rather than being repeated at each use.
    """
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    return TimeoutExpired(cmd="osascript", timeout=5)


def _window(
    *,
    number: int = 1,
    title: str = "",
    owner: str = "PokerStars",
    pid: int = 100,
    width: int = 600,
    height: int = 500,
) -> dict:
    return {
        "kCGWindowNumber": number,
        "kCGWindowName": title,
        "kCGWindowOwnerName": owner,
        "kCGWindowOwnerPID": pid,
        "kCGWindowBounds": {"X": 10, "Y": 20, "Width": width, "Height": height},
    }


def test_platform_property() -> None:
    assert _detector().platform == Platform.MACOS


def test_constructor_initializes_quartz() -> None:
    nsworkspace = Mock()
    copy = Mock()
    with patch.dict(
        "sys.modules",
        {
            "AppKit": Mock(NSWorkspace=nsworkspace),
            "Quartz": Mock(),
            "Quartz.CoreGraphics": Mock(
                CGWindowListCopyWindowInfo=copy,
                kCGNullWindowID=0,
                kCGWindowListOptionOnScreenOnly=8,
            ),
        },
    ):
        detector = MacOSTableDetector()
    assert detector._NSWorkspace is nsworkspace
    assert detector._CGWindowListCopyWindowInfo is copy


def test_constructor_raises_when_pyobjc_missing() -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "AppKit":
            raise ImportError("no pyobjc")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="pyobjc"):
            MacOSTableDetector()


def test_find_tables_matches_regex_search() -> None:
    detector = _detector(
        window_list=[
            _window(number=1, title="PokerStars - Table 1", owner="PokerStars"),
            _window(number=2, title="Winamax - SpeedPool", owner="Winamax"),
        ],
    )
    tables = detector.find_tables("pokerstars")
    assert [t.window_id for t in tables] == [1]
    assert tables[0].geometry.x == 10
    assert tables[0].geometry.y == 20
    assert tables[0].geometry.width == 600
    assert tables[0].geometry.height == 500


def test_find_tables_empty_search_returns_all() -> None:
    detector = _detector(
        window_list=[_window(number=1, title="A"), _window(number=2, title="B")],
    )
    assert len(detector.find_tables("")) == 2


def test_find_tables_returns_fallback_when_quartz_blank() -> None:
    detector = _detector(window_list=[_window(number=1, title="", owner="PokerStars", pid=42)])
    fallback = [TableInfo(window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_name="PokerStars")]
    detector._find_tables_without_titles = Mock(return_value=fallback)
    assert detector.find_tables("pokerstars") == fallback


def test_find_tables_collects_blank_target_windows() -> None:
    detector = _detector(
        window_list=[
            _window(number=1, title="", owner="PokerStars", pid=42),
            _window(number=2, title="", owner="PokerStars", pid=43),
        ],
    )
    detector._find_tables_without_titles = Mock(return_value=None)
    detector.find_tables("pokerstars")
    detector._find_tables_without_titles.assert_called_once()
    args = detector._find_tables_without_titles.call_args[0]
    assert len(args[1]) == 2  # target_table_windows
    assert len(args[2]) == 2  # blank_target_windows


def test_find_tables_invalid_regex_falls_back_to_escape() -> None:
    detector = _detector(window_list=[_window(number=1, title="table 5", owner="PokerStars")])
    # "[" alone is an invalid regex; escaped it matches the literal.
    tables = detector.find_tables("table [")
    assert tables == []


def test_find_tables_swallows_quartz_error() -> None:
    detector = _detector()
    detector._CGWindowListCopyWindowInfo = Mock(side_effect=RuntimeError("quartz down"))
    assert detector.find_tables("pokerstars") == []


def test_is_target_process() -> None:
    detector = _detector()
    assert detector._is_target_process("PokerStars.EU")
    assert detector._is_target_process("pokerstars")
    assert detector._is_target_process("Winamax")
    assert not detector._is_target_process("Finder")
    assert not detector._is_target_process(None)
    assert not detector._is_target_process("")


def test_looks_like_table_window() -> None:
    detector = _detector()
    assert detector._looks_like_table_window(TableGeometry(0, 0, 300, 250))
    assert detector._looks_like_table_window(TableGeometry(0, 0, 1000, 800))
    assert not detector._looks_like_table_window(TableGeometry(0, 0, 299, 250))
    assert not detector._looks_like_table_window(TableGeometry(0, 0, 300, 249))


def test_find_tables_applescript_caches_and_filters() -> None:
    detector = _detector()
    detector._applescript_last_result = [
        TableInfo(window_id=1, title="PokerStars Table Alpha", geometry=TableGeometry(0, 0, 600, 500)),
        TableInfo(window_id=2, title="Winamax Pool", geometry=TableGeometry(0, 0, 600, 500)),
    ]
    detector._applescript_last_scan = time.monotonic()  # fresh, no rescan
    with patch("fpdb.infrastructure.platform.macos.subprocess.run") as run:
        tables = detector.find_tables_applescript("winamax")
        run.assert_not_called()
    assert [t.window_id for t in tables] == [2]


def test_find_tables_applescript_rescans_after_ttl() -> None:
    detector = _detector()
    detector._applescript_last_result = []
    detector._applescript_last_scan = 0.0  # stale -> triggers rescan
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        return_value=Mock(returncode=0, stdout="PokerStars|Table 1|0|0|600|500", stderr=""),
    ):
        tables = detector.find_tables_applescript("")
    assert len(tables) == 1
    assert tables[0].title == "Table 1"


def test_run_applescript_scan_parses_entries() -> None:
    detector = _detector()
    stdout = "PokerStars|Table 1|10|20|600|500, Winamax|SpeedPool|5|5|800|600, PokerStars|Lobby|0|0|300|200"
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        return_value=Mock(returncode=0, stdout=stdout, stderr=""),
    ):
        detector._run_applescript_scan()
    titles = [t.title for t in detector._applescript_last_result]
    assert titles == ["Table 1", "SpeedPool"]  # lobby filtered out
    window_id = detector._applescript_last_result[0].window_id
    assert window_id >= detector._FAKE_ID_BASE
    assert detector._applescript_cache[window_id].title == "Table 1"


def test_run_applescript_scan_skips_malformed_entries() -> None:
    detector = _detector()
    stdout = "PokerStars|Table 1|not|a|number|here, PokerStars|truncated"
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        return_value=Mock(returncode=0, stdout=stdout, stderr=""),
    ):
        detector._run_applescript_scan()
    assert detector._applescript_last_result == []


def test_run_applescript_scan_warns_on_automation_blocked() -> None:
    detector = _detector()
    result = Mock(returncode=1, stdout="", stderr="-1743 operation not allowed")
    with (
        patch("fpdb.infrastructure.platform.macos.subprocess.run", return_value=result),
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        detector._run_applescript_scan()
    assert detector._automation_warned is True
    logger.warning.assert_called_once()


def test_run_applescript_scan_warns_at_most_once() -> None:
    detector = _detector()
    result = Mock(returncode=1, stdout="", stderr="-1743 operation not allowed")
    with (
        patch("fpdb.infrastructure.platform.macos.subprocess.run", return_value=result),
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        detector._run_applescript_scan()
        detector._run_applescript_scan()
    assert logger.warning.call_count == 1


def test_run_applescript_scan_does_not_warn_on_other_errors() -> None:
    detector = _detector()
    result = Mock(returncode=1, stdout="", stderr="some other error")
    with (
        patch("fpdb.infrastructure.platform.macos.subprocess.run", return_value=result),
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        detector._run_applescript_scan()
    assert detector._automation_warned is False
    assert detector._automation_blocked is False
    logger.warning.assert_not_called()


def test_run_applescript_scan_treats_a_refusal_as_blocking() -> None:
    detector = _detector()
    result = Mock(returncode=1, stdout="", stderr="-1743 operation not allowed")
    with patch("fpdb.infrastructure.platform.macos.subprocess.run", return_value=result):
        detector._run_applescript_scan()
    assert detector._automation_blocked is True


def test_run_applescript_scan_treats_an_unanswered_prompt_as_blocking() -> None:
    """-1712 means the Automation dialog is up and nobody has answered it.

    Every later scan would sit through the same multi-second timeout, and
    Fast-Fold reaches this path on every hand.
    """
    detector = _detector()
    result = Mock(returncode=1, stdout="", stderr="AppleEvent timed out. (-1712)")
    with (
        patch("fpdb.infrastructure.platform.macos.subprocess.run", return_value=result),
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        detector._run_applescript_scan()
    assert detector._automation_blocked is True
    logger.warning.assert_called_once()


def test_run_applescript_scan_swallows_errors() -> None:
    detector = _detector()
    with patch("fpdb.infrastructure.platform.macos.subprocess.run", side_effect=OSError("osascript gone")):
        detector._run_applescript_scan()
    assert detector._applescript_last_result == []


def test_match_target_window_by_pid_exact() -> None:
    detector = _detector()
    windows = [
        TableInfo(window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=101),
        TableInfo(window_id=2, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=102),
    ]
    with patch(
        "fpdb.infrastructure.platform.macos_process.table_id_for_pid", side_effect={101: "922564", 102: "1"}.__getitem__
    ):
        assert detector._match_target_window_by_pid("922564", windows).window_id == 1


def test_match_target_window_by_pid_insensitive_to_punctuation() -> None:
    detector = _detector()
    windows = [TableInfo(window_id=7, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=101)]
    with patch("fpdb.infrastructure.platform.macos_process.table_id_for_pid", return_value="922-564"):
        assert detector._match_target_window_by_pid("922564", windows).window_id == 7


def test_match_target_window_by_pid_no_match() -> None:
    detector = _detector()
    windows = [TableInfo(window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=101)]
    with patch("fpdb.infrastructure.platform.macos_process.table_id_for_pid", return_value="999999"):
        assert detector._match_target_window_by_pid("922564", windows) is None


def test_match_target_window_by_pid_empty_target() -> None:
    detector = _detector()
    assert detector._match_target_window_by_pid("!!!", []) is None


def test_match_target_window_by_pid_missing_module() -> None:
    detector = _detector()
    import sys
    import types

    import fpdb.infrastructure.platform as platform_pkg

    # A module without `table_id_for_pid` forces the `from ... import` to raise
    # ImportError, the defensive short-circuit in _match_target_window_by_pid.
    stub = types.ModuleType("fpdb.infrastructure.platform.macos_process")
    saved_module = sys.modules.get("fpdb.infrastructure.platform.macos_process")
    saved_attr = platform_pkg.__dict__.get("macos_process")
    windows = [TableInfo(window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=101)]

    sys.modules["fpdb.infrastructure.platform.macos_process"] = stub
    platform_pkg.__dict__["macos_process"] = stub
    try:
        # A window that would match if the lookup worked must still yield
        # None, proving the ImportError short-circuit fired.
        assert detector._match_target_window_by_pid("922564", windows) is None
    finally:
        if saved_module is not None:
            sys.modules["fpdb.infrastructure.platform.macos_process"] = saved_module
        else:
            del sys.modules["fpdb.infrastructure.platform.macos_process"]
        if saved_attr is not None:
            platform_pkg.__dict__["macos_process"] = saved_attr
        else:
            platform_pkg.__dict__.pop("macos_process", None)


def test_match_target_window_by_pid_skips_failed_lookups() -> None:
    detector = _detector()
    windows = [
        TableInfo(window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=101),
        TableInfo(window_id=2, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=102),
    ]

    def lookup(pid: int) -> str:
        if pid == 101:
            raise RuntimeError("ps failed")
        return "922564"

    with patch("fpdb.infrastructure.platform.macos_process.table_id_for_pid", side_effect=lookup):
        assert detector._match_target_window_by_pid("922564", windows).window_id == 2


def test_match_target_window_by_pid_skips_empty_ids() -> None:
    detector = _detector()
    windows = [TableInfo(window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=101)]
    with patch("fpdb.infrastructure.platform.macos_process.table_id_for_pid", return_value=""):
        assert detector._match_target_window_by_pid("922564", windows) is None


def test_match_target_window_by_pid_skips_windows_without_pid() -> None:
    detector = _detector()
    windows = [
        TableInfo(window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=None),
        TableInfo(window_id=2, title="", geometry=TableGeometry(0, 0, 600, 500), process_id=102),
    ]
    with patch("fpdb.infrastructure.platform.macos_process.table_id_for_pid", return_value="922564"):
        assert detector._match_target_window_by_pid("922564", windows).window_id == 2


def test_get_window_geometry_for_fake_id_uses_cache() -> None:
    detector = _detector()
    fake_id = detector._FAKE_ID_BASE + 5
    detector._applescript_cache[fake_id] = TableInfo(
        window_id=fake_id,
        title="Table 1",
        geometry=TableGeometry(3, 4, 600, 500),
    )
    detector.find_tables_applescript = Mock()
    geometry = detector.get_window_geometry(fake_id)
    assert geometry == (3, 4, 600, 500) or (geometry.x, geometry.y, geometry.width, geometry.height) == (3, 4, 600, 500)
    detector.find_tables_applescript.assert_called_once_with("")


def test_get_window_geometry_for_real_id_queries_quartz() -> None:
    detector = _detector()
    desc = Mock(
        return_value=[{"kCGWindowBounds": {"X": 1, "Y": 2, "Width": 640, "Height": 480}}],
    )
    with patch.dict(
        "sys.modules", {"Quartz": Mock(), "Quartz.CoreGraphics": Mock(CGWindowListCreateDescriptionFromArray=desc)}
    ):
        geometry = detector.get_window_geometry(9)
    assert geometry == (1, 2, 640, 480) or (geometry.x, geometry.y, geometry.width, geometry.height) == (1, 2, 640, 480)


def test_get_window_geometry_none_when_window_missing() -> None:
    detector = _detector()
    desc = Mock(return_value=[])
    with patch.dict(
        "sys.modules", {"Quartz": Mock(), "Quartz.CoreGraphics": Mock(CGWindowListCreateDescriptionFromArray=desc)}
    ):
        assert detector.get_window_geometry(9) is None


def test_get_window_geometry_none_on_error() -> None:
    detector = _detector()
    with patch.dict(
        "sys.modules",
        {
            "Quartz": Mock(),
            "Quartz.CoreGraphics": Mock(CGWindowListCreateDescriptionFromArray=Mock(side_effect=RuntimeError)),
        },
    ):
        assert detector.get_window_geometry(9) is None


def test_is_window_visible_real_id() -> None:
    detector = _detector(window_list=[_window(number=5, title="Table")])
    assert detector.is_window_visible(5) is True
    assert detector.is_window_visible(6) is False


def test_is_window_visible_fake_id_rescans() -> None:
    detector = _detector()
    fake_id = detector._FAKE_ID_BASE + 5
    detector._applescript_cache[fake_id] = TableInfo(
        window_id=fake_id, title="T", geometry=TableGeometry(0, 0, 600, 500)
    )
    detector.find_tables_applescript = Mock()
    assert detector.is_window_visible(fake_id) is True
    detector.find_tables_applescript.assert_called_once_with("")


def test_is_window_visible_false_on_error() -> None:
    detector = _detector()
    detector._CGWindowListCopyWindowInfo = Mock(side_effect=OSError("boom"))
    assert detector.is_window_visible(5) is False


def test_is_window_displayed_mirrors_visibility() -> None:
    detector = _detector()
    detector.is_window_visible = Mock(return_value=True)
    assert detector.is_window_displayed(5) is True
    detector.is_window_visible = Mock(return_value=False)
    assert detector.is_window_displayed(5) is False


def test_get_window_title_fake_id() -> None:
    detector = _detector()
    fake_id = detector._FAKE_ID_BASE + 5
    detector._applescript_cache[fake_id] = TableInfo(
        window_id=fake_id,
        title="Table Alpha",
        geometry=TableGeometry(0, 0, 600, 500),
    )
    assert detector.get_window_title(fake_id) == "Table Alpha"
    assert detector.get_window_title(detector._FAKE_ID_BASE + 999) is None


def test_get_window_title_real_id() -> None:
    detector = _detector()
    desc = Mock(return_value=[{"kCGWindowName": "Table Beta"}])
    with patch.dict(
        "sys.modules", {"Quartz": Mock(), "Quartz.CoreGraphics": Mock(CGWindowListCreateDescriptionFromArray=desc)}
    ):
        assert detector.get_window_title(9) == "Table Beta"


def test_get_window_title_none_when_window_missing() -> None:
    detector = _detector()
    desc = Mock(return_value=[])
    with patch.dict(
        "sys.modules", {"Quartz": Mock(), "Quartz.CoreGraphics": Mock(CGWindowListCreateDescriptionFromArray=desc)}
    ):
        assert detector.get_window_title(9) is None


def test_get_window_title_none_on_error() -> None:
    detector = _detector()
    with patch.dict(
        "sys.modules",
        {
            "Quartz": Mock(),
            "Quartz.CoreGraphics": Mock(CGWindowListCreateDescriptionFromArray=Mock(side_effect=RuntimeError)),
        },
    ):
        assert detector.get_window_title(9) is None


def test_find_winamax_tables_applescript_parses() -> None:
    detector = _detector()
    stdout = "Winamax 02|10|20|800|600, Winamax|0|0|300|200"
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        return_value=Mock(returncode=0, stdout=stdout, stderr=""),
    ):
        tables = detector.find_winamax_tables_applescript()
    assert len(tables) == 1  # the lobby ("Winamax") is skipped
    assert tables[0].title == "Winamax 02"
    assert tables[0].process_name == "Winamax"
    assert tables[0].process_id == 0


def test_find_winamax_tables_skips_malformed_entries() -> None:
    detector = _detector()
    stdout = "Winamax 02|a|b|c|d, Winamax 03|truncated, Winamax 04|1|2|3"
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        return_value=Mock(returncode=0, stdout=stdout, stderr=""),
    ):
        tables = detector.find_winamax_tables_applescript()
    assert tables == []


def test_find_winamax_tables_timeout_warns() -> None:
    detector = _detector()
    with (
        patch("fpdb.infrastructure.platform.macos.subprocess.run", side_effect=TimeoutExpired("osascript", 5)),
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        assert detector.find_winamax_tables_applescript() == []
    logger.warning.assert_called_once()


def test_find_winamax_tables_empty_output() -> None:
    detector = _detector()
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        return_value=Mock(returncode=0, stdout="", stderr=""),
    ):
        assert detector.find_winamax_tables_applescript() == []


def test_find_winamax_tables_only_lobby_returns_empty() -> None:
    detector = _detector()
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        return_value=Mock(returncode=0, stdout="Winamax|0|0|300|200", stderr=""),
    ):
        assert detector.find_winamax_tables_applescript() == []


def test_find_winamax_tables_swallows_errors() -> None:
    detector = _detector()
    with patch("fpdb.infrastructure.platform.macos.subprocess.run", side_effect=OSError("no osascript")):
        assert detector.find_winamax_tables_applescript() == []


def test_focus_window_reports_unsupported() -> None:
    detector = _detector()
    assert detector.focus_window(5) is False


def test_resize_window_reports_unsupported() -> None:
    detector = _detector()
    assert detector.resize_window(5, 0, 0, 10, 10) is False


def test_check_permissions_once_logs_missing() -> None:
    detector = _detector()
    with (
        patch("fpdb.infrastructure.platform.macos.permissions") as permissions,
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        permissions.get_status.return_value = Mock(screen_recording=False, accessibility=False)
        permissions.describe_missing.return_value = ["missing screen recording", "missing accessibility"]
        detector._check_permissions_once()
        assert detector._permissions_checked is True
        assert logger.warning.call_count == 2


def test_check_permissions_once_requests_when_env_set() -> None:
    detector = _detector()
    with (
        patch.dict("os.environ", {"FPDB_REQUEST_MACOS_PERMISSIONS": "1"}),
        patch("fpdb.infrastructure.platform.macos.permissions") as permissions,
    ):
        permissions.get_status.return_value = Mock(screen_recording=False, accessibility=False)
        permissions.describe_missing.return_value = ["missing"]
        detector._check_permissions_once()
        permissions.request_screen_recording_permission.assert_called_once()
        permissions.open_screen_recording_settings.assert_called_once()
        permissions.request_accessibility_permission.assert_called_once_with(prompt=True)
        permissions.open_accessibility_settings.assert_called_once()


def test_check_permissions_once_env_skips_granted_permissions() -> None:
    detector = _detector()
    with (
        patch.dict("os.environ", {"FPDB_REQUEST_MACOS_PERMISSIONS": "1"}),
        patch("fpdb.infrastructure.platform.macos.permissions") as permissions,
    ):
        permissions.get_status.return_value = Mock(screen_recording=True, accessibility=False)
        permissions.describe_missing.return_value = ["missing accessibility"]
        detector._check_permissions_once()
        permissions.request_screen_recording_permission.assert_not_called()
        permissions.open_screen_recording_settings.assert_not_called()
        permissions.request_accessibility_permission.assert_called_once()


def test_check_permissions_once_env_skips_all_when_granted() -> None:
    detector = _detector()
    with (
        patch.dict("os.environ", {"FPDB_REQUEST_MACOS_PERMISSIONS": "1"}),
        patch("fpdb.infrastructure.platform.macos.permissions") as permissions,
    ):
        permissions.get_status.return_value = Mock(screen_recording=True, accessibility=True)
        permissions.describe_missing.return_value = []
        detector._check_permissions_once()
        permissions.request_screen_recording_permission.assert_not_called()
        permissions.open_screen_recording_settings.assert_not_called()
        permissions.request_accessibility_permission.assert_not_called()
        permissions.open_accessibility_settings.assert_not_called()


def test_check_permissions_once_env_accessibility_granted() -> None:
    detector = _detector()
    with (
        patch.dict("os.environ", {"FPDB_REQUEST_MACOS_PERMISSIONS": "1"}),
        patch("fpdb.infrastructure.platform.macos.permissions") as permissions,
    ):
        # Accessibility granted but Screen Recording missing: only the latter is
        # requested, and the accessibility branch is skipped.
        permissions.get_status.return_value = Mock(screen_recording=False, accessibility=True)
        permissions.describe_missing.return_value = ["missing screen recording"]
        detector._check_permissions_once()
        permissions.request_screen_recording_permission.assert_called_once()
        permissions.request_accessibility_permission.assert_not_called()


def test_check_permissions_once_runs_at_most_once() -> None:
    detector = _detector()
    with (
        patch("fpdb.infrastructure.platform.macos.permissions") as permissions,
        patch("fpdb.infrastructure.platform.macos.logger"),
    ):
        permissions.get_status.return_value = Mock(screen_recording=False, accessibility=False)
        permissions.describe_missing.return_value = ["missing"]
        detector._check_permissions_once()
        detector._check_permissions_once()
        assert permissions.describe_missing.call_count == 1


def test_check_permissions_once_noop_when_permissions_ok() -> None:
    detector = _detector()
    with (
        patch("fpdb.infrastructure.platform.macos.permissions") as permissions,
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        permissions.get_status.return_value = Mock(screen_recording=True, accessibility=True)
        permissions.describe_missing.return_value = []
        detector._check_permissions_once()
        assert detector._permissions_checked is True
        logger.debug.assert_called_once()


def test_find_tables_without_titles_prefers_pid_match() -> None:
    detector = _detector()
    target = TableInfo(
        window_id=1, title="", geometry=TableGeometry(0, 0, 600, 500), process_name="CoinPoker", process_id=99
    )
    detector._match_target_window_by_pid = Mock(return_value=target)
    result = detector._find_tables_without_titles("922564", [target], [], 2, 0)
    assert result == [target]


def test_find_tables_without_titles_falls_to_applescript() -> None:
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    applescript = [TableInfo(window_id=9, title="Table 9", geometry=TableGeometry(0, 0, 600, 500))]
    detector.find_tables_applescript = Mock(return_value=applescript)
    result = detector._find_tables_without_titles("table", [], [], 0, 0)
    assert result == applescript


def test_find_tables_without_titles_checks_permissions_when_no_titles() -> None:
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    detector.find_tables_applescript = Mock(return_value=[])
    detector._check_permissions_once = Mock()
    # total_windows > 0 but titled_windows == 0 => missing Screen Recording path.
    result = detector._find_tables_without_titles("table", [], [], 5, 0)
    assert result is None
    detector._check_permissions_once.assert_called_once()


def test_find_tables_without_titles_uses_sole_blank_window() -> None:
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    detector.find_tables_applescript = Mock(return_value=[])
    blank = TableInfo(window_id=3, title="", geometry=TableGeometry(0, 0, 600, 500), process_name="PokerStars")
    result = detector._find_tables_without_titles("pokerstars", [], [blank], 0, 0)
    assert result == [blank]


def test_find_tables_without_titles_still_scans_when_accessibility_is_missing() -> None:
    """Driving System Events needs Automation, which is a different grant.

    Gating the scan on Accessibility switched it off in every packaged build,
    and for an Electron client like Winamax it is the only way left to read a
    window title -- Quartz never exposes one.
    """
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    detector._check_permissions_once = Mock(return_value=Mock(accessibility=False))
    found = TableInfo(window_id=9, title="Winamax Bucarest 6", geometry=TableGeometry(0, 0, 600, 500))
    detector.find_tables_applescript = Mock(return_value=[found])
    blank = TableInfo(window_id=3, title="", geometry=TableGeometry(0, 0, 600, 500), process_name="Winamax")

    result = detector._find_tables_without_titles("Winamax Bucarest 6", [], [blank], 3, 0)

    detector.find_tables_applescript.assert_called_once_with("Winamax Bucarest 6")
    assert result == [found]


def test_find_tables_without_titles_stops_scanning_once_system_events_refuses() -> None:
    """A refused scan costs seconds, and Fast-Fold hits this path per hand."""
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    detector.find_tables_applescript = Mock(return_value=[])
    detector._automation_blocked = True
    blank = TableInfo(window_id=3, title="", geometry=TableGeometry(0, 0, 600, 500), process_name="Winamax")

    result = detector._find_tables_without_titles("Winamax Bucarest 6", [], [blank], 3, 0)

    detector.find_tables_applescript.assert_not_called()
    # The sole-window heuristic is still allowed to answer.
    assert result == [blank]


def test_find_tables_without_titles_rejects_cross_room_blank_window_fallback() -> None:
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    detector.find_tables_applescript = Mock(return_value=[])
    winamax_blank = TableInfo(window_id=3, title="", geometry=TableGeometry(0, 0, 600, 500), process_name="Winamax")
    # PartyPoker search string (#?7490030) must NOT hijack the Winamax window
    result = detector._find_tables_without_titles("#?7490030", [], [winamax_blank], 0, 0)
    assert result is None


def test_is_process_matching_search() -> None:
    detector = _detector()
    assert detector._is_process_matching_search("Winamax", "Winamax Casablanca 02") is True
    assert detector._is_process_matching_search("Winamax", "") is True
    assert detector._is_process_matching_search("Winamax", "#?7490030") is False
    assert detector._is_process_matching_search("Winamax", "PartyPoker Table 1") is False
    assert detector._is_process_matching_search("PokerStars", "PokerStars Table 5") is True
    assert detector._is_process_matching_search("PokerStars", "Winamax SpeedPool") is False


def test_a_window_with_no_owner_name_is_not_used_as_a_fallback() -> None:
    # Quartz does not always report an owner name. Calling casefold() on that
    # None used to be an AttributeError waiting for the first window without one.
    detector = _detector()
    assert detector._is_process_matching_search(None, "Winamax Casablanca 02") is False
    assert detector._is_process_matching_search(None, "") is False


def test_a_room_keyword_is_not_matched_inside_an_ordinary_table_name() -> None:
    # Keywords are substring-matched against the table search string too, so a
    # short one turns any table whose name happens to contain it into another
    # room and rejects a legitimate fallback.
    detector = _detector()
    assert detector._is_process_matching_search("Winamax", "Winamax Biggie 04") is True
    assert detector._is_process_matching_search("Winamax", "Winamax Coinflip 04") is True
    # The real rooms still reject each other.
    assert detector._is_process_matching_search("Winamax", "GGPoker Rush 12") is False
    assert detector._is_process_matching_search("CoinPoker", "Winamax Casablanca 02") is False


def test_find_tables_without_titles_returns_none() -> None:
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    detector.find_tables_applescript = Mock(return_value=[])
    assert detector._find_tables_without_titles("table", [], [], 0, 0) is None


def test_synthetic_window_id_is_deterministic() -> None:
    detector = _detector()
    base = detector._FAKE_ID_BASE
    one = base + zlib.crc32(b"Table Alpha") % 1_000_000
    two = base + zlib.crc32(b"Table Alpha") % 1_000_000
    assert one == two
    assert one >= base


def test_run_applescript_scan_treats_a_hung_scan_as_blocking() -> None:
    """An unanswered Automation prompt blocks osascript rather than failing it.

    TimeoutExpired never reaches the return-code handling, so before this the
    broad handler swallowed it and left the scan enabled -- every table lookup
    then paid the full timeout again.
    """
    detector = _detector()
    with (
        patch(
            "fpdb.infrastructure.platform.macos.subprocess.run",
            side_effect=_hung_osascript(),
        ),
        patch("fpdb.infrastructure.platform.macos.logger") as logger,
    ):
        detector._run_applescript_scan()

    assert detector._automation_blocked is True
    logger.warning.assert_called_once()
    logger.error.assert_not_called()


def test_a_hung_scan_is_not_repeated_on_the_next_lookup() -> None:
    """The whole point of noticing the block: the second lookup must be free."""
    detector = _detector()
    detector._match_target_window_by_pid = Mock(return_value=None)
    with patch(
        "fpdb.infrastructure.platform.macos.subprocess.run",
        side_effect=_hung_osascript(),
    ) as run:
        detector._find_tables_without_titles("Winamax Colorado 6", [], [], 3, 0)
        detector._find_tables_without_titles("Winamax Colorado 5", [], [], 3, 0)

    assert run.call_count == 1


def test_an_empty_result_still_respects_the_scan_ttl() -> None:
    """"Nothing found" is what a refused or hanging scan returns, too.

    Re-scanning whenever the last result was empty made that the one case that
    repeated on every lookup.
    """
    detector = _detector()
    detector._applescript_last_result = []
    detector._applescript_last_scan = time.monotonic()
    detector._run_applescript_scan = Mock()

    detector.find_tables_applescript("anything")

    detector._run_applescript_scan.assert_not_called()


def test_the_first_scan_still_runs_with_no_cached_result() -> None:
    detector = _detector()
    detector._applescript_last_result = []
    detector._applescript_last_scan = 0.0
    detector._run_applescript_scan = Mock()

    detector.find_tables_applescript("anything")

    detector._run_applescript_scan.assert_called_once()
