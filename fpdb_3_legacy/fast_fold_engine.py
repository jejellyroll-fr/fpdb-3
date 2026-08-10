"""Fast-Fold (Winamax Go Fast / Hold-Up) real-time HUD engine.

Provides fast seat-to-player stat fetching and HUD overlay updates when Hero
folds or moves to a new table pool.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FastFoldStatsRequest:
    """Ask the database worker for stats on the players now sitting at a table.

    The GUI thread cannot read them itself -- its ``db_connection`` is the
    database-free replay facade -- so the seat map makes the round trip and
    comes back with the stats attached.
    """

    temp_key: str
    """hud_dict key of the table the seats belong to."""

    seat_map: dict[int, str] = field(default_factory=dict)
    """``{seat_number: login}``, already anchored on the hero."""

    hand_id: Any = None
    """Any hand imported for this table, used to resolve its gametypeId."""

    num_seats: int = 6


@dataclass(frozen=True)
class FastFoldStatsResult:
    """A completed :class:`FastFoldStatsRequest`, safe for the GUI thread."""

    temp_key: str
    seat_map: dict[int, str] = field(default_factory=dict)
    stat_dict: dict[int, dict[str, Any]] = field(default_factory=dict)

FAST_FOLD_TITLE_PATTERNS = (
    re.compile(r"Go\s*Fast", re.IGNORECASE),
    re.compile(r"HOLD-?UP", re.IGNORECASE),
    re.compile(r"Escape", re.IGNORECASE),
    re.compile(r"Splash", re.IGNORECASE),
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


def build_seat_map(
    ring: list[str],
    hero: str | None,
    max_seats: int,
    hero_seat: int = 3,
) -> dict[int, str]:
    """Turn a clockwise ring of logins into ``{seat_number: login}``.

    ``ring`` is ordered clockwise from the small blind (see
    :mod:`fpdb_3_legacy.winamax_live_log_reader`), which is an order, not a set
    of seats -- its starting point moves with the button every hand. Seats are
    therefore assigned relative to ``hero``, who is pinned to ``hero_seat`` and
    the rest laid out clockwise from there.

    Pinning the hero matters: ``Aux_Base.adj_seats`` computes the rotation that
    puts the hero at the bottom of the screen once, when the HUD is created, and
    that rotation stays correct only if the hero's seat number never moves.
    Numbering from the small blind instead would renumber every player each hand.

    Returns an empty map when the hero is not in the ring yet, since without the
    anchor no placement can be trusted.
    """
    if not ring or not hero or hero not in ring or max_seats <= 0:
        return {}

    hero_idx = ring.index(hero)
    seat_map: dict[int, str] = {}
    for idx, login in enumerate(ring[:max_seats]):
        seat = ((idx - hero_idx + hero_seat - 1) % max_seats) + 1
        seat_map[seat] = login
    return seat_map


class FastFoldEngine:
    """Engine managing real-time opponent seat mapping and stat updates for Fast-Fold pools."""

    def __init__(self, config: Any = None, db_connection: Any = None) -> None:
        self.config = config
        self.db_connection = db_connection

    @staticmethod
    def _resolve_player_ids(conn: Any, names: Any) -> dict[str, int]:
        """Database ids for the given screen names; names unknown to it are dropped."""
        ids_by_name: dict[str, int] = {}
        if conn is None or not hasattr(conn, "get_player_id_by_name"):
            return ids_by_name
        for name in names:
            try:
                pid = conn.get_player_id_by_name(name)
            except Exception:
                log.exception("Error resolving Fast-Fold player %s:", name)
                continue
            if pid is not None:
                ids_by_name[name] = int(pid)
        return ids_by_name

    def get_player_stats_for_seat_map(
        self,
        seat_player_map: dict[int, str],
        game_type: str = "ring",
        db_conn: Any = None,
        gametype_id: Any = None,
        hud_params: dict[str, Any] | None = None,
        hero_id: int = -1,
        num_seats: int = 6,
    ) -> dict[int, dict[str, Any]]:
        """Build a HUD ``stat_dict`` for a map of ``{seat_number: player_name}``.

        The rows come from the same aggregate the HUD uses for an imported hand
        (``get_stats_for_players``), because the stat functions that render them
        expect its raw counter columns -- handing them ready-made percentages
        instead is what makes every stat display as "NA".

        Players with no rows yet still get a seat entry, so a new opponent shows
        up by name with empty stats rather than leaving a hole in the table.
        """
        conn = db_conn or self.db_connection
        seats_by_name = {name: seat for seat, name in seat_player_map.items() if name}
        if not seats_by_name:
            return {}

        ids_by_name = self._resolve_player_ids(conn, seats_by_name)

        stat_dict: dict[int, dict[str, Any]] = {}
        if ids_by_name and gametype_id is not None and hasattr(conn, "get_stats_for_players"):
            try:
                stat_dict = conn.get_stats_for_players(
                    list(ids_by_name.values()),
                    gametype_id,
                    hud_params=hud_params,
                    hero_id=hero_id,
                    num_seats=num_seats,
                )
            except Exception:
                log.exception("Error fetching Fast-Fold stats for %s:", list(ids_by_name))
                stat_dict = {}

        by_id = {pid: name for name, pid in ids_by_name.items()}
        for pid, row in stat_dict.items():
            name = row.get("screen_name") or by_id.get(pid, "")
            row["screen_name"] = name
            row["player_id"] = pid
            row["seat"] = seats_by_name.get(name, row.get("seat"))

        # Seats whose player the aggregate returned nothing for: unknown to the
        # database, or no hands at comparable stakes.
        placed = {row.get("screen_name") for row in stat_dict.values()}
        for name, seat in seats_by_name.items():
            if name in placed:
                continue
            pid = ids_by_name.get(name, 1000 + seat)
            stat_dict[pid] = {"seat": seat, "screen_name": name, "player_id": pid, "n": 0}

        return stat_dict

    def pin_hero_seat(self, hud: Any) -> int:
        """Return (and remember) the seat number this HUD assigns to the hero.

        FastFold table layouts always draw the hero at the bottom-center anchor
        slot (seat 3 on 6-max Winamax layouts). Forcing hero_seat to the layout
        anchor ensures live updates and log-ring fallbacks use the exact same seat
        anchor without rotating HUD blocks across hands.
        """
        anchor = self._anchor_slot(hud) or 3
        if hud is not None:
            hud.fast_fold_hero_seat = anchor
        return anchor

    @staticmethod
    def _anchor_slot(hud: Any) -> int | None:
        """The layout slot the hero's block is anchored to, if the aux windows know."""
        for aux in getattr(hud, "aux_windows", None) or []:
            anchor = getattr(aux, "_anchor_slot", None)
            if callable(anchor):
                try:
                    return int(anchor())
                except Exception:
                    log.debug("Could not read hero anchor slot from %r", aux, exc_info=True)
        return None

    def update_hud_seats(
        self,
        hud: Any,
        seat_player_map: dict[int, str],
        game_type: str = "ring",
        db_conn: Any = None,
        gametype_id: Any = None,
        hud_params: dict[str, Any] | None = None,
        hero_id: int = -1,
    ) -> bool:
        """Read stats and apply them. Needs a real connection, so not for the GUI thread."""
        if hud is None or not seat_player_map:
            return False

        stat_dict = self.get_player_stats_for_seat_map(
            seat_player_map,
            game_type=game_type,
            db_conn=db_conn,
            gametype_id=gametype_id,
            hud_params=hud_params,
            hero_id=hero_id,
            num_seats=getattr(hud, "max", 6) or 6,
        )
        return self.apply_seats(hud, seat_player_map, stat_dict)

    @staticmethod
    def clear_seats(hud: Any) -> None:
        """Empty a Fast-Fold HUD's seats and redraw it.

        Called when a new hand starts: the hero has been moved to a new table and
        the players on the overlay are no longer at it. Blank stats are honest;
        the previous table's numbers shown against these opponents are not.
        """
        if hud is None:
            return
        hud.stat_dict = {}
        hud.seat_players = {}
        hud.fast_fold_seats = {}
        hud.fast_fold_seat_players = {}
        for aux in getattr(hud, "aux_windows", None) or []:
            try:
                aux.refresh_stats(None)
            except Exception:
                log.exception("Error clearing aux window for Fast-Fold hand start:")

    @staticmethod
    def apply_seats(hud: Any, seat_player_map: dict[int, str], stat_dict: dict[int, dict[str, Any]]) -> bool:
        """Put an already-read stat_dict on a HUD and redraw it.

        Split from the reading so the GUI thread only ever does this half: the
        HUD's ``db_connection`` is a database-free replay facade, and the stats
        have to come from the worker that owns the real one.
        """
        if hud is None or not seat_player_map or not stat_dict:
            return False

        seat_players: dict[int, dict[str, Any]] = {}
        for pid, pdata in stat_dict.items():
            seat = pdata.get("seat")
            if seat is not None:
                seat_players[int(seat)] = {
                    "player_id": pid,
                    "screen_name": pdata.get("screen_name"),
                    "seat": int(seat),
                }

        hud.stat_dict = stat_dict
        hud.seat_players = seat_players
        # Kept so a background import of an already-finished hand can restore the
        # live table instead of overwriting it with the old one's players.
        hud.fast_fold_seats = dict(seat_player_map)
        hud.fast_fold_seat_players = seat_players

        if getattr(hud, "is_loading", False):
            # The placeholder HUD has no seat windows to redraw yet; the seats
            # are on it and will be drawn when a hand replaces it with a real one.
            return True

        # refresh_stats redraws the seat windows straight from hud.stat_dict and
        # ignores the hand id, which is what a live update needs -- update_data
        # would go back to the database for a hand that has not been imported yet.
        for aux in getattr(hud, "aux_windows", None) or []:
            try:
                aux.refresh_stats(None)
            except Exception:
                log.exception("Error refreshing aux window for Fast-Fold seat update:")

        return True
