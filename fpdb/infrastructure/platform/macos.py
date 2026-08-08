"""macOS table detector implementation

Uses AppKit/Quartz frameworks for window detection on macOS.
Also uses AppleScript as fallback for apps like Winamax (Electron)
that don't expose window titles through Quartz.
"""

from __future__ import annotations

import logging
import os
import subprocess

from . import permissions
from .protocol import Platform, TableGeometry, TableInfo

logger = logging.getLogger(__name__)


class MacOSTableDetector:
    """macOS-specific table detector using Quartz/AppKit

    This implementation uses PyObjC to access macOS Quartz and AppKit
    frameworks for finding and manipulating poker table windows.

    Note:
        Requires pyobjc package to be installed.
        Only works on macOS platforms.
    """

    # Window IDs at or above this value are synthetic IDs assigned to windows
    # discovered through the AppleScript fallback (Quartz IDs are far smaller in
    # practice, and AppleScript does not expose the real CGWindowID).
    _FAKE_ID_BASE = 2_000_000
    _TARGET_PROCESSES = (
        "PokerStars",
        "PokerStars.FR",
        "PokerStars.COM",
        "PokerStars.EU",
        "PokerStars.IT",
        "PokerStars.ES",
        "PokerStars.PT",
        "PokerStars.DE",
        "pokerstars",
        "pokerstars.fr",
        "pokerstars.com",
        "pokerstars.eu",
        "pokerstars.it",
        "pokerstars.es",
        "pokerstars.pt",
        "pokerstars.de",
        "Winamax",
        "CoinPoker",
        "coinpoker",
        "Full Tilt",
        "Party",
        "888",
        "Pacific",
        "Bovada",
        "Bodog",
        "GGPoker",
        "SealsWithClubs",
        "PMU",
        "FDJ",
        "Bwin",
        "bwin",
        "betclic",
        "Betclic",
        "iPoker",
        "ipoker",
    )

    def __init__(self):
        """Initialize macOS table detector"""
        self._platform = Platform.MACOS

        # Cache of windows discovered via the AppleScript fallback, keyed by the
        # synthetic window ID. Lets get_window_geometry/get_window_title resolve
        # those windows (Quartz cannot, since the ID is not a real CGWindowID).
        self._applescript_cache: dict[int, TableInfo] = {}

        # Throttle the full (match-all) AppleScript scan. The HUD polls window
        # geometry/visibility several times per second and each synthetic-window
        # lookup re-runs find_tables_applescript(""), a slow synchronous
        # `osascript` call. Serving repeated full scans from a short-lived cache
        # keeps those polls from starving the Qt GUI thread (sluggish popups /
        # HUD drags). Real moves/resizes are still picked up within the TTL.
        self._applescript_scan_ttl = 1.0  # seconds
        self._applescript_last_scan = 0.0
        self._applescript_last_result: list[TableInfo] = []

        # Emit the privacy-permission diagnosis at most once per process.
        self._permissions_checked = False
        self._permission_status: permissions.PermissionStatus | None = None
        self._automation_warned = False

        # Lazy-import macOS dependencies
        try:
            from AppKit import NSWorkspace
            from Quartz.CoreGraphics import (
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListOptionOnScreenOnly,
            )

            self._NSWorkspace = NSWorkspace
            self._CGWindowListCopyWindowInfo = CGWindowListCopyWindowInfo
            self._kCGNullWindowID = kCGNullWindowID
            self._kCGWindowListOptionOnScreenOnly = kCGWindowListOptionOnScreenOnly

            logger.info("macOS table detector initialized")

        except ImportError as e:
            logger.error(f"Failed to import macOS dependencies: {e}")
            raise ImportError("pyobjc is required for macOS table detection. Install with: pip install pyobjc") from e

    @property
    def platform(self) -> Platform:
        """Get the current platform"""
        return self._platform

    def _check_permissions_once(self) -> permissions.PermissionStatus:
        """Log the privacy-permission diagnosis once when titles are missing.

        Set ``FPDB_REQUEST_MACOS_PERMISSIONS=1`` to also trigger the native
        prompts / open the relevant System Settings panes automatically.
        """
        if self._permissions_checked:
            return self._permission_status or permissions.get_status()
        self._permissions_checked = True

        status = permissions.get_status()
        self._permission_status = status
        messages = permissions.describe_missing(status)
        if not messages:
            # Titles missing despite permissions looking granted (e.g. an
            # Electron client like Winamax): the AppleScript fallback handles it.
            logger.debug(
                "Quartz exposed no window titles but permissions look granted; relying on the AppleScript fallback.",
            )
            return status

        for message in messages:
            logger.warning(message)

        if os.getenv("FPDB_REQUEST_MACOS_PERMISSIONS") == "1":
            if not status.screen_recording:
                logger.info("Requesting Screen Recording permission (native prompt)...")
                permissions.request_screen_recording_permission()
                permissions.open_screen_recording_settings()
            if not status.accessibility:
                logger.info("Requesting Accessibility permission (native prompt)...")
                permissions.request_accessibility_permission(prompt=True)
                permissions.open_accessibility_settings()
        return status

    def find_tables(self, search_string: str = "") -> list[TableInfo]:
        """Find all windows matching the search string

        Args:
            search_string: String to search for in window titles

        Returns:
            List of TableInfo for matching windows
        """
        tables = []
        import re

        try:
            pattern = re.compile(search_string, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(search_string), re.IGNORECASE)

        total_windows = 0
        titled_windows = 0
        blank_target_windows = []
        target_table_windows = []
        try:
            # Get list of all on-screen windows
            options = self._kCGWindowListOptionOnScreenOnly
            window_list = self._CGWindowListCopyWindowInfo(options, self._kCGNullWindowID)

            for window in window_list:
                window_number = window.get("kCGWindowNumber")
                window_title = window.get("kCGWindowName", "")
                owner_name = window.get("kCGWindowOwnerName", "")
                pid = window.get("kCGWindowOwnerPID")
                bounds = window.get("kCGWindowBounds", {})

                total_windows += 1
                if window_title:
                    titled_windows += 1

                geometry = TableGeometry(
                    x=int(bounds.get("X", 0)),
                    y=int(bounds.get("Y", 0)),
                    width=int(bounds.get("Width", 0)),
                    height=int(bounds.get("Height", 0)),
                )

                if search_string and self._is_target_process(owner_name) and self._looks_like_table_window(geometry):
                    candidate = TableInfo(
                        window_id=window_number,
                        title=window_title,
                        geometry=geometry,
                        process_name=owner_name,
                        process_id=pid,
                    )
                    # Every target poker table window, whatever its title. Used to
                    # resolve the real table id from the owning process's argv
                    # (CoinPoker) when the title doesn't carry it.
                    target_table_windows.append(candidate)
                    if not window_title:
                        blank_target_windows.append(candidate)

                # Check if matches search using regex
                if not search_string or pattern.search(window_title):
                    table_info = TableInfo(
                        window_id=window_number,
                        title=window_title,
                        geometry=geometry,
                        process_name=owner_name,
                        process_id=pid,
                    )
                    tables.append(table_info)

        except Exception as e:
            logger.error(f"Error finding tables via Quartz: {e}", exc_info=True)

        # Quartz only exposes window titles when Screen Recording permission is
        # granted; without it kCGWindowName is empty for every window. Electron
        # clients (e.g. Winamax) also never expose titles through Quartz. Detect
        # both cases so we can tell a permission problem apart from a regex miss.
        logger.debug(
            "DIAGNOSTIC: Quartz saw %d on-screen windows, %d with titles; %d matched search '%s'",
            total_windows,
            titled_windows,
            len(tables),
            search_string,
        )

        # Fallback to AppleScript / argv when Quartz produced no usable match:
        # either no window matched, or none exposed a title at all (missing Screen
        # Recording permission / Electron client).
        has_only_empty_titles = len(tables) > 0 and all(t.title == "" for t in tables)
        if len(tables) == 0 or has_only_empty_titles:
            fallback = self._find_tables_without_titles(
                search_string,
                target_table_windows,
                blank_target_windows,
                total_windows,
                titled_windows,
            )
            if fallback is not None:
                return fallback

        logger.debug(f"DIAGNOSTIC: Found {len(tables)} matching tables via Quartz")
        return tables

    def _find_tables_without_titles(
        self,
        search_string: str,
        target_table_windows: list[TableInfo],
        blank_target_windows: list[TableInfo],
        total_windows: int,
        titled_windows: int,
    ) -> list[TableInfo] | None:
        """Resolve tables when Quartz exposed no usable title, else return None.

        Tried in order: the owning process's argv (deterministic, no Screen
        Recording), then AppleScript, then the sole blank target window.
        """
        # CoinPoker renders each table in its own Unity process whose window
        # carries no useful title and no accessibility text, so the tables are
        # indistinguishable to every macOS window API. The owning process's argv,
        # however, contains the table id (window -> kCGWindowOwnerPID -> argv ->
        # table id). This is deterministic, so try it before AppleScript.
        if search_string and target_table_windows:
            pid_match = self._match_target_window_by_pid(search_string, target_table_windows)
            if pid_match is not None:
                logger.debug(
                    "DIAGNOSTIC: argv matched %s window %s (pid %s) for search %r",
                    pid_match.process_name,
                    pid_match.window_id,
                    pid_match.process_id,
                    search_string,
                )
                return [pid_match]

        permission_status = self._check_permissions_once()
        if not (total_windows > 0 and titled_windows == 0):
            logger.debug("DIAGNOSTIC: No Quartz window matched the search string. Trying AppleScript fallback...")
        # System Events takes around two seconds to reject an untrusted app.
        # Fast-Fold can hit this path several times for one newly imported hand,
        # so do not make a synchronous call that the native permission check has
        # already told us cannot succeed.
        applescript_tables = []
        if permission_status.accessibility:
            applescript_tables = self.find_tables_applescript(search_string)
        else:
            logger.debug("Skipping AppleScript table scan because Accessibility permission is unavailable")
        if applescript_tables:
            logger.debug(f"DIAGNOSTIC: AppleScript fallback found {len(applescript_tables)} matching tables")
            return applescript_tables

        if len(blank_target_windows) == 1:
            fallback = blank_target_windows[0]
            if self._is_process_matching_search(fallback.process_name, search_string):
                logger.warning(
                    "Using the only visible %s window as a fallback for table search %r "
                    "because macOS did not expose a window title and AppleScript did not "
                    "return a match. Grant Screen Recording/Accessibility permissions for "
                    "reliable multi-table detection.",
                    fallback.process_name,
                    search_string,
                )
                return [fallback]

        return None

    def _is_process_matching_search(self, process_name: str | None, search_string: str) -> bool:
        """Check if a fallback target window's process matches the search string.

        Prevents cross-assigning a fallback window of one poker client (e.g. Winamax)
        to a table search originating from a different poker room (e.g. PartyPoker).

        Quartz does not always report an owner name, which is why TableInfo types
        it as optional. A window whose process cannot be identified is exactly the
        one this check exists to refuse: there is nothing to compare the search
        against, so it is not offered as a fallback.
        """
        if process_name is None:
            return False

        if not search_string:
            return True

        search_lower = search_string.casefold()
        proc_lower = process_name.casefold()

        # Keywords are matched as substrings against both the process name and
        # the table search string, so every one of them has to be long enough to
        # be a room and nothing else. "gg" and "coin" were not: a table named
        # "Biggie" or "Coinflip" reads as GGPoker or CoinPoker and gets a
        # legitimate fallback from another room rejected. The full product names
        # already cover the real process names.
        process_groups: dict[str, tuple[str, ...]] = {
            "winamax": ("winamax",),
            "pokerstars": ("pokerstars", "stars"),
            "party": ("party", "pmu", "bwin"),
            "coinpoker": ("coinpoker",),
            "full tilt": ("full tilt", "fulltilt"),
            "888": ("888", "pacific"),
            "bovada": ("bovada", "bodog"),
            "ggpoker": ("ggpoker",),
            "sealswithclubs": ("seals", "swc"),
            "ipoker": ("ipoker", "betclic"),
        }

        fallback_group = None
        for group, keywords in process_groups.items():
            if any(kw in proc_lower for kw in keywords):
                fallback_group = group
                break

        if fallback_group is None:
            return proc_lower in search_lower

        # Reject if search_string explicitly belongs to another poker process family
        for group, keywords in process_groups.items():
            if group == fallback_group:
                continue
            if any(kw in search_lower for kw in keywords):
                return False

        # If search_string does not mention fallback_group keywords, reject unless search_string is empty/wildcard
        fallback_keywords = process_groups[fallback_group]
        if not any(kw in search_lower for kw in fallback_keywords):
            if search_lower not in ("", ".*", "^.*$"):
                return False

        return True

    def _is_target_process(self, process_name: str | None) -> bool:
        if not process_name:
            return False
        folded_process_name = process_name.casefold()
        return any(target.casefold() in folded_process_name for target in self._TARGET_PROCESSES)

    def _looks_like_table_window(self, geometry: TableGeometry) -> bool:
        return geometry.width >= 300 and geometry.height >= 250

    def _match_target_window_by_pid(
        self,
        search_string: str,
        windows: list[TableInfo],
    ) -> TableInfo | None:
        """Return the table window whose owning process argv carries ``search_string``.

        CoinPoker table windows are owned by per-table Unity processes that pass
        the table id on their command line, so the window's ``kCGWindowOwnerPID``
        resolves to that id without reading pixels or a window title. Matching is
        digit/whitespace-insensitive so a table id like ``922564`` matches the
        escaped search string. Returns ``None`` when unavailable or no match.
        """
        try:
            from .macos_process import table_id_for_pid
        except ImportError:
            return None

        target = "".join(ch for ch in search_string if ch.isalnum()).lower()
        if not target:
            return None

        for window in windows:
            if not window.process_id:
                continue
            try:
                table_id = table_id_for_pid(window.process_id)
            except Exception as exc:  # pragma: no cover - platform dependent
                logger.debug("argv lookup failed for pid %s: %s", window.process_id, exc)
                continue
            if not table_id:
                continue
            resolved = "".join(ch for ch in table_id if ch.isalnum()).lower()
            # Exact match only: both the window's argv id and the imported hand's
            # table id are the same derivation (game hand id // 100000), so a
            # substring match would risk cross-assigning two similar table ids.
            if resolved and resolved == target:
                return window
        return None

    def _run_applescript_scan(self) -> None:
        """Execute the full AppleScript scan and populate the cache.

        This lists all windows of the target processes and updates the cache.
        """
        import re
        import subprocess
        import time
        import zlib

        logger.debug("DIAGNOSTIC: Running full AppleScript scan")
        self._applescript_cache.clear()
        self._applescript_last_result = []

        try:
            # Script AppleScript pour lister toutes les fenêtres de ces processus
            script_lines = [
                'tell application "System Events"',
                "    set windowList to {}",
                "    repeat with proc in (every process whose visible is true)",
                "        set procName to name of proc",
                "        set isTarget to false",
                "        -- Check against target poker apps",
            ]
            for proc in self._TARGET_PROCESSES:
                script_lines.append(f'        if procName contains "{proc}" then')
                script_lines.append("            set isTarget to true")
                script_lines.append("        end if")

            script_lines.extend(
                [
                    "        if isTarget then",
                    "            repeat with win in (every window of proc)",
                    "                try",
                    "                    set winName to name of win",
                    "                    set winPos to position of win",
                    "                    set winSize to size of win",
                    '                    set end of windowList to procName & "|" & winName & "|" & (item 1 of winPos) & "|" & (item 2 of winPos) & "|" & (item 1 of winSize) & "|" & (item 2 of winSize)',
                    "                end try",
                    "            end repeat",
                    "        end if",
                    "    end repeat",
                    "    return windowList",
                    "end tell",
                ]
            )

            script = "\n".join(script_lines)
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)

            logger.debug(
                "DIAGNOSTIC: AppleScript exited with code %d. Output len: %d. Error: '%s'",
                result.returncode,
                len(result.stdout),
                result.stderr.strip(),
            )

            if result.returncode != 0 and not self._automation_warned:
                stderr = result.stderr.strip()
                if "-1743" in stderr or "Not authorized to send Apple events" in stderr:
                    self._automation_warned = True
                    logger.warning(
                        "AppleScript fallback is blocked: this app is not allowed to "
                        "control 'System Events' (Automation). Grant it in System "
                        "Settings > Privacy & Security > Automation (allow FPDB/your "
                        "terminal to control System Events), then restart FPDB. "
                        "osascript error: %s",
                        stderr,
                    )

            if result.returncode == 0 and result.stdout.strip():
                windows_str = result.stdout.strip()
                # Sortie de la forme: "proc|title|x|y|w|h, proc|title|x|y|w|h, ..."
                entries = re.split(r",\s*(?=[a-zA-Z0-9_.\-\s]+\|)", windows_str)

                for entry in entries:
                    parts = entry.split("|")
                    if len(parts) >= 6:
                        proc_name = parts[0].strip()
                        title = parts[1].strip()
                        try:
                            x = int(float(parts[2]))
                            y = int(float(parts[3]))
                            width = int(float(parts[4]))
                            height = int(float(parts[5]))
                        except (ValueError, IndexError):
                            continue

                        # Si la fenêtre a des dimensions valides
                        if title and not any(
                            bad in title for bad in ["History for table:", "HUD:", "Chat:", "FPDBHUD", "Lobby"]
                        ):
                            geometry = TableGeometry(x=x, y=y, width=width, height=height)
                            # Deterministic synthetic ID derived from the title
                            window_id = self._FAKE_ID_BASE + (zlib.crc32(title.encode("utf-8")) % 1_000_000)
                            table_info = TableInfo(
                                window_id=window_id,
                                title=title,
                                geometry=geometry,
                                process_name=proc_name,
                                process_id=0,
                            )
                            self._applescript_last_result.append(table_info)
                            self._applescript_cache[window_id] = table_info

        except Exception as e:
            logger.error(f"Error in _run_applescript_scan: {e}", exc_info=True)

        self._applescript_last_scan = time.monotonic()

    def find_tables_applescript(self, search_string: str = "") -> list[TableInfo]:
        """Find tables using AppleScript for all active poker processes.

        This serves as a robust fallback on macOS 10.15+ when Screen Recording
        permissions are missing or when Electron apps do not expose titles via Quartz.
        """
        import re
        import time

        now = time.monotonic()
        if not self._applescript_last_result or (now - self._applescript_last_scan) >= self._applescript_scan_ttl:
            self._run_applescript_scan()

        try:
            pattern = re.compile(search_string, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(search_string), re.IGNORECASE)

        tables = []
        for table_info in self._applescript_last_result:
            matches_pattern = not search_string or pattern.search(table_info.title)
            logger.debug(
                "DIAGNOSTIC: AppleScript candidate window '%s' (process: %s). Matches pattern? %s",
                table_info.title,
                table_info.process_name,
                matches_pattern,
            )
            if matches_pattern:
                tables.append(table_info)

        return tables

    def get_window_geometry(self, window_id: int | str) -> TableGeometry | None:
        """Get geometry for a specific window

        Args:
            window_id: Window number (CGWindowID)

        Returns:
            TableGeometry if successful, None otherwise
        """
        try:
            window_id = int(window_id)

            # Synthetic AppleScript window: refresh via AppleScript so geometry
            # tracks moves/resizes, then return the cached bounds. Quartz cannot
            # resolve these IDs because they are not real CGWindowIDs.
            if window_id >= self._FAKE_ID_BASE:
                self.find_tables_applescript("")
                cached = self._applescript_cache.get(window_id)
                return cached.geometry if cached else None

            # Get window info for specific window
            from Quartz.CoreGraphics import CGWindowListCreateDescriptionFromArray

            window_info = CGWindowListCreateDescriptionFromArray([window_id])
            if window_info and len(window_info) > 0:
                bounds = window_info[0].get("kCGWindowBounds", {})
                return TableGeometry(
                    x=int(bounds.get("X", 0)),
                    y=int(bounds.get("Y", 0)),
                    width=int(bounds.get("Width", 0)),
                    height=int(bounds.get("Height", 0)),
                )

        except Exception as e:
            logger.debug(f"Error getting geometry for window {window_id}: {e}")

        return None

    def is_window_visible(self, window_id: int | str) -> bool:
        """Check if window is visible

        Args:
            window_id: Window number

        Returns:
            True if window exists and is on screen
        """
        try:
            window_id = int(window_id)

            # Synthetic AppleScript window: visible if a rescan still finds it.
            if window_id >= self._FAKE_ID_BASE:
                self.find_tables_applescript("")
                return window_id in self._applescript_cache

            options = self._kCGWindowListOptionOnScreenOnly
            window_list = self._CGWindowListCopyWindowInfo(options, self._kCGNullWindowID)

            for window in window_list:
                if window.get("kCGWindowNumber") == window_id:
                    return True

            return False

        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def is_window_displayed(self, window_id: int | str) -> bool:
        """Check if window is actually shown on screen right now

        macOS has no equivalent of DWM cloaking, and is_window_visible()
        already queries the on-screen window list, so this mirrors it.

        Args:
            window_id: Window number

        Returns:
            True if window exists and is on screen
        """
        return self.is_window_visible(window_id)

    def get_window_title(self, window_id: int | str) -> str | None:
        """Get window title

        Args:
            window_id: Window number

        Returns:
            Window title or None if not found
        """
        try:
            window_id = int(window_id)

            # Synthetic AppleScript window: return the cached title.
            if window_id >= self._FAKE_ID_BASE:
                cached = self._applescript_cache.get(window_id)
                return cached.title if cached else None

            from Quartz.CoreGraphics import CGWindowListCreateDescriptionFromArray

            window_info = CGWindowListCreateDescriptionFromArray([window_id])
            if window_info and len(window_info) > 0:
                return window_info[0].get("kCGWindowName", "")

        except Exception as e:
            logger.debug(f"Error getting title for window {window_id}: {e}")

        return None

    def find_winamax_tables_applescript(self) -> list[TableInfo]:
        """Find Winamax tables using AppleScript (fallback for Electron apps)

        Winamax on macOS is an Electron app that doesn't expose window titles
        through Quartz. This method uses AppleScript to get window titles.

        Returns:
            List of TableInfo for Winamax windows
        """
        tables = []

        try:
            # Get window titles via AppleScript
            script = """
            tell application "System Events"
                set windowList to {}
                repeat with proc in (processes whose name contains "Winamax")
                    repeat with win in (every window of proc)
                        set winName to name of win
                        set winPos to position of win
                        set winSize to size of win
                        set end of windowList to winName & "|" & (item 1 of winPos) & "|" & (item 2 of winPos) & "|" & (item 1 of winSize) & "|" & (item 2 of winSize)
                    end repeat
                end repeat
                return windowList
            end tell
            """

            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)

            if result.returncode == 0 and result.stdout.strip():
                # Parse the output: "title|x|y|width|height, title|x|y|width|height, ..."
                windows_str = result.stdout.strip()
                if windows_str:
                    window_entries = windows_str.split(", ")
                    window_id = 1000  # Fake window ID for AppleScript results

                    for entry in window_entries:
                        parts = entry.split("|")
                        if len(parts) >= 5:
                            title = parts[0].strip()
                            try:
                                x = int(float(parts[1]))
                                y = int(float(parts[2]))
                                width = int(float(parts[3]))
                                height = int(float(parts[4]))
                            except (ValueError, IndexError):
                                continue

                            # Skip lobby (no table name suffix)
                            if title and title != "Winamax":
                                geometry = TableGeometry(x=x, y=y, width=width, height=height)
                                table_info = TableInfo(
                                    window_id=window_id,
                                    title=title,
                                    geometry=geometry,
                                    process_name="Winamax",
                                    process_id=0,
                                )
                                tables.append(table_info)
                                window_id += 1

            logger.debug(f"AppleScript found {len(tables)} Winamax tables")

        except subprocess.TimeoutExpired:
            logger.warning("AppleScript timed out getting Winamax windows")
        except Exception as e:
            logger.error(f"Error getting Winamax windows via AppleScript: {e}")

        return tables

    def focus_window(self, window_id: int | str) -> bool:
        """Bring window to foreground

        Args:
            window_id: Window number

        Returns:
            True if successful
        """
        try:
            # Note: Focusing specific windows on macOS is more complex
            # This is a simplified implementation
            logger.warning("Window focusing on macOS has limited support")
            return False

        except Exception as e:
            logger.error(f"Error focusing window {window_id}: {e}")
            return False

    def resize_window(self, window_id: int | str, x: int, y: int, width: int, height: int) -> bool:
        """Resize and reposition window

        Args:
            window_id: Window number
            x: New X coordinate
            y: New Y coordinate
            width: New width
            height: New height

        Returns:
            True if successful
        """
        try:
            # Note: Resizing windows on macOS requires accessibility permissions
            # This is a placeholder - full implementation would use AXUIElement
            logger.warning("Window resizing on macOS requires accessibility permissions")
            return False

        except Exception as e:
            logger.error(f"Error resizing window {window_id}: {e}")
            return False
