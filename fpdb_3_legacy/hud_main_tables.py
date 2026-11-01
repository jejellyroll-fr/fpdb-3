"""Table window lifecycle: found, moved, resized, renamed, closed and stale tables.

One of the mixins HudMain (HUD_main.pyw) is built from. What it calls on the
other mixins is declared, for the type checker, on HudMainBase in hud_main_base.
"""

import contextlib
import os
import re
from typing import Any

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QWidget

from fpdb_3_legacy import Aux_Base, Hud
from fpdb_3_legacy.hud_diagnostics import session_id
from fpdb_3_legacy.hud_main_base import HudMainBase, log
from fpdb_3_legacy.SmartHudManager import RestartReason


class HudMainTablesMixin(HudMainBase):
    """Follow the table windows a HUD is attached to."""

    def _cleanup_closed_windows(self) -> None:
        """Close HUD overlays for Winamax table windows that have closed at session end."""
        import platform
        if platform.system() != "Windows":
            return
        import ctypes
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return
        is_window = windll.user32.IsWindow
        to_remove = []
        for temp_key, hud in list(self.hud_dict.items()):
            if not getattr(hud, "is_fast_fold", False):
                continue
            m = re.search(r"#(\d+)$", temp_key)
            if m:
                hwnd = int(m.group(1))
                if not is_window(hwnd):
                    to_remove.append((temp_key, hud))
        for temp_key, hud in to_remove:
            log.info("Closing Fast-Fold HUD for closed window: %s", temp_key)
            self._clear_fast_fold_table(temp_key, hud, "session-end", "window closed")
            close_hud = getattr(hud, "close", getattr(hud, "kill", None))
            if callable(close_hud):
                with contextlib.suppress(Exception):
                    close_hud()
            self.hud_dict.pop(temp_key, None)
            # This path bypasses idle_kill, so the window it held has to be
            # given back explicitly or the next HUD on it reads as a duplicate.
            self._forget_window_seat_state(temp_key, getattr(getattr(hud, "table", None), "number", None))
            self._window_registry.release(temp_key)
            aliases = getattr(self, "_fast_fold_aliases", None)
            if aliases is not None:
                for alias, live_key in list(aliases.items()):
                    if live_key == temp_key:
                        aliases.pop(alias, None)

    def _handle_table_status(self, hud: Hud.Hud) -> None:
        """Handle status changes for a single table."""
        table = getattr(hud, "table", None)
        if table is None:
            # Preview and lightweight test HUDs can intentionally omit the
            # live table object. They must not break the shared status timer.
            return
        status = table.check_table()
        if status == "client_destroyed":
            self.client_destroyed(None, hud)
        elif status == "client_moved":
            self.client_moved(None, hud)
        elif status == "client_resized":
            self.client_resized(None, hud)
        elif getattr(table, "type", "") == "tour":
            self._handle_tour_table_switch(hud, table)

    def _log_table_not_found(
        self,
        temp_key: str,
        table_name: str,
        db_site: str,
        hud_site: str,
        tablewindow: Any,
    ) -> None:
        """Report a table whose window could not be found, at the right volume.

        A hand reaches the HUD 15 to 30 seconds after it was played, so the last
        hands of a table that has just been closed -- and every hand of a Sit'n'Go
        whose file the client only writes once the match is over -- routinely
        arrive with no window left to attach to. Logged as errors, and once per
        hand, they buried the case that is a real failure: a table that is open
        on screen and never gets a HUD. That one still logs an error, once, with
        the search string it failed on, which is the part that identifies why.
        """
        if temp_key in self._tables_attached:
            report = log.info  # window was found before: the table has since closed
        elif temp_key in self._tables_not_found:
            report = log.debug  # already reported once for this table
        else:
            report = log.error
        self._tables_not_found.add(temp_key)
        report(
            "HUD create: table name %s not found for db_site=%s hud_site=%s (searched %r), skipping.",
            table_name,
            db_site,
            hud_site,
            getattr(tablewindow, "search_string", ""),
        )

    def _handle_tour_table_switch(self, hud: Hud.Hud, table: Any) -> None:
        """Kill a tournament HUD whose window has moved on to another table.

        check_table() only watches geometry, so a window that keeps its size and
        position while its title changes table went unnoticed until a hand of the
        new table was imported -- 15 to 30 seconds later on a Twister, where the
        client reuses the same window for the next match of the series. Until
        then the finished tournament's HUD sat on the new table showing the
        previous opponents. Killing it here means the worst case is no HUD for a
        few seconds instead of a wrong one.
        """
        try:
            seen = table.get_table_no()
        except Exception:
            log.debug("Table title check failed for %r", getattr(table, "key", "?"), exc_info=True)
            return
        if seen is False:
            return
        # The number the title carried when the HUD attached is the baseline, so
        # a site whose title never shows the table id simply never signals here
        # instead of the HUD being killed on a mismatch it cannot control.
        baseline = getattr(table, "title_table_no", None)
        if baseline is None:
            table.title_table_no = seen
            return
        if seen != baseline:
            log.warning(
                "HUD dropped: window %s left table %s (title now shows table %s, was %s)",
                table.number,
                table.key,
                seen,
                baseline,
            )
            self.table_is_stale(hud)

    def _topify_mac_windows(self) -> None:
        """Bring all HUD windows to the top on macOS."""
        if self.config.os_family == "Mac":
            for hud in self.hud_dict.values():
                for aw in hud.aux_windows:
                    if not hasattr(aw, "m_windows"):
                        continue
                    for w in aw.m_windows.values():
                        if w.isVisible():
                            hud.table.topify(w)

    def check_tables(self) -> None:
        """Periodically check the status of poker tables."""
        # Skip while a HUD window is being dragged: the geometry poll (an
        # expensive AppleScript scan on macOS) and the window re-raise (topify)
        # both run on the UI thread and re-order the dragged window, which makes
        # the drag stutter. Table geometry changes are picked up on the next tick.
        if Aux_Base.is_drag_active():
            return
        # Checked here rather than on a timer of its own: it is one os.stat
        # unless the file really changed, and skipping it during a drag also
        # keeps the HUD's own layout writes from rebuilding what is being
        # dragged.
        self.refresh_profiles_from_config()
        if not self.hud_dict:
            # log.info("Waiting for hands ...")
            pass
        for hud in list(self.hud_dict.values()):
            self._handle_table_status(hud)
        self._topify_mac_windows()

    def client_moved(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the client moved event."""
        log.debug("Client moved event")
        self.idle_move(hud)

    def client_resized(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the client resized event."""
        log.debug("Client resized event")
        self.idle_resize(hud)

    def client_destroyed(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the client destroyed event."""
        log.debug("Client destroyed event")
        self.clear_table_stat_set_override(hud.table.key)
        self.kill_hud(None, hud.table.key)

    def table_title_changed(self, _widget: QWidget | None, hud: Hud.Hud) -> None:
        """Handle the table title changed event."""
        table_key = hud.table.key
        new_title = getattr(hud.table, "title", "")

        # Use smart manager to determine if title change is significant
        if self.smart_hud_manager.has_table_title_changed(table_key, new_title):
            should_restart, reason = self.smart_hud_manager.should_restart_hud(
                table_key,
                RestartReason.TABLE_CLOSED,
            )

            if should_restart:
                log.info(f"Table title changed significantly, restarting HUD: {reason}")
                self.smart_hud_manager.record_restart(table_key, f"Title change: {reason}")
                self.kill_hud(None, table_key)
            else:
                log.debug(f"Table title changed but restart not needed: {reason}")
        else:
            log.debug("Table title change detected but not significant enough for restart")

    def table_is_stale(self, hud: Hud.Hud) -> None:
        """Handle a stale table by killing the HUD."""
        log.debug("Moved to a new table, killing current HUD")
        self.clear_table_stat_set_override(hud.table.key)
        self.kill_hud(None, hud.table.key)

    def kill_hud(self, _event: QEvent | None, table: str) -> None:
        """Kill the HUD for a specific table."""
        log.debug("kill_hud event")
        self.idle_kill(table)

    def blacklist_hud(self, _event: QEvent | None, table: str) -> None:
        """Blacklist a HUD and kill it."""
        log.debug("blacklist_hud event")
        self.blacklist.append(self.hud_dict[table].tablenumber)
        self.clear_table_stat_set_override(table)
        self.idle_kill(table)

    def _get_temp_key(self, game_type: str, tour_number: str, tab_number: str, table_name: str) -> str:
        """Generate a temporary key for the table."""
        if game_type != "tour":
            return table_name
        try:
            log.debug("creating temp_key for tour")
            tab_number_suffix = tab_number.rsplit(" ", 1)[-1]
        except ValueError:
            log.exception("Both tab_number and table_name not working")
            return table_name
        else:
            return f"{tour_number} Table {tab_number_suffix}"

    def _handle_tournament_table_changes(self, game_type: str, temp_key: str, tour_number: str) -> bool:
        """Handle table changes in tournaments. Returns True if stale."""
        if game_type != "tour":
            return False

        if temp_key in self.hud_dict:
            if self.hud_dict[temp_key].table.has_table_title_changed(self.hud_dict[temp_key]):
                log.debug("table has been renamed")
                self.table_is_stale(self.hud_dict[temp_key])
                return True
        else:
            for k in list(self.hud_dict.keys()):
                # The key of a tournament HUD is "<tournament> Table <n>", so
                # the tournament is compared whole. A prefix match made
                # tournament 116 the same as 1160391.
                if k.split(" Table ", 1)[0] == tour_number:
                    log.debug("check if the tournament number is in the hud_dict under a different table")
                    self.table_is_stale(self.hud_dict[k])
                    # continue checking other tables
        return False

    def idle_move(self, hud: Hud.Hud) -> None:
        """Handle the idle move event."""
        try:
            # Real geometry change: bump the generation so block windows re-place.
            hud.geometry_generation += 1
            hud.move_table_position()
            self._position_loading_indicator(hud)
            for aw in hud.aux_windows:
                aw.move_windows()
        except Exception:
            log.exception("Error moving HUD for table: %s.", hud.table.title)

    def idle_resize(self, hud: Hud.Hud) -> None:
        """Handle the idle resize event."""
        try:
            # Real geometry change: bump the generation so block windows re-place.
            hud.geometry_generation += 1
            hud.resize_windows()
            self._position_loading_indicator(hud)
            for aw in hud.aux_windows:
                aw.resize_windows()
        except Exception:
            log.exception("Error resizing HUD for table: %s.", hud.table.title)

    def idle_kill(self, table: str) -> None:
        """Handle the idle kill event."""
        try:
            if table in self.hud_dict:
                # Save HUD stats before killing to prevent data loss
                hud = self.hud_dict[table]
                if not getattr(hud, "is_loading", False):
                    hud_data = {
                        "stat_dict": getattr(hud, "stat_dict", {}),
                        "cards": getattr(hud, "cards", {}),
                        "poker_game": getattr(hud, "poker_game", ""),
                        "game_type": getattr(hud, "game_type", ""),
                        "max_seats": getattr(hud, "max", 0),
                        "hud_params": getattr(hud, "hud_params", {}),
                        "last_hand_id": getattr(hud, "last_hand_id", ""),
                    }

                    if self.stats_persistence.save_hud_stats(table, hud_data):
                        log.info(f"HUD stats saved before restart for table: {table}")
                    else:
                        log.warning(f"Failed to save HUD stats for table: {table}")

                # Take the label out of the main window and destroy it. setParent(None)
                # only detached it, which turns a QLabel into a top-level widget --
                # its own window, captioned with its text ("SealsWithClubs - <tourney>
                # Table 3"). Killing a HUD must leave nothing of it behind: in a
                # tournament the hero is moved from table to table, and each move left
                # one more of these behind.
                label = self.hud_dict[table].tablehudlabel
                self.vb.removeWidget(label)
                label.hide()
                label.deleteLater()
                self.hud_dict[table].tablehudlabel = None
                overlays = self._describe_overlay_win_ids(hud)
                self.hud_dict[table].kill()
                retiring_hwnd = getattr(getattr(hud, "table", None), "number", None)
                del self.hud_dict[table]
                self._forget_window_seat_state(table, retiring_hwnd)
                released = self._window_registry.release(table)
                log.debug(
                    "HUD destroyed: session=%s pid=%s generation=%s table=%r window_id=%s overlays=%s",
                    session_id(),
                    os.getpid(),
                    None if released is None else released.generation,
                    table,
                    None if released is None else released.window_id,
                    overlays,
                )
            self.main_window.resize(1, 1)
        except Exception:
            log.exception("Error killing HUD for table: %s.", table)
