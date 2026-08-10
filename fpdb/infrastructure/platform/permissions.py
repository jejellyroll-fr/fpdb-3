"""macOS privacy-permission preflight for HUD table detection.

Table detection on macOS depends on separate privacy permissions, and a
missing one is the usual reason a HUD never appears ("table name ... not
found"):

* **Screen Recording** – required for Quartz (``CGWindowListCopyWindowInfo``) to
  expose window *titles* (``kCGWindowName``). Without it every title is empty,
  so title-based matching fails. Geometry/IDs are still available.
* **Accessibility** – required for the Winamax seat reader and for System
  Events GUI scripting of processes/windows.
* **App Data** – macOS may require consent when FPDB reads Winamax logs or hand
  histories owned by another application. There is no side-effect-free public
  preflight for this consent; its status is therefore informational until the
  first real file access, whose system prompt uses ``NSAppDataUsageDescription``.
* **Automation** – separately requested by macOS when FPDB sends an Apple Event
  to System Events. There is no side-effect-free preflight for that consent, so
  it is diagnosed from the first real scan rather than stored in this snapshot.

This module checks, requests, and explains those permissions. Everything is a
safe no-op (returning ``True``) on non-macOS so callers need no platform guard.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_IS_MACOS = platform.system() == "Darwin"

# System Settings deep links (Privacy & Security panes).
_SCREEN_RECORDING_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
_ACCESSIBILITY_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"


@dataclass(frozen=True)
class PermissionStatus:
    """Snapshot of the macOS permissions relevant to table detection."""

    screen_recording: bool
    accessibility: bool
    # macOS exposes no public, side-effect-free App Data preflight. ``None`` is
    # deliberately distinct from granted: the UI can explain that the status
    # is managed by macOS without pretending that access was verified.
    app_data: bool | None = None

    @property
    def all_granted(self) -> bool:
        # App Data is informational and must never gate table detection or HUD
        # startup: unlike the two checks above, it cannot be preflighted safely.
        return self.screen_recording and self.accessibility


def has_screen_recording_permission() -> bool:
    """Return True if Screen Recording is granted (no prompt). True off-macOS."""
    if not _IS_MACOS:
        return True
    try:
        import Quartz

        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        logger.debug("Could not preflight Screen Recording permission", exc_info=True)
        # Unknown -> assume granted so we don't nag on unexpected failures.
        return True


def has_accessibility_permission() -> bool:
    """Return True if Accessibility is granted (no prompt). True off-macOS."""
    if not _IS_MACOS:
        return True
    try:
        import ApplicationServices

        return bool(ApplicationServices.AXIsProcessTrusted())
    except Exception:
        logger.debug("Could not preflight Accessibility permission", exc_info=True)
        return True


def request_screen_recording_permission() -> bool:
    """Trigger the native Screen Recording prompt and add the app to the list.

    The prompt only appears the first time; afterwards this just reports the
    current status. A restart is required for a freshly granted permission to
    take effect. Returns the (current) granted state.
    """
    if not _IS_MACOS:
        return True
    try:
        import Quartz

        return bool(Quartz.CGRequestScreenCaptureAccess())
    except Exception:
        logger.debug("Could not request Screen Recording permission", exc_info=True)
        return has_screen_recording_permission()


def request_accessibility_permission(*, prompt: bool = True) -> bool:
    """Check Accessibility, optionally showing the system prompt. Returns status."""
    if not _IS_MACOS:
        return True
    try:
        import ApplicationServices

        options = {ApplicationServices.kAXTrustedCheckOptionPrompt: bool(prompt)}
        return bool(ApplicationServices.AXIsProcessTrustedWithOptions(options))
    except Exception:
        logger.debug("Could not request Accessibility permission", exc_info=True)
        return has_accessibility_permission()


def open_screen_recording_settings() -> None:
    """Open System Settings at the Screen Recording pane."""
    _open_pane(_SCREEN_RECORDING_PANE)


def open_accessibility_settings() -> None:
    """Open System Settings at the Accessibility pane."""
    _open_pane(_ACCESSIBILITY_PANE)


def _open_pane(url: str) -> None:
    if not _IS_MACOS:
        return
    try:
        subprocess.run(["open", url], check=False, timeout=5)
    except Exception:
        logger.debug("Could not open System Settings pane %s", url, exc_info=True)


def get_status() -> PermissionStatus:
    """Return the current permission snapshot."""
    return PermissionStatus(
        screen_recording=has_screen_recording_permission(),
        accessibility=has_accessibility_permission(),
        app_data=None,
    )


def describe_missing(status: PermissionStatus | None = None) -> list[str]:
    """Return actionable, human-readable lines for each missing permission."""
    if not _IS_MACOS:
        return []
    if status is None:
        status = get_status()

    messages: list[str] = []
    if not status.screen_recording:
        messages.append(
            "Screen Recording permission is missing: Quartz cannot read window "
            "titles, so poker tables won't be detected by title. Grant it in "
            "System Settings > Privacy & Security > Screen & System Audio "
            "Recording. Return to FPDB and use Recheck; quit and reopen FPDB "
            "manually only if table titles remain unavailable.",
        )
    if not status.accessibility:
        messages.append(
            "Accessibility permission is missing: FPDB cannot inspect poker "
            "windows or read Winamax seats through Accessibility/System Events. "
            "Grant it in System Settings > Privacy & Security > Accessibility "
            "and then return to FPDB and use Recheck.",
        )
    if status.app_data is False:
        messages.append(
            "App Data access is missing: FPDB may be unable to read Winamax "
            "logs or hand histories. macOS owns this consent and provides no "
            "safe preflight, request API, or dedicated Settings pane; FPDB "
            "therefore waits for the prompt from the first real file access.",
        )
    return messages
