"""Shared ground of the HUD main mixins: the HUD's logger, constants and declared state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import ModuleType
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy import Configuration, Hud
from fpdb_3_legacy.hud_profiles import HudContext
from fpdb_3_legacy.hud_read_service import (
    HudReplayDatabase,
)
from fpdb_3_legacy.hud_window_registry import HudWindowRegistry
from fpdb_3_legacy.loggingFpdb import get_logger

if TYPE_CHECKING:
    from fpdb_3_legacy.hud_main_window import HudMainWindow
    from fpdb_3_legacy.hud_read_service import HudReplayDatabase
    from fpdb_3_legacy.hud_window_registry import HudWindowRegistry
    from fpdb_3_legacy.hud_workers import DbRecoveryWorker
    from fpdb_3_legacy.HudStatsPersistence import HudStatsPersistence
    from fpdb_3_legacy.SmartHudManager import SmartHudManager

# Logging configuration

# One logger object for HUD_main and every module split out of it, so that
# patching one of its methods reaches all of them.
log = get_logger("hud_main")

FAST_FOLD_POOL_PREFIX = "gf."
"""What the Winamax log calls a Fast-Fold pool, covering Escape and HOLD-UP."""


@dataclass
class HUDCreationArgs:
    """Arguments for creating a HUD."""

    new_hand_id: str
    table: Any
    temp_key: str
    max_seats: int
    poker_game: str
    game_type: str
    stat_dict: dict[str, Any]
    cards: dict[str, Any]
    context: HudContext | None = None
    hand_instance: Any = None
    loading: bool = False


@dataclass
class TableReadState:
    """What has been learned about reading one table's window.

    Three dictionaries held this, keyed by the table's name, each read and
    written in a different place and each forgotten -- or not -- on its own. The
    one that was not forgotten cost a restarted client its seats for a whole
    session: a pool hands the same name to the next table it opens, so a new HUD
    inherited "this client will not answer" from a client that had exited.

    One object with one lifetime. Created when a table is first read, dropped
    whole when it retires, so nothing can be left behind by being overlooked.
    """

    #: The hand the ring below was read for, the ring itself, and how many reads
    #: it took. Reset when the hand changes: the seats cannot change within one.
    hand_id: str | None = None
    ring: dict[int, str] = field(default_factory=dict)
    reads: int = 0

    #: Reads in a row that could not seat anyone -- not reads that came back
    #: empty. A client answering with the hero and one neighbour answers
    #: non-empty every time and can never be acted on.
    fruitless: int = 0

    #: Whether the reader has been given up on for this table.
    gave_up: bool = False

    def start_hand(self, hand_id: str) -> None:
        """Forget the previous hand's ring, keeping what was learned about the client."""
        if self.hand_id != hand_id:
            self.hand_id, self.ring, self.reads = hand_id, {}, 0



class HudMainBase:
    """The constants and state every HudMain mixin works on."""

    AX_READS_PER_HAND = 6

    #: Consecutive window reads that may fail to seat anyone before the reader
    #: is given up on for that table. Two hands' worth.
    #:
    #: It was five, and five is what the evidence costs rather than what it is
    #: worth: a read of a client that answers takes 94-218ms, synchronously, on
    #: the GUI thread, six times a hand, per table. Thirty of them is four and a
    #: half seconds of frozen HUD spent proving something a table caught
    #: mid-redraw proves in one hand -- and a client that does not publish its
    #: felt proves immediately. Two hands is still twice what it takes.
    AX_FRUITLESS_READS_BEFORE_GIVING_UP = AX_READS_PER_HAND * 2
    """How many times a table's window may be re-read within one hand.

    A read costs ~20ms through the macOS accessibility API and 100-300ms
    through Windows UIAutomation (measured on a Chromium window), and the seats
    settle within the first few log lines, so this bounds the cost while still
    letting a table that was read before it was drawn fill in. Reads stop as
    soon as the table looks full, so a full table costs one or two of them.
    """

    HERO_SLOT = 0
    """The bottom chair, which is where the client always draws the hero."""

    FF_IDLE_RECHECK_SECONDS = 20.0
    """Silence on a Fast-Fold table before its window is asked about directly.

    Long enough that a hand being tanked over is never mistaken for an empty
    table -- the log emits a line for every action, so a hand in progress
    refreshes this constantly -- and short enough that blocks do not sit over
    an abandoned felt for the minutes measured before the sweep existed.
    """

    FF_UNMAPPED_LOG_MEMORY = 500
    """Hands remembered as already reported missing from the log window map.

    Only large enough that the two snapshots of one hand fall inside it; the
    set is cleared wholesale past this, since an old hand can no longer be
    warned about twice.
    """

    MIN_PLAYERS_TO_SHOW = 2

    #: How long after asking for a table's statistics further ring growth is
    #: coalesced instead of asking again. The client log names players one at a
    #: time, so a six-handed table produced a request, a database round trip and
    #: a redraw per name -- fourteen in one hand, across two tables, in a
    #: measured session. The first answer is never delayed by this; only the
    #: ones chasing it are merged.
    FF_STATS_COALESCE_MS = 400
    """Players a window must be drawing before its blocks are worth showing.

    The hero alone means the table is between hands or waiting for players, and
    stat blocks over an empty felt describe nobody.
    """

    FAST_FOLD_MAX_SEATS = 6
    """Seats on a Winamax Escape / Go Fast table.

    The window says what is played and for how much, but not how many chairs it
    draws; the pools are 6-max. An imported hand corrects it if that changes.
    """

    AX_RECHECK_DELAYS_MS = (250, 700, 1500)

    #: Hands remembered as having a seat-wait recheck already scheduled. Bounded
    #: because a session plays thousands of them and nothing else prunes it.
    FF_SEAT_WAIT_MEMO_LIMIT = 200
    """When to look at the window again after a hand starts.

    Every log line of a new hand -- the hand id, both blinds, the hole cards --
    is written in the same millisecond, before the client has drawn the table,
    so re-reading on log lines alone would just repeat the same empty answer.
    """


    Tables: ModuleType
    _ax_reader_enabled: bool
    _config_fingerprint: tuple[float, int] | None
    _db_available: bool
    _db_backend: int
    _db_batch_inflight: bool
    _db_batch_sequence: int
    _db_consecutive_failures: int
    _db_progress_refreshed: set[str]
    _db_recovery_worker: DbRecoveryWorker | None
    _deferred_hands: list[str]
    _fast_fold_pending: dict[str, dict[int, str]]
    _fast_fold_seat_wait_ms: int
    _fast_fold_tables: set[str]
    _ff_coalesce_timers: dict[str, Any]
    _ff_coalesced: dict[str, tuple[Any, dict[int, str], Any]]
    _ff_last_activity: dict[str, float]
    _ff_last_request_at: dict[str, float]
    _ff_pending_generation: dict[str, int | None]
    _ff_pending_hand: dict[str, str]
    _ff_pending_request: dict[str, int]
    _ff_request_sequence: int
    _ff_seat_wait_scheduled: set[tuple[str, str]]
    _ff_started: dict[str, float]
    _ff_unmapped_logged: set[str]
    _hand_batch_timer: Any
    _hand_players: Any
    _hud_generation: int
    _import_request_sequence: int
    _last_applied_revision: int
    _last_applied_sequence: int
    _last_batch_queries: int
    _last_processed_hands: dict[str, str]
    _last_table_info: dict[str, tuple[Any, ...]]
    _pending_hands: list[str]
    _prepared_hands: dict[str, Any]
    _shutdown_started: bool
    _table_reads: dict[str, TableReadState]
    _table_stat_set_overrides: dict[str, tuple[str, str, str]]
    _tables_attached: set[str]
    _tables_not_found: set[str]
    _unpaired_pools: set[str]
    _winamax_pool_huds: dict[str, str]
    _winamax_regular_seen: dict[Any, tuple[Any, str]]
    _winamax_regular_unmatched: set[tuple[Any, str]]
    _winamax_site_id: Any
    _window_registry: HudWindowRegistry
    blacklist: list[Any]
    cache: Any
    config: Configuration.Config
    db_connection: HudReplayDatabase
    hero: dict[int, str]
    hero_ids: dict[int, int]
    hud_dict: dict[str, Hud.Hud]
    hud_params: Any
    main_window: HudMainWindow
    smart_hud_manager: SmartHudManager
    stats_persistence: HudStatsPersistence
    vb: Any

    if TYPE_CHECKING:
        winamax_table_update: Any
        # Methods one mixin calls on another. Declared as callables rather than
        # stub methods: pylint reads a stub's empty body as a method that
        # returns nothing, and flags every caller that uses the result.
        note_db_error: Callable[..., bool]
        _show_loading_hud: Callable[..., str | None]
        _resolve_fast_fold_key: Callable[..., str]
        _live_hud_key_for_table_no: Callable[..., str | None]
        destroy: Callable[..., None]
        _clear_fast_fold_table: Callable[..., None]
        _read_window_slots: Callable[..., dict[int, str] | None]
        _ff_trace: Callable[..., None]
        _request_fast_fold_stats_coalesced: Callable[..., None]
        _forget_window_seat_state: Callable[..., None]
        _has_live_seat_source: Callable[..., bool]
        _hud_is_fast_fold: Callable[..., bool]
        _find_fast_fold_hud: Callable[..., tuple[str, Hud.Hud] | None]
        _log_table_not_found: Callable[..., None]
        kill_hud: Callable[..., None]
        clear_table_stat_set_override: Callable[..., None]
        refresh_profiles_from_config: Callable[..., int]
        _describe_overlay_win_ids: Callable[..., str]
        _resolve_hud_config_site: Callable[..., str]
        _get_table_info: Callable[..., tuple | None]
        _get_temp_key: Callable[..., str]
        _handle_tournament_table_changes: Callable[..., bool]
        _seat_players: Callable[..., dict]
        _refresh_other_huds: Callable[..., None]
        _create_new_hud: Callable[..., None]
        read_stdin: Callable[..., str | None]
        _set_table_stats: Callable[..., None]
        _merge_positions: Callable[..., None]
        idle_kill: Callable[..., None]
        idle_create: Callable[..., None]
        _position_loading_indicator: Callable[..., None]
