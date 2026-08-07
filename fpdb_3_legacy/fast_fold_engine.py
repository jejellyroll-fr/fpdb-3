"""Fast-Fold (Winamax Go Fast / Hold-Up) real-time HUD engine.

Provides fast seat-to-player stat fetching and HUD overlay updates when Hero
folds or moves to a new table pool.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

FAST_FOLD_TITLE_PATTERNS = (
    re.compile(r"Go\s*Fast", re.IGNORECASE),
    re.compile(r"HOLD-?UP", re.IGNORECASE),
    re.compile(r"Zoom", re.IGNORECASE),
    re.compile(r"Rush", re.IGNORECASE),
)


def is_fast_fold_table(table_title: str | None = None, game_type: str = "") -> bool:
    """Return True if the table window or game type belongs to a Fast-Fold pool."""
    if "fast" in (game_type or "").lower() or "zoom" in (game_type or "").lower():
        return True
    if not table_title:
        return False
    return any(pattern.search(table_title) for pattern in FAST_FOLD_TITLE_PATTERNS)


class FastFoldEngine:
    """Engine managing real-time opponent seat mapping and stat updates for Fast-Fold pools."""

    def __init__(self, config: Any = None, db_connection: Any = None) -> None:
        self.config = config
        self.db_connection = db_connection

    def get_player_stats_for_seat_map(
        self,
        seat_player_map: dict[int, str],
        game_type: str = "ring",
        db_conn: Any = None,
    ) -> dict[int, dict[str, Any]]:
        """Fetch historical stats for a map of {seat_number: player_name} from database.

        Returns a stat_dict mapping player_id (or synthetic seat id) to player HUD stats.
        """
        conn = db_conn or self.db_connection
        stat_dict: dict[int, dict[str, Any]] = {}

        for seat, player_name in seat_player_map.items():
            if not player_name:
                continue

            player_id: int | None = None
            stats: dict[str, Any] = {}

            if conn is not None:
                try:
                    if hasattr(conn, "get_player_id_by_name"):
                        player_id = conn.get_player_id_by_name(player_name)

                    if hasattr(conn, "get_player_stats_by_name"):
                        stats = conn.get_player_stats_by_name(player_name, game_type=game_type) or {}
                except Exception:
                    log.exception("Error fetching stats for Fast-Fold player %s:", player_name)

            pid = player_id if player_id is not None else (1000 + seat)
            player_data: dict[str, Any] = {
                "seat": seat,
                "screen_name": player_name,
                "player_id": pid,
                "n": stats.get("n", 0),
                "vpip": stats.get("vpip", 0.0),
                "pfr": stats.get("pfr", 0.0),
                "three_B": stats.get("three_B", 0.0),
                "f_3bet": stats.get("f_3bet", 0.0),
                "cb1": stats.get("cb1", 0.0),
                "f_cb1": stats.get("f_cb1", 0.0),
                "wtsd": stats.get("wtsd", 0.0),
                "profit100": stats.get("profit100", 0.0),
            }
            player_data.update(stats)
            stat_dict[pid] = player_data

        return stat_dict

    def update_hud_seats(
        self,
        hud: Any,
        seat_player_map: dict[int, str],
        game_type: str = "ring",
        db_conn: Any = None,
    ) -> bool:
        """Update a live HUD instance with new Fast-Fold seat assignments."""
        if hud is None:
            return False

        stat_dict = self.get_player_stats_for_seat_map(seat_player_map, game_type=game_type, db_conn=db_conn)
        hud.stat_dict = stat_dict

        if hasattr(hud, "update_hud"):
            try:
                hud.update_hud(stat_dict)
            except Exception:
                log.exception("Error re-rendering HUD stats for Fast-Fold seat update:")

        return True
