"""Unit tests for the macOS privacy-permission preflight module.

The permission checks live behind ``_IS_MACOS`` so every code path is
reachable from any OS: non-macOS branches are the safe no-ops, and the macOS
branches are exercised by patching the flag and the native frameworks.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from fpdb.infrastructure.platform import permissions
from fpdb.infrastructure.platform.permissions import PermissionStatus


def test_off_macos_everything_is_a_safe_noop() -> None:
    with patch.object(permissions, "_IS_MACOS", False):
        assert permissions.has_screen_recording_permission() is True
        assert permissions.has_accessibility_permission() is True
        assert permissions.request_screen_recording_permission() is True
        assert permissions.request_accessibility_permission() is True
        assert permissions.get_status().all_granted
        assert permissions.describe_missing() == []


def test_permission_status_aggregation() -> None:
    assert PermissionStatus(True, True).all_granted
    assert PermissionStatus(True, True, app_data=False).all_granted
    assert not PermissionStatus(True, False).all_granted
    assert not PermissionStatus(False, True).all_granted
    assert not PermissionStatus(False, False).all_granted


def test_screen_recording_queries_quartz() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        quartz = Mock(CGPreflightScreenCaptureAccess=Mock(return_value=True))
        with patch.dict("sys.modules", {"Quartz": quartz}):
            assert permissions.has_screen_recording_permission() is True
            quartz.CGPreflightScreenCaptureAccess.assert_called_once_with()


def test_screen_recording_unknown_failure_assumes_granted() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        quartz = Mock(CGPreflightScreenCaptureAccess=Mock(side_effect=RuntimeError("boom")))
        with patch.dict("sys.modules", {"Quartz": quartz}):
            assert permissions.has_screen_recording_permission() is True


def test_accessibility_queries_application_services() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        services = Mock(AXIsProcessTrusted=Mock(return_value=True))
        with patch.dict("sys.modules", {"ApplicationServices": services}):
            assert permissions.has_accessibility_permission() is True
            services.AXIsProcessTrusted.assert_called_once_with()


def test_accessibility_unknown_failure_assumes_granted() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        services = Mock(AXIsProcessTrusted=Mock(side_effect=RuntimeError("boom")))
        with patch.dict("sys.modules", {"ApplicationServices": services}):
            assert permissions.has_accessibility_permission() is True


def test_request_screen_recording_returns_status() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        quartz = Mock(CGRequestScreenCaptureAccess=Mock(return_value=False))
        with patch.dict("sys.modules", {"Quartz": quartz}):
            assert permissions.request_screen_recording_permission() is False


def test_request_screen_recording_falls_back_on_failure() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        quartz = Mock(CGRequestScreenCaptureAccess=Mock(side_effect=RuntimeError("boom")))
        with (
            patch.dict("sys.modules", {"Quartz": quartz}),
            patch.object(permissions, "has_screen_recording_permission", return_value=True),
        ):
            assert permissions.request_screen_recording_permission() is True


def test_request_accessibility_passes_prompt_option() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        services = Mock(AXIsProcessTrustedWithOptions=Mock(return_value=True))
        with patch.dict("sys.modules", {"ApplicationServices": services}):
            assert permissions.request_accessibility_permission(prompt=False) is True
            services.AXIsProcessTrustedWithOptions.assert_called_once_with(
                {services.kAXTrustedCheckOptionPrompt: False},
            )


def test_request_accessibility_prompt_defaults_to_true() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        services = Mock(AXIsProcessTrustedWithOptions=Mock(return_value=True))
        with patch.dict("sys.modules", {"ApplicationServices": services}):
            permissions.request_accessibility_permission()
            services.AXIsProcessTrustedWithOptions.assert_called_once_with(
                {services.kAXTrustedCheckOptionPrompt: True},
            )


def test_request_accessibility_falls_back_on_failure() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        services = Mock(AXIsProcessTrustedWithOptions=Mock(side_effect=RuntimeError("boom")))
        with (
            patch.dict("sys.modules", {"ApplicationServices": services}),
            patch.object(permissions, "has_accessibility_permission", return_value=False),
        ):
            assert permissions.request_accessibility_permission() is False


def test_open_settings_panes_are_noops_off_macos() -> None:
    with patch.object(permissions, "_IS_MACOS", False):
        with patch("fpdb.infrastructure.platform.permissions.subprocess.run") as run:
            permissions.open_screen_recording_settings()
            permissions.open_accessibility_settings()
            run.assert_not_called()


def test_open_settings_uses_deep_link_on_macos() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        with patch("fpdb.infrastructure.platform.permissions.subprocess.run") as run:
            permissions.open_screen_recording_settings()
            run.assert_called_once_with(
                ["open", permissions._SCREEN_RECORDING_PANE],
                check=False,
                timeout=5,
            )
            run.reset_mock()
            permissions.open_accessibility_settings()
            run.assert_called_once_with(
                ["open", permissions._ACCESSIBILITY_PANE],
                check=False,
                timeout=5,
            )


def test_app_data_exposes_no_synthetic_request_or_settings_action() -> None:
    assert not hasattr(permissions, "request_app_data_permission")
    assert not hasattr(permissions, "open_app_data_settings")
    assert not hasattr(permissions, "_APP_DATA_PANE")


def test_open_settings_swallows_failures() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        with patch("fpdb.infrastructure.platform.permissions.subprocess.run", side_effect=OSError("no open")) as run:
            permissions.open_screen_recording_settings()
            run.assert_called_once()


def test_describe_missing_lists_only_missing_permissions() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        status = PermissionStatus(False, False)
        messages = permissions.describe_missing(status)
        assert len(messages) == 2
        assert "Screen Recording" in messages[0]
        assert "quit and reopen FPDB manually only if" in messages[0]
        assert "Accessibility" in messages[1]
        assert "Recheck" in messages[1]
        assert "restart" not in messages[1].lower()


def test_describe_missing_reports_known_app_data_denial_without_gating_hud() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        status = PermissionStatus(True, True, app_data=False)
        messages = permissions.describe_missing(status)
        assert status.all_granted is True
        assert len(messages) == 1
        assert "App Data" in messages[0]
        assert "no safe preflight, request API, or dedicated Settings pane" in messages[0]


def test_describe_missing_none_fetches_status() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        with patch.object(permissions, "get_status", return_value=PermissionStatus(True, True)):
            assert permissions.describe_missing() == []


def test_get_status_builds_snapshot() -> None:
    with patch.object(permissions, "_IS_MACOS", True):
        with (
            patch.object(permissions, "has_screen_recording_permission", return_value=True),
            patch.object(permissions, "has_accessibility_permission", return_value=False),
        ):
            status = permissions.get_status()
            assert status.screen_recording is True
            assert status.accessibility is False
            assert status.app_data is None
