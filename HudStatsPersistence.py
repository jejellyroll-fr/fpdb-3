"""HUD Statistics Persistence Manager to prevent data loss during restarts.

This module provides a temporary persistence layer for HUD statistics,
allowing accumulated data to be preserved during unexpected restarts.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

from loggingFpdb import get_logger

log = get_logger("hud_stats_persistence")


class HudStatsPersistence:
    """HUD statistics persistence manager."""

    def __init__(self, config_dir: str | None = None) -> None:
        """Initialize the persistence manager.

        Args:
            config_dir: Configuration directory, defaults to ~/.fpdb
        """
        if config_dir is None:
            config_dir = os.path.expanduser("~/.fpdb")

        self.persistence_dir = Path(config_dir) / "hud_stats_cache"
        self.persistence_dir.mkdir(parents=True, exist_ok=True)

        # TTL for cached statistics (30 minutes)
        self.stats_ttl = 30 * 60

        log.info(f"HUD Stats Persistence initialized at {self.persistence_dir}")

    def _get_cache_file_path(self, table_key: str) -> Path:
        """Generate cache file path for a table."""
        safe_key = "".join(c for c in table_key if c.isalnum() or c in "._-")
        return self.persistence_dir / f"{safe_key}.json"

    def save_hud_stats(self, table_key: str, hud_data: dict[str, Any]) -> bool:
        """Save HUD statistics for a table.

        Args:
            table_key: Unique table identifier
            hud_data: HUD data to save

        Returns:
            True if save succeeded, False otherwise
        """
        try:
            cache_file = self._get_cache_file_path(table_key)

            # Prepare data with metadata
            cache_data = {
                "table_key": table_key,
                "timestamp": time.time(),
                "stat_dict": hud_data.get("stat_dict", {}),
                "cards": hud_data.get("cards", {}),
                "poker_game": hud_data.get("poker_game", ""),
                "game_type": hud_data.get("game_type", ""),
                "max_seats": hud_data.get("max_seats", 0),
                "hud_params": hud_data.get("hud_params", {}),
                "last_hand_id": hud_data.get("last_hand_id", ""),
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, default=str)

            log.debug(f"HUD stats saved for table {table_key}")
            return True

        except Exception as e:
            log.exception(f"Failed to save HUD stats for table {table_key}: {e}")
            return False

    def load_hud_stats(self, table_key: str) -> dict[str, Any] | None:
        """Load HUD statistics for a table.

        Args:
            table_key: Unique table identifier

        Returns:
            HUD data dictionary or None if not found/expired
        """
        try:
            cache_file = self._get_cache_file_path(table_key)

            if not cache_file.exists():
                log.debug(f"No cached stats found for table {table_key}")
                return None

            with open(cache_file, encoding="utf-8") as f:
                cache_data = json.load(f)

            # Check if data is not expired
            current_time = time.time()
            file_timestamp = cache_data.get("timestamp", 0)
            time_diff = current_time - file_timestamp

            log.debug(
                f"Checking expiration for {table_key}: current_time={current_time}, file_timestamp={file_timestamp}, time_diff={time_diff}, ttl={self.stats_ttl}"
            )

            # Special case: if TTL is 0, always consider expired (used by tests)
            if self.stats_ttl == 0 or time_diff >= self.stats_ttl:  # Use >= instead of > for edge cases
                log.debug(f"Cached stats expired for table {table_key} (time_diff={time_diff} >= ttl={self.stats_ttl})")
                # Try to remove the expired file, but return None regardless
                self.remove_hud_stats(table_key)
                # Double-check if file still exists (Windows filesystem issue)
                if cache_file.exists():
                    log.warning(f"File still exists after removal attempt on Windows: {cache_file}")
                    # Force removal with retry logic
                    import platform

                    if platform.system() == "Windows":
                        for i in range(3):  # Try up to 3 times
                            try:
                                cache_file.unlink(missing_ok=True)
                                time.sleep(0.01 * (i + 1))  # Progressive delay
                                if not cache_file.exists():
                                    break
                            except Exception as e:
                                log.warning(f"Retry {i+1} failed to remove {cache_file}: {e}")
                return None

            log.debug(f"HUD stats loaded for table {table_key}")
            # Return the HUD data without cache metadata (timestamp)
            hud_data = {
                "table_key": cache_data.get("table_key", table_key),
                "stat_dict": cache_data.get("stat_dict", {}),
                "cards": cache_data.get("cards", {}),
                "poker_game": cache_data.get("poker_game", ""),
                "game_type": cache_data.get("game_type", ""),
                "max_seats": cache_data.get("max_seats", 0),
                "hud_params": cache_data.get("hud_params", {}),
                "last_hand_id": cache_data.get("last_hand_id", ""),
            }
            return hud_data

        except Exception as e:
            log.exception(f"Failed to load HUD stats for table {table_key}: {e}")
            return None

    def remove_hud_stats(self, table_key: str) -> bool:
        """Remove cached HUD statistics for a table.

        Args:
            table_key: Unique table identifier

        Returns:
            True if removal succeeded, False otherwise
        """
        try:
            cache_file = self._get_cache_file_path(table_key)

            if cache_file.exists():
                cache_file.unlink()
                # On Windows, verify file is actually deleted
                import platform

                if platform.system() == "Windows":
                    # Small delay to ensure Windows filesystem operations complete
                    import time

                    time.sleep(0.01)
                    if cache_file.exists():
                        log.warning(f"File deletion delayed on Windows for {cache_file}")
                        return False
                log.debug(f"Cached stats removed for table {table_key}")

            return True

        except Exception as e:
            log.exception(f"Failed to remove HUD stats for table {table_key}: {e}")
            return False

    def cleanup_expired_stats(self) -> None:
        """Clean up expired statistics from cache."""
        try:
            current_time = time.time()
            removed_count = 0

            for cache_file in self.persistence_dir.glob("*.json"):
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        cache_data = json.load(f)

                    file_timestamp = cache_data.get("timestamp", 0)
                    time_diff = current_time - file_timestamp
                    log.debug(f"Cleanup check for {cache_file.name}: time_diff={time_diff}, ttl={self.stats_ttl}")

                    # Special case: if TTL is 0, always consider expired (used by tests)
                    if self.stats_ttl == 0 or time_diff >= self.stats_ttl:  # Use >= for consistency
                        # Enhanced Windows-compatible file removal
                        try:
                            cache_file.unlink(missing_ok=True)
                            removed_count += 1
                            # Verify removal on Windows
                            import platform

                            if platform.system() == "Windows" and cache_file.exists():
                                log.warning(f"File still exists after cleanup on Windows: {cache_file}")
                                # Force retry
                                for i in range(3):
                                    try:
                                        cache_file.unlink(missing_ok=True)
                                        time.sleep(0.01 * (i + 1))
                                        if not cache_file.exists():
                                            break
                                    except Exception as retry_e:
                                        log.warning(f"Cleanup retry {i+1} failed for {cache_file}: {retry_e}")
                        except Exception as unlink_e:
                            log.warning(f"Failed to remove expired file {cache_file}: {unlink_e}")

                except Exception as e:
                    log.warning(f"Failed to process cache file {cache_file}: {e}")
                    # Remove corrupted file with Windows handling
                    try:
                        cache_file.unlink(missing_ok=True)
                        removed_count += 1
                    except Exception as unlink_e:
                        log.warning(f"Failed to remove corrupted file {cache_file}: {unlink_e}")

            if removed_count > 0:
                log.info(f"Cleaned up {removed_count} expired HUD stats cache files")

        except Exception as e:
            log.exception(f"Failed to cleanup expired stats: {e}")

    def merge_stats(self, cached_stats: dict[str, Any], new_stats: dict[str, Any]) -> dict[str, Any]:
        """Merge cached statistics with new ones.

        Args:
            cached_stats: Cached statistics
            new_stats: New statistics

        Returns:
            Merged statistics
        """
        try:
            # Start with new stats as base
            merged = new_stats.copy()

            # Merge stat_dict while preserving historical data
            cached_stat_dict = cached_stats.get("stat_dict", {})
            new_stat_dict = new_stats.get("stat_dict", {})

            # For each player in cached stats
            for player_id, cached_player_stats in cached_stat_dict.items():
                if player_id in new_stat_dict:
                    # Player present in both: merge intelligently
                    merged_player_stats = new_stat_dict[player_id].copy()

                    # Preserve certain accumulated stats if they are more important
                    for stat_key, cached_value in cached_player_stats.items():
                        if stat_key not in merged_player_stats or merged_player_stats[stat_key] == 0:
                            merged_player_stats[stat_key] = cached_value

                    merged["stat_dict"][player_id] = merged_player_stats
                else:
                    # Player only in cache: preserve
                    if "stat_dict" not in merged:
                        merged["stat_dict"] = {}
                    merged["stat_dict"][player_id] = cached_player_stats

            log.debug("Successfully merged cached and new HUD stats")
            return merged

        except Exception as e:
            log.exception(f"Failed to merge stats: {e}")
            return new_stats  # Return new stats on error


# Global instance for easy usage
_persistence_instance = None


def get_hud_stats_persistence() -> HudStatsPersistence:
    """Return global instance of persistence manager."""
    global _persistence_instance
    if _persistence_instance is None:
        _persistence_instance = HudStatsPersistence()
    return _persistence_instance
