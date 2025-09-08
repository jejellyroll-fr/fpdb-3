#!/usr/bin/env python3
"""Smart HUD Manager to prevent unnecessary HUD restarts.

This module provides intelligent decision-making for HUD restarts,
distinguishing between cases that truly require a restart and those
that can be handled with simple updates.
"""

import time
from dataclasses import dataclass
from enum import Enum

from loggingFpdb import get_logger

log = get_logger("smart_hud_manager")


class RestartReason(Enum):
    """Reasons for HUD restart."""

    TABLE_CLOSED = "table_closed"
    GAME_TYPE_CHANGE = "game_type_change"
    MAX_SEATS_CHANGE = "max_seats_change"
    SITE_CHANGE = "site_change"
    CONFIGURATION_CHANGE = "configuration_change"
    ERROR_RECOVERY = "error_recovery"


@dataclass
class TableState:
    """Current state of a poker table."""

    table_key: str
    poker_game: str
    game_type: str
    max_seats: int
    site_name: str
    table_title: str
    last_update: float
    error_count: int = 0
    restart_count: int = 0


class SmartHudManager:
    """Intelligent HUD restart manager."""

    def __init__(self) -> None:
        """Initialize the smart HUD manager."""
        self.table_states: dict[str, TableState] = {}
        self.restart_cooldown = 30  # Seconds between allowed restarts
        self.max_error_count = 5  # Max errors before forced restart
        self.table_title_changes: dict[str, str] = {}  # Track title changes

        # Settings that require restart vs those that don't
        self.restart_required_changes = {
            "poker_game",
            "game_type",
            "max_seats",
            "site_name",
        }

        self.update_only_changes = {
            "hud_params",
            "stat_dict",
            "cards",
            "positions",
        }

    def should_restart_hud(
        self,
        table_key: str,
        reason: RestartReason,
        current_state: dict | None = None,
        new_state: dict | None = None,
    ) -> tuple[bool, str]:
        """Determine if HUD should be restarted.

        Args:
            table_key: Unique table identifier
            reason: Reason for potential restart
            current_state: Current table state
            new_state: New table state

        Returns:
            Tuple of (should_restart, explanation)
        """
        current_time = time.time()

        # Always restart for table closure
        if reason == RestartReason.TABLE_CLOSED:
            self._cleanup_table_state(table_key)
            return True, "Table closed"

        # Check if table is in cooldown period
        if table_key in self.table_states:
            last_restart = self.table_states[table_key].last_update
            if current_time - last_restart < self.restart_cooldown:
                return False, f"Restart cooldown active ({self.restart_cooldown}s)"

        # Handle different restart reasons
        if reason == RestartReason.ERROR_RECOVERY:
            return self._should_restart_for_error(table_key)

        if reason == RestartReason.GAME_TYPE_CHANGE:
            return self._should_restart_for_game_change(table_key, current_state, new_state)

        if reason == RestartReason.MAX_SEATS_CHANGE:
            return self._should_restart_for_seats_change(table_key, current_state, new_state)

        if reason == RestartReason.CONFIGURATION_CHANGE:
            return self._should_restart_for_config_change()

        return False, "No restart needed"

    def _should_restart_for_error(self, table_key: str) -> tuple[bool, str]:
        """Check if restart is needed for error recovery."""
        if table_key not in self.table_states:
            return True, "No table state found, restart needed"

        state = self.table_states[table_key]

        # Increment error count first
        state.error_count += 1

        # Check if we've exceeded the threshold
        if state.error_count >= self.max_error_count:
            log.warning(f"Too many errors ({state.error_count}) for table {table_key}, forcing restart")
            return True, f"Error count exceeded threshold ({self.max_error_count})"

        return False, f"Error recorded ({state.error_count}/{self.max_error_count}), no restart yet"

    def _should_restart_for_game_change(
        self,
        table_key: str,
        current_state: dict | None,
        new_state: dict | None,
    ) -> tuple[bool, str]:
        """Check if restart is needed for game type change."""
        if not current_state or not new_state:
            return True, "Missing state information"

        current_game = current_state.get("poker_game", "")
        new_game = new_state.get("poker_game", "")

        if current_game != new_game:
            log.info(f"Game type change detected for {table_key}: {current_game} -> {new_game}")
            return True, f"Game changed from {current_game} to {new_game}"

        return False, "No game type change"

    def _should_restart_for_seats_change(
        self,
        table_key: str,
        current_state: dict | None,
        new_state: dict | None,
    ) -> tuple[bool, str]:
        """Check if restart is needed for max seats change."""
        if not current_state or not new_state:
            return True, "Missing state information"

        current_seats = current_state.get("max_seats", 0)
        new_seats = new_state.get("max_seats", 0)

        if current_seats != new_seats:
            # Only restart if the change is significant (not just a minor adjustment)
            seat_difference = abs(current_seats - new_seats)
            if seat_difference > 2:  # Significant change
                log.info(f"Significant seat change for {table_key}: {current_seats} -> {new_seats}")
                return True, f"Seats changed significantly: {current_seats} -> {new_seats}"
            log.debug(f"Minor seat change for {table_key}: {current_seats} -> {new_seats}, no restart")
            return False, f"Minor seat change ({current_seats} -> {new_seats})"

        return False, "No seats change"

    def _should_restart_for_config_change(self) -> tuple[bool, str]:
        """Check if restart is needed for configuration change."""
        # For now, be conservative with config changes
        # In the future, this could analyze which specific config changed
        return False, "Configuration changes handled dynamically"

    def update_table_state(
        self,
        table_key: str,
        poker_game: str,
        game_type: str,
        max_seats: int,
        site_name: str,
        table_title: str = "",
    ) -> None:
        """Update stored table state.

        Args:
            table_key: Unique table identifier
            poker_game: Poker game type
            game_type: Game category (ring/tour)
            max_seats: Maximum seats at table
            site_name: Poker site name
            table_title: Table window title
        """
        current_time = time.time()

        if table_key in self.table_states:
            state = self.table_states[table_key]
            state.poker_game = poker_game
            state.game_type = game_type
            state.max_seats = max_seats
            state.site_name = site_name
            state.table_title = table_title
            state.last_update = current_time
            # Reset error count on successful update
            state.error_count = 0
        else:
            self.table_states[table_key] = TableState(
                table_key=table_key,
                poker_game=poker_game,
                game_type=game_type,
                max_seats=max_seats,
                site_name=site_name,
                table_title=table_title,
                last_update=current_time,
            )

    def record_restart(self, table_key: str, reason: str) -> None:
        """Record that a HUD restart occurred.

        Args:
            table_key: Unique table identifier
            reason: Reason for restart
        """
        if table_key in self.table_states:
            self.table_states[table_key].restart_count += 1
            self.table_states[table_key].last_update = time.time()
            log.info(
                f"HUD restart recorded for {table_key}: {reason} (restart #{self.table_states[table_key].restart_count})"
            )

    def _cleanup_table_state(self, table_key: str) -> None:
        """Clean up state for closed table."""
        if table_key in self.table_states:
            del self.table_states[table_key]
            log.debug(f"Cleaned up state for table {table_key}")

    def has_table_title_changed(self, table_key: str, new_title: str) -> bool:
        """Check if table title has significantly changed.

        Args:
            table_key: Unique table identifier
            new_title: New table title

        Returns:
            True if title change indicates table change
        """
        if table_key not in self.table_title_changes:
            self.table_title_changes[table_key] = new_title
            return False

        old_title = self.table_title_changes[table_key]

        # Simple heuristic: if core parts of title changed, it's a different table
        # Remove common dynamic parts (like blinds, player counts)
        def normalize_title(title: str) -> str:
            # Remove numbers that commonly change (blinds, player counts, etc.)
            import re

            normalized = re.sub(r"\d+/\d+", "", title)  # Remove blinds
            normalized = re.sub(r"\(\d+\s+players?\)", "", normalized)  # Remove player counts like "(6 players)"
            normalized = re.sub(r"\(\d+\)", "", normalized)  # Remove simple numbers in parentheses
            return normalized.strip().lower()

        old_normalized = normalize_title(old_title)
        new_normalized = normalize_title(new_title)

        if old_normalized != new_normalized:
            log.info(f"Significant title change for {table_key}: '{old_title}' -> '{new_title}'")
            self.table_title_changes[table_key] = new_title
            return True

        return False

    def get_restart_statistics(self) -> dict[str, dict]:
        """Get restart statistics for all tables."""
        stats = {}
        for table_key, state in self.table_states.items():
            stats[table_key] = {
                "restart_count": state.restart_count,
                "error_count": state.error_count,
                "last_update": state.last_update,
                "uptime": time.time() - state.last_update,
            }
        return stats


# Global instance for easy usage
_smart_hud_manager_instance = None


def get_smart_hud_manager() -> SmartHudManager:
    """Return global instance of smart HUD manager."""
    global _smart_hud_manager_instance
    if _smart_hud_manager_instance is None:
        _smart_hud_manager_instance = SmartHudManager()
    return _smart_hud_manager_instance
