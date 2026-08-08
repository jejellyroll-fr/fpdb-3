"""Real-time log reader for Winamax application log files.

Tails the active Winamax log (``~/Library/Application Support/winamax/logs/*.log``)
to recover, at hand start, who is sitting at a Fast-Fold / Escape table -- long
before the hand history for that hand is written and imported.

What the log actually provides
------------------------------
The client logs no seat numbers at all. The only per-table events are::

    [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 hand 22754010-6356-1786128858
    [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action SB login="<hero>"
    [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action BB login="<player2>"
    [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 cards login="<hero>" As,8h,3h,4c
    [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action fold login="<player3>"

So seats have to be inferred. Two properties make that possible:

* Blinds are posted in seat order and preflop action then proceeds clockwise
  from UTG, so the order in which logins first appear is the clockwise ring
  order starting at the small blind. Measured against 356 hands of real
  histories, that holds for 97.2% of hands.
* ``cards login=`` is emitted exactly once per hand (52 ``cards`` for 52
  ``hand`` events in the reference log) and only ever for the hero, which
  identifies the hero without any configuration.

The ring is emitted raw, paired with the hero. Turning it into seat numbers
needs the table size and is left to :mod:`fpdb_3_legacy.fast_fold_engine`.

Known limitation: Fast-Fold lets players pre-select an action, and a
pre-selected fold is logged when it is clicked rather than when the turn comes
round, which puts that player early in the ring. This affects ~3% of hands and
is self-correcting -- the next hand rebuilds the ring from scratch.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class WinamaxTableUpdate:
    """Live view of one Winamax table, as recovered from the application log."""

    pool: str
    """Pool/table identifier, e.g. ``gf.cgmatchmaker.gf_1.t22754010.0``. Unique per open table."""

    table_no: str
    """The ``[table] N`` index used by the client."""

    hand_id: str
    """Site hand id, e.g. ``22754010-6356-1786128858``. Matches ``HandId:`` in the hand history."""

    hero: str | None
    """Hero login, from ``cards login=``; ``None`` until the cards line is seen."""

    ring: list[str] = field(default_factory=list)
    """Logins in clockwise order starting at the small blind."""

    hero_left: bool = False
    """The hero has folded, so this table is over for them.

    On a Fast-Fold pool a fold is a departure: the client moves the hero to a
    new table at once, and these players stop being the ones in front of them.
    """

    hand_over: bool = False
    """The pot has been awarded, so nobody is at this table any more."""

    @property
    def finished(self) -> bool:
        """Whether there is no longer a table here worth describing."""
        return self.hero_left or self.hand_over

    logged_at_ms: int = 0
    """Client timestamp of the line that started the hand, in epoch milliseconds.

    Lets a consumer measure how far behind the log it is running, which is the
    difference between "the HUD is slow" and "the HUD is waiting for data".
    """

    @property
    def table_id(self) -> str:
        """Winamax table id shared by the pool and the hand id (``t22754010`` -> ``22754010``).

        Lets a pool be matched to an imported hand, and so to a HUD, without
        depending on window titles.
        """
        return self.hand_id.split("-")[0] if self.hand_id else ""


def fpdb_hand_id(site_hand_id: str) -> str | None:
    """The id fpdb stores for a Winamax hand the log calls ``22754010-6356-1786128858``.

    ``WinamaxToFpdb.readHandInfo`` keeps only the first two fields and joins
    them (``227540106356``), so a log id has to be put through the same rule
    before it can be matched against an imported hand.
    """
    parts = str(site_hand_id).split("-")
    if len(parts) < 2:
        return None
    try:
        return f"{int(parts[0][:14])}{int(parts[1])}"
    except ValueError:
        return None


def get_winamax_log_dir() -> Path | None:
    """Return Path to Winamax application logs directory if present."""
    sys_name = platform.system()
    candidates: list[Path] = []

    if sys_name == "Darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "winamax" / "logs")
    elif sys_name == "Linux":
        candidates.append(Path.home() / ".config" / "winamax" / "logs")
        candidates.append(Path.home() / ".winamax" / "logs")
    elif sys_name == "Windows":
        appdata = os.environ.get("APPDATA")
        localdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Winamax" / "logs")
        if localdata:
            candidates.append(Path(localdata) / "Winamax" / "logs")

    for path in candidates:
        if path.is_dir():
            return path

    return None


def get_latest_winamax_log_file(log_dir: Path | None = None) -> Path | None:
    """Return path to the latest Winamax .log file by modification time."""
    target_dir = log_dir or get_winamax_log_dir()
    if not target_dir or not target_dir.is_dir():
        return None

    log_files = list(target_dir.glob("*.log"))
    if not log_files:
        return None

    return max(log_files, key=lambda f: f.stat().st_mtime)


class WinamaxLiveLogReader:
    """Tails the active Winamax log and reports live table composition.

    ``on_table_update`` is called from the tailing thread, so callers that touch
    Qt widgets must marshal onto the GUI thread themselves.
    """

    PRIME_BYTES = 400_000
    """How far back to read when opening a log, to recover recent hand/window pairs.

    The client writes a few hundred bytes per hand, so this covers well over an
    hour of multi-table play -- comfortably more than the backlog still waiting
    to be imported when the HUD starts.
    """

    HAND_TABLE_HISTORY = 500
    """How many recent hands to remember for :meth:`table_no_for_hand`.

    Imports lag the log by seconds; this covers a long multi-table burst with
    room to spare while staying bounded over a session.
    """

    RE_HAND_START = re.compile(
        r"\[table\]\s+(?P<tbl_no>\d+)\s+(?P<pool>\S+)\s+hand\s+(?P<hand_id>\S+)",
    )
    RE_ACTION = re.compile(
        r"\[table\]\s+(?P<tbl_no>\d+)\s+(?P<pool>\S+)\s+action\s+(?P<action_type>\S+)\s+login=\"(?P<login>[^\"]+)\"",
    )
    RE_CARDS = re.compile(
        r"\[table\]\s+(?P<tbl_no>\d+)\s+(?P<pool>\S+)\s+cards\s+login=\"(?P<login>[^\"]+)\"",
    )
    # The pot being awarded is the end of the hand, and of this table.
    RE_GAIN = re.compile(
        r"\[table\]\s+(?P<tbl_no>\d+)\s+(?P<pool>\S+)\s+gain\s",
    )

    def __init__(
        self,
        on_table_update: Callable[[WinamaxTableUpdate], None] | None = None,
        poll_interval: float = 0.2,
    ) -> None:
        self.on_table_update = on_table_update
        self.poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._tables: dict[str, WinamaxTableUpdate] = {}
        self._tailing: Path | None = None
        # Site hand id -> client table index, so an imported hand can be traced
        # back to the window it was played on. Bounded: only recent hands can
        # still be waiting to be imported.
        self._hand_tables: OrderedDict[str, str] = OrderedDict()
        self._priming = False

    @property
    def is_tailing(self) -> bool:
        """Whether a Winamax log file is currently open and being followed.

        False when the client is not installed, or its logs live somewhere this
        build does not know about -- in which case there is no live seat data and
        callers should not rely on one existing.
        """
        return self._running and self._tailing is not None

    def get_table(self, pool: str) -> WinamaxTableUpdate | None:
        """Return the last known state for a pool, if any."""
        return self._tables.get(pool)

    def table_no_for_hand(self, hand_id: str) -> str | None:
        """The client table index a hand was dealt on, if it was seen in the log.

        Several Escape windows on one pool all write hand histories under the
        pool's name, so this is the only thing that says which window a hand came
        from -- and therefore which window's HUD it belongs to.
        """
        return self._hand_tables.get(str(hand_id))

    def parse_log_line(self, line: str) -> dict[str, Any] | None:
        """Parse a single Winamax log line into an event dict, or None."""
        if "[table]" not in line:
            return None

        if " hand " in line and (m := self.RE_HAND_START.search(line)):
            stamp = re.match(r"\s*(\d{10,})", line)
            return {
                "event": "hand_start",
                "table_no": m.group("tbl_no"),
                "pool": m.group("pool"),
                "hand_id": m.group("hand_id"),
                "logged_at_ms": int(stamp.group(1)) if stamp else 0,
            }

        if " action " in line and (m := self.RE_ACTION.search(line)):
            return {
                "event": "action",
                "table_no": m.group("tbl_no"),
                "pool": m.group("pool"),
                "action_type": m.group("action_type"),
                "login": m.group("login"),
            }

        if " gain " in line and (m := self.RE_GAIN.search(line)):
            return {
                "event": "hand_over",
                "table_no": m.group("tbl_no"),
                "pool": m.group("pool"),
            }

        # Only the hero's cards are ever logged, which is what identifies them.
        if " cards " in line and (m := self.RE_CARDS.search(line)):
            return {
                "event": "cards",
                "table_no": m.group("tbl_no"),
                "pool": m.group("pool"),
                "login": m.group("login"),
            }

        return None

    def _prime_from_tail(self, file_obj: Any) -> None:
        """Learn recent hand -> window pairings before following the file live.

        Hands played in the seconds before the HUD started are still waiting to
        be imported, and without their window they cannot be given a HUD -- so
        each one costs the table a hand's delay at startup. Reading back over
        the end of the log recovers the pairings; the callback stays silent so
        no long-finished table is ever reported as current.
        """
        try:
            file_obj.seek(0, os.SEEK_END)
            size = file_obj.tell()
            file_obj.seek(max(0, size - self.PRIME_BYTES))
            if size > self.PRIME_BYTES:
                file_obj.readline()  # discard a line the seek cut in half

            self._priming = True
            lines = 0
            for line in file_obj:
                self.process_line(line)
                lines += 1
        except Exception:
            log.exception("Could not prime the Winamax hand/window map:")
        finally:
            self._priming = False

        log.info(
            "Primed %d hand/window pairings from the last %d lines of the log",
            len(self._hand_tables),
            lines,
        )

    def _notify(self, table: WinamaxTableUpdate) -> None:
        """Hand the current table state to the callback, never raising."""
        if self._priming or not self.on_table_update:
            return
        try:
            self.on_table_update(table)
        except Exception:
            log.exception("Error in on_table_update callback:")

    def _start_hand(
        self,
        pool: str,
        table_no: str,
        hand_id: str,
        logged_at_ms: int = 0,
    ) -> WinamaxTableUpdate:
        """Begin a new hand: a new table in a Fast-Fold pool, so a fresh ring.

        Keeping the previous ring would leave players from the table the hero
        just left showing on the one they moved to.
        """
        table = WinamaxTableUpdate(
            pool=pool,
            table_no=table_no,
            hand_id=hand_id,
            hero=None,
            logged_at_ms=logged_at_ms,
        )
        self._tables[pool] = table
        # Indexed under both the log's own id and the one fpdb stores for it, so
        # the caller can ask with whichever it is holding.
        self._hand_tables[hand_id] = table_no
        if (fpdb_id := fpdb_hand_id(hand_id)) is not None:
            self._hand_tables[fpdb_id] = table_no
        while len(self._hand_tables) > self.HAND_TABLE_HISTORY:
            self._hand_tables.popitem(last=False)
        return table

    def process_line(self, line: str) -> None:
        """Update table state from one log line and notify on change."""
        parsed = self.parse_log_line(line)
        if not parsed:
            return

        pool = parsed["pool"]
        event = parsed["event"]

        if event == "hand_start":
            table = self._start_hand(
                pool,
                parsed["table_no"],
                parsed["hand_id"],
                parsed.get("logged_at_ms", 0),
            )
            # Reported straight away, with an empty ring: on a Fast-Fold table
            # the hero has just been moved somewhere new, and everyone the HUD is
            # still showing has been left behind.
            self._notify(table)
            return

        table = self._tables.get(pool)
        if table is None:
            # Log tailing started mid-hand; wait for the next hand boundary so the
            # ring is anchored on the small blind rather than on a random actor.
            return

        if self._apply_event(table, event, parsed):
            self._notify(table)

    @staticmethod
    def _apply_event(table: WinamaxTableUpdate, event: str, parsed: dict[str, Any]) -> bool:
        """Fold one parsed event into a table's state; True if anything moved."""
        changed = False

        if event == "hand_over":
            if not table.hand_over:
                table.hand_over = True
                changed = True

        elif event == "cards":
            if table.hero != parsed["login"]:
                table.hero = parsed["login"]
                changed = True

        elif event == "action":
            login = parsed["login"]
            if login not in table.ring:
                table.ring.append(login)
                changed = True
            # A fold by the hero ends this table for them: the client moves them
            # on immediately, so the overlay should stop describing it.
            if login == table.hero and "fold" in parsed["action_type"].lower() and not table.hero_left:
                table.hero_left = True
                changed = True

        return changed

    def start(self) -> None:
        """Start the background log watcher thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop,
            name="WinamaxLiveLogReader",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background log watcher thread."""
        self._running = False
        thread, self._thread = self._thread, None
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _watch_loop(self) -> None:
        """Tail the newest Winamax log file, following rotation."""
        file_obj = None
        current_path: Path | None = None

        try:
            while self._running:
                try:
                    latest = get_latest_winamax_log_file()
                    if latest != current_path:
                        if file_obj:
                            file_obj.close()
                            file_obj = None
                        current_path = latest
                        if latest:
                            file_obj = latest.open(encoding="utf-8", errors="ignore")
                            self._prime_from_tail(file_obj)
                            log.info("Tailing Winamax log file: %s", latest)
                        self._tailing = latest

                    if file_obj:
                        while line := file_obj.readline():
                            self.process_line(line)

                except Exception:
                    log.exception("Error reading Winamax live log:")
                    if file_obj:
                        file_obj.close()
                        file_obj = None
                    current_path = None
                    self._tailing = None

                time.sleep(self.poll_interval)
        finally:
            self._tailing = None
            if file_obj:
                file_obj.close()
