#!/usr/bin/env python3
"""Live CoinPoker HUD feed: sniff the poker TCP stream, decode, import to DB.

CoinPoker's poker protocol is a plaintext binary stream on raw TCP
(poker-nlb:9000 and :7002), opened by the Electron main process. This module
captures that traffic natively (``coinpoker_pcap``, libpcap on Linux/macOS,
Npcap on Windows -- no external Python dependency), reassembles the
server->client byte stream, decodes game events (``coinpoker_protocol``), builds
fpdb hands (``coinpoker_hand_builder`` -> ``http_capture_hand_builder``) and
imports each completed hand into the fpdb database so the existing HUD reads it.

Modes
-----
Live capture (needs root / Administrator, like any sniffer)::

    sudo python -m fpdb_3_legacy.coinpoker_live_capture --live
    # Windows (elevated shell, Npcap installed):
    python -m fpdb_3_legacy.coinpoker_live_capture --live --iface "\\Device\\NPF_{...}"

List capture devices::

    python -m fpdb_3_legacy.coinpoker_live_capture --list-ifaces

Replay a saved pcap/pcapng file (no privileges; for testing)::

    python -m fpdb_3_legacy.coinpoker_live_capture --replay capture.pcap --dry-run

Portable fallback if native capture is unavailable, pipe any sniffer's
``-S -x`` text (tcpdump/tshark) into stdin::

    sudo tcpdump -i any -l -n -S -x 'tcp port 9000 or tcp port 7002' \
        | python -m fpdb_3_legacy.coinpoker_live_capture --stdin

``--dry-run`` builds and validates hands without writing to the database.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator
from typing import Any

from fpdb_3_legacy.aof_equity import KnownCardsAnalysisCoordinator
from fpdb_3_legacy.aof_ranges import PopulationActionModel, PopulationObservedRange
from fpdb_3_legacy.coinpoker_hand_builder import (
    AOF_OMAHA_CATEGORY,
    MINI_GAME_OMAHA,
    build_hands,
    joined_tournaments,
    tournament_result_announcements,
)
from fpdb_3_legacy.coinpoker_protocol import decode_frame
from fpdb_3_legacy.equity_async import AsyncEquityService
from fpdb_3_legacy.Exceptions import FpdbHandDuplicate
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    HttpCaptureHandConfig,
    build_fpdb_hand,
    import_fpdb_hand,
    render_fpdb_hand,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("coinpoker_live_capture")


def _default_archive_dir() -> str:
    """Directory holding the text archive of captured hands."""
    return os.path.join(os.path.expanduser("~"), ".fpdb", "coinpoker-capture")


class RawEventArchive:
    """Append decoded protocol events verbatim enough for later replay/audit."""

    def __init__(self, archive_dir: str | None = None) -> None:
        self.archive_dir = archive_dir if archive_dir is not None else _default_archive_dir()
        self._warned = False

    def append(self, event: tuple) -> None:
        if not self.archive_dir:
            return
        try:
            now = datetime.datetime.now(datetime.UTC)
            name, hand_id, payload = event
            record = {
                "captured_at": now.isoformat(),
                "event": name,
                "hand_id": hand_id,
                "payload": payload,
            }
            os.makedirs(self.archive_dir, exist_ok=True)
            path = os.path.join(self.archive_dir, f"coinpoker-raw-{now:%Y-%m-%d}.jsonl")
            with open(path, "a", encoding="utf-8") as archive:
                archive.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001 - diagnostics must never break capture
            if not self._warned:
                self._warned = True
                print(f"[WARN] could not archive raw CoinPoker events: {exc}")


COINPOKER_SITE_ID = 140
# How many sweeps a player's place is offered before the absence of a row for
# them is taken as final rather than as something still on its way.
MAX_RESULT_ATTEMPTS = 3
# What it takes for the announced players to name one tournament rather than
# another: several of them at that tournament, and clearly more than anywhere
# else. One shared regular says nothing, and a lead of one is not a lead.
MIN_CORRELATED_PLAYERS = 2
CORRELATION_MARGIN = 2
# What has become of an announcement: waiting to be tied to a tournament, tied
# to one, answered in full, or tied to none and closed unanswered.
UNASSIGNED = "unassigned"
ASSIGNED = "assigned"
SETTLED = "settled"
REJECTED = "rejected"
# CoinPoker game servers: TCP 9000 (poker cluster) plus a per-table 70xx range
# (7001, 7002, ... vary by table), so match the whole range rather than fixed ports.
GAME_PORTS = ("3000", "3001", "9000", "7002")  # see _is_game_port / BPF_FILTER
_TOURNAMENT_PORT_RANGE = range(3000, 3002)
_GAME_PORT_RANGE = range(7000, 7101)


def _known_aof_tables(db) -> dict[str, int]:
    """Recover AoF table identities already established by an earlier run.

    CoinPoker sends the AoF catalogue through the lobby connection, not the
    table connection. A capture restarted while the player is already seated
    therefore sees hands but no catalogue and used to file the same table as
    ordinary Omaha until the lobby happened to announce it again. A prior hand
    stored under the dedicated category is durable, table-specific evidence
    that survives that restart.
    """
    if db is None:
        return {}
    try:
        placeholder = db.sql.query.get("placeholder", "%s")
        cursor = db.get_cursor()
        cursor.execute(
            f"""
                SELECT DISTINCT h.tableName
                  FROM Hands h
                  JOIN Gametypes g ON g.id = h.gametypeId
                 WHERE g.siteId = {placeholder}
                   AND g.category = {placeholder}
                   AND h.tableName IS NOT NULL
            """,
            (COINPOKER_SITE_ID, AOF_OMAHA_CATEGORY),
        )
        return {str(row[0]): MINI_GAME_OMAHA for row in cursor.fetchall() if row[0] is not None}
    except Exception:  # noqa: BLE001 - a cache read must not stop live capture
        log.warning("Could not restore known CoinPoker AoF tables from the database", exc_info=True)
        return {}
    finally:
        # The read opens a transaction on PostgreSQL. The capture can then wait
        # indefinitely for packets, so release its snapshot and locks now.
        with contextlib.suppress(Exception):
            db.rollback()


def _is_game_port(port: int) -> bool:
    return port == 9000 or port in _TOURNAMENT_PORT_RANGE or port in _GAME_PORT_RANGE


# Header line carries seq (absolute, since capture starts mid-connection) and length.
_HDR_RE = re.compile(
    r"\.(?P<sport>\d+) > \S+?\.(?P<dport>\d+):.*?\bseq (?P<seq>\d+)(?::\d+)?.*\blength (?P<len>\d+)$",
)
_HEX_RE = re.compile(r"\s+0x[0-9a-f]+:\s+((?:[0-9a-f]{2,4}\s?)+)")

_FRAME_FLAGS = frozenset({0x80, 0xA0})  # uncompressed / zlib frame start markers
_SEQ_MOD = 1 << 32
_MAX_PENDING = 512  # out-of-order segments before we force a resync
_MAX_TAIL = 1 << 20  # cap the undecoded tail buffer (guards against runaway)


def _seq_lt(a: int, b: int) -> bool:
    """Serial-number (RFC 1982) less-than for 32-bit TCP sequence numbers."""
    return 0 < (b - a) % _SEQ_MOD < (_SEQ_MOD >> 1)


class _Tee:
    """Write to several streams at once (used to mirror output to a log file).

    ``None`` streams are dropped: under ``pythonw.exe`` (how the Windows GUI
    launches the elevated capture) there is no console, so ``sys.__stdout__`` and
    ``sys.__stderr__`` are ``None``. Writing to them would raise on the first
    ``print`` and kill the capture silently, so the log file must survive alone.
    """

    def __init__(self, *streams) -> None:
        self._streams = [s for s in streams if s is not None]

    def write(self, text: str) -> int:
        for stream in self._streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


class _Conn:
    """Per-connection sequenced reassembly + incremental frame decoding."""

    def __init__(self) -> None:
        self.next_seq: int | None = None
        self.pending: dict[int, bytes] = {}
        self.buf = bytearray()  # contiguous, not-yet-decoded application bytes

    def add(self, seq: int, payload: bytes) -> None:
        if not payload:
            return
        if self.next_seq is None:
            self.next_seq = seq
        if seq == self.next_seq:
            self._append(payload)
        elif _seq_lt(seq, self.next_seq):
            # Retransmission / overlap: keep only bytes past next_seq.
            overlap = (self.next_seq - seq) % _SEQ_MOD
            if overlap < len(payload):
                self._append(payload[overlap:])
            # else: a pure duplicate — drop it.
        else:
            # Ahead of next_seq: buffer until the gap fills.
            self.pending[seq] = payload
            if len(self.pending) > _MAX_PENDING:
                self._resync()

    def _append(self, payload: bytes) -> None:
        if self.next_seq is None:
            raise RuntimeError("cannot append TCP payload before sequence initialization")
        self.buf.extend(payload)
        self.next_seq = (self.next_seq + len(payload)) % _SEQ_MOD
        self._drain()
        if len(self.buf) > _MAX_TAIL:
            # A frame never completed (corruption/gap): drop to the next marker.
            self._realign()

    def _drain(self) -> None:
        while self.next_seq in self.pending:
            seg = self.pending.pop(self.next_seq)
            self.buf.extend(seg)
            self.next_seq = (self.next_seq + len(seg)) % _SEQ_MOD

    def _resync(self) -> None:
        # A segment was lost (never captured). Skip ahead to the earliest pending
        # segment and let frame realignment recover the stream.
        lo = min(self.pending, key=lambda s: (s - (self.next_seq or 0)) % _SEQ_MOD)
        self.next_seq = lo
        self._drain()
        self._realign()

    def _realign(self) -> None:
        # After a gap we cannot know frame boundaries; scan to the next frame
        # start marker and drop the garbage before it.
        for i in range(len(self.buf)):
            if self.buf[i] in _FRAME_FLAGS:
                del self.buf[:i]
                return
        self.buf.clear()

    def pop_frames(self) -> list[tuple[int, bytes]]:
        """Extract all complete frames now available; self-heals misalignment."""
        frames: list[tuple[int, bytes]] = []
        while len(self.buf) >= 3:
            if self.buf[0] not in _FRAME_FLAGS:
                self._realign()
                if len(self.buf) < 3 or self.buf[0] not in _FRAME_FLAGS:
                    break
            flags = self.buf[0]
            length = (self.buf[1] << 8) | self.buf[2]
            if 3 + length > len(self.buf):
                break
            frames.append((flags, bytes(self.buf[3 : 3 + length])))
            del self.buf[: 3 + length]
        return frames


class StreamReassembler:
    """Reassemble server->client TCP streams from ``tcpdump -x`` text lines.

    Sequence numbers order the payloads, drop retransmissions, and buffer
    out-of-order segments; frames are decoded incrementally (so the buffer stays
    bounded) and misalignment self-heals on the frame markers. ``feed_line``
    returns any newly decoded ``game.*`` events.
    """

    def __init__(self) -> None:
        from fpdb_3_legacy.coinpoker_protocol import protocol_event_from_object

        # Preserve tournament/result envelopes as well as game actions. Hand
        # construction naturally ignores unrelated event names.
        self._protocol_event = protocol_event_from_object
        self.conns: dict[str, _Conn] = {}
        self._cur_key: str | None = None
        self._cur_seq = 0
        self._cur_len = 0
        self._hex: list[str] = []

    def add_segment(self, key: str, seq: int, payload: bytes) -> list[tuple]:
        """Add one server->client TCP segment and return newly decoded events.

        This is the transport-agnostic entry point shared by the text (tcpdump)
        and native libpcap sources.
        """
        if not payload:
            return []
        conn = self.conns.setdefault(key, _Conn())
        conn.add(seq % _SEQ_MOD, payload)
        events = []
        try:
            server_port = int(key.partition("->")[0])
        except ValueError:
            server_port = 0
        for flags, body in conn.pop_frames():
            try:
                obj = decode_frame(flags, body)
            except Exception:  # noqa: BLE001 - best-effort decode; skip malformed frames
                log.debug("Skipping malformed CoinPoker frame", exc_info=True)
                continue
            ev = self._protocol_event(obj) if obj is not None else None
            if ev is not None:
                name, hand_id, data = ev
                if server_port in _TOURNAMENT_PORT_RANGE and isinstance(data, dict):
                    data = {**data, "_coinpokerServerPort": server_port}
                    ev = (name, hand_id, data)
                events.append(ev)
        return events

    def _flush(self) -> list[tuple]:
        if self._cur_key is None:
            return []
        allb = bytes.fromhex("".join(self._hex))
        payload = allb[-self._cur_len :] if 0 < self._cur_len <= len(allb) else b""
        key, seq = self._cur_key, self._cur_seq
        self._cur_key, self._cur_len, self._hex = None, 0, []
        return self.add_segment(key, seq, payload)

    def feed_line(self, line: str) -> list[tuple]:
        """Feed one tcpdump text line; return newly decoded game events."""
        if line and not line[0].isspace():
            events = self._flush()
            m = _HDR_RE.search(line)
            if m and _is_game_port(int(m.group("sport"))):
                self._cur_key = f"{m.group('sport')}->{m.group('dport')}"
                self._cur_seq = int(m.group("seq")) % _SEQ_MOD
                self._cur_len = int(m.group("len"))
                self._hex = []
            else:
                self._cur_key = None
            return events
        m = _HEX_RE.match(line)
        if m and self._cur_key is not None:
            self._hex.append(m.group(1).replace(" ", ""))
        return []


BPF_FILTER = "tcp portrange 3000-3001 or tcp portrange 7000-7100 or tcp port 9000"


def _events_from_segments(segments: Iterable[tuple[int, int, int, bytes]]) -> Iterator[tuple]:
    """Turn (src_port, dst_port, seq, payload) tuples into decoded game events."""
    reassembler = StreamReassembler()
    for src_port, dst_port, seq, payload in segments:
        if _is_game_port(src_port) and payload:
            yield from reassembler.add_segment(f"{src_port}->{dst_port}", seq, payload)


def _events_from_lines(lines: Iterable[str]) -> Iterator[tuple]:
    """Turn tcpdump ``-x`` text lines (stdin fallback) into decoded game events."""
    reassembler = StreamReassembler()
    for line in lines:
        yield from reassembler.feed_line(line.rstrip("\n"))


def ensure_coinpoker_site(db) -> None:
    """Insert the CoinPoker row into the Sites table if it is missing."""
    try:
        cur = db.get_cursor()
        ph = db.sql.query.get("placeholder", "%s")
        cur.execute(f"SELECT id FROM Sites WHERE id = {ph}".replace("%s", ph), (COINPOKER_SITE_ID,))
        if cur.fetchone() is None:
            cur.execute(
                f"INSERT INTO Sites (id, name, code) VALUES ({ph}, {ph}, {ph})".replace("%s", ph),
                (COINPOKER_SITE_ID, "CoinPoker", "CP"),
            )
            db.commit()
            print(f"[INFO] Registered CoinPoker as site id {COINPOKER_SITE_ID}.")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not ensure CoinPoker site row: {exc}")


class HandPump:
    """Turns a growing event list into imported hands, once per completed hand."""

    def __init__(
        self,
        db,
        config,
        *,
        table_category: str = "PLO4",
        dry_run: bool = False,
        file_id: int = 0,
        notify=None,
        archive_dir: str | None = None,
        equity_coordinator: KnownCardsAnalysisCoordinator | None = None,
        known_aof_tables: dict[str, Any] | None = None,
    ) -> None:
        self.db = db
        self.config = config
        self.table_category = table_category
        self.dry_run = dry_run
        self.file_id = file_id
        self.notify = notify  # ZMQSender to ping HUD_main after each import
        self.equity_coordinator = equity_coordinator
        self.imported: set[str] = set()
        self.failed: set[str] = set()
        # Hands of a game fpdb cannot store. Terminal like the other two: what
        # is not importable now will not become so, and a hand nobody ever
        # answers for is a hand whose events are never dropped.
        self.capture_only: set[str] = set()
        # The room announces the tournament once, when the table is joined.
        # Holding the announcement here keeps every later batch on the same
        # tournament instead of each naming itself after its own table.
        self._session_context: list[tuple] = []
        # Tournaments the room has said this capture is playing, by table.
        self._tournaments_by_table: dict[str, str] = {}
        # Who was seen playing which tournament. The closing announcement names
        # only players, so this is what tells us which tournament it closes.
        self._players_by_tournament: dict[str, set[str]] = {}
        # The tables this capture has dealt hands at. Whether a marker naming
        # no table is ambiguous is a fact about the capture, not about the
        # twenty events of one sweep.
        self._session_tables: set[str] = set()
        # Which tables are All-in or Fold, as the room said. The catalogue
        # saying so is far too large to keep among the events and is pruned
        # with them, so what it said is kept here instead. The database seeds
        # the new process as well: restarting while already seated carries no
        # lobby catalogue, but must not turn the same table into ordinary Omaha.
        self._session_aof: dict[str, Any] = dict(known_aof_tables or {})
        # How each table deals: flop first, or betting first. When the capture
        # began with the client already seated it sees no lobby at all, and
        # the order of the room's own packets is the last thing left to tell
        # All-in or Fold apart.
        self._session_shape: dict[str, Any] = {}
        # One entry per closing announcement, each with its own tournament and
        # its own tally of who has been filed. They are held here rather than
        # left in the event buffer: an announcement is answered over several
        # sweeps, so it must outlive the events it arrived on -- and two of
        # them left in the buffer together were read as one roll of names.
        self._pending_results: list[dict] = []
        # Every announcement this capture has taken, answered or not, so one
        # already dealt with is not picked up again from a later sweep.
        self._announcements_seen: set[frozenset] = set()
        # How many times each player's place has been attempted, so a player
        # with no entry to write on stops being re-queried on every sweep for
        # the rest of the run.
        self._result_attempts: dict[str, dict[str, int]] = {}
        # A live capture has no source file: once a hand is imported the packets
        # are gone, so nothing could be checked against the room afterwards (the
        # hand text is not stored in the database either -- Hands has no text
        # column and RawHands is never written). Render every built hand to a
        # dated archive so winnings stay auditable and re-importable.
        self.archive_dir = archive_dir if archive_dir is not None else _default_archive_dir()
        self._archive_warned = False

    def _archive_hand(self, hand) -> None:
        """Append the built hand's text rendering to the dated archive."""
        if not self.archive_dir:
            return
        try:
            os.makedirs(self.archive_dir, exist_ok=True)
            day = getattr(hand, "startTime", None) or datetime.datetime.now(datetime.UTC)
            path = os.path.join(self.archive_dir, f"coinpoker-{day:%Y-%m-%d}.txt")
            text = render_fpdb_hand(hand)
            with open(path, "a", encoding="utf-8") as archive:
                archive.write(text.rstrip("\n") + "\n\n\n")
        except Exception as exc:  # noqa: BLE001 - archiving must never break the feed
            if not self._archive_warned:
                self._archive_warned = True
                print(f"[WARN] could not archive captured hands to {self.archive_dir}: {exc}")

    @staticmethod
    def _stamp_capture_time(hand_data: dict) -> None:
        """Give an unstamped hand the capture time (UTC-naive) instead of 1970.

        The CoinPoker stream carries no per-hand clock, so an unstamped hand would
        default to 1970-01-01 and fall outside the GUI's date filters (empty
        graphs / hand viewer). This is a live feed, so "now" is the hand time, and
        UTC-naive matches how every other site stores startTime.
        """
        if not hand_data.get("timestamp"):
            hand_data["timestamp"] = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    def _remember_tournaments(self, events: list[tuple]) -> None:
        """Note which tournament each joined table belongs to."""
        for table, (tour_no, _name) in joined_tournaments(events).items():
            self._tournaments_by_table[table] = tour_no

    def _remember_tournament_players(self, hand_data: dict) -> None:
        """Note who was seen playing which tournament.

        This is what later ties a closing announcement to a tournament: the
        announcement names players, and the players are the only thing it and
        the tournament's hands have in common.
        """
        tournament = hand_data.get("tournament")
        if not tournament:
            return
        seated = self._players_by_tournament.setdefault(tournament["tour_no"], set())
        seated.update(player["name"] for player in hand_data.get("players", ()))

    def _the_tournament_being_finished(self, results: list[dict]) -> str | None:
        """The tournament a closing announcement belongs to, when it is certain.

        The announcement names neither a tournament nor a table, only players,
        so they are what identifies it: the tournament these people were
        actually playing is the one finishing. Counting the tournaments known
        would not do -- with one on the books the count is right whether or not
        the announcement is that tournament's, and a capture that played two in
        a row has two long after the first has ended. Filing a place on the
        wrong tournament is worse than not filing it: it would land on someone
        else's entry and read as a real result.

        Sharing a player is not enough either: regulars turn up in several of
        an evening's tournaments, and a real announcement of 35 places was
        found to brush against three of them -- on 9, 3 and 2 shared players.
        Nor is simply sharing the most of them, which 3 against 2 would win on
        a single regular's whim. The tournament has to be the obvious answer:
        it must share several of the announced players, and clearly more of
        them than any other tournament of the capture. Anything closer is a
        coincidence being read as a correlation, and it is not filed.

        What this cannot rule out is an announcement for a tournament none of
        whose hands were captured, whose entire table also played one that
        was. Nothing in the announcement distinguishes that case, so a place
        stays only as good as having seen the tournament played.
        """
        announced = {result["player"] for result in results}
        overlaps = sorted(
            ((len(announced & seated), tour_no) for tour_no, seated in self._players_by_tournament.items()),
            reverse=True,
        )
        shared, best = overlaps[0] if overlaps else (0, None)
        runner_up = overlaps[1][0] if len(overlaps) > 1 else 0
        if shared >= MIN_CORRELATED_PLAYERS and shared >= runner_up * CORRELATION_MARGIN:
            return best
        if not shared:
            print("[WARN] tournament results announced for players seen in no tournament of this capture; not filed")
        else:
            print(
                f"[WARN] tournament results announced share {shared} player(s) with one tournament "
                f"and {runner_up} with another; too close to tell them apart, not filed",
            )
        return None

    def _write_one_place(self, tour_no: str, result: dict, given_up: set[str]) -> str | None:
        """File one player's place in its own transaction, returning their name.

        One place, one transaction. Holding a whole sweep open instead would
        make every place hostage to the worst of them: a statement that raises
        leaves the transaction aborted on PostgreSQL, so each later place in
        the sweep fails too and the closing commit writes nobody -- while the
        error names only the first player, so the log reads as one casualty.
        Committing per player also keeps a place durable the moment it lands,
        and marked only once its own commit has returned.
        """
        player = result["player"]
        attempts = self._result_attempts.setdefault(tour_no, {})
        attempts[player] = attempts.get(player, 0) + 1
        try:
            # The place only. What was won is a label ("Ticket"), and writing a
            # number in an unproven unit or currency would read as a real
            # result; the update coalesces, so the winnings column is left as
            # it was.
            found = self.db.updateTourneyPlayerResult("CoinPoker", tour_no, player, result["rank"])
            if found:
                self.db.commit()
        except Exception as exc:  # noqa: BLE001 - one player must not lose the rest
            # Undo whatever this player's statement left behind, so the next
            # one starts on a transaction the database will still accept.
            with contextlib.suppress(Exception):
                self.db.rollback()
            print(f"[WARN] could not record {player} in tournament {tour_no}: {exc}")
            return None
        if found:
            return player
        # Nothing was written, but the read opened a transaction; leaving it
        # hanging would hold locks for the rest of the run.
        with contextlib.suppress(Exception):
            self.db.rollback()
        if attempts[player] >= MAX_RESULT_ATTEMPTS:
            # No row for this player, and the announcement only arrives once
            # the last hand has been played -- so a player still absent after
            # several sweeps was never dealt in at a table we captured, and no
            # amount of retrying will conjure the row. Left in, they would be
            # re-queried on every sweep for the rest of the run, which for a
            # table of strangers is most of the announcement.
            given_up.add(player)
            print(f"[WARN] tournament {tour_no}: {player} has no entry to record a place on; giving up")
        return None

    def _take_announcements(self, events: list[tuple]) -> None:
        """Hold each closing announcement seen, once, as its own piece of work.

        Taking them out of the stream is what lets the buffer be pruned: an
        announcement is answered over several sweeps, so it has to outlive the
        events it arrived on -- and while it stayed among them, the next
        tournament's announcement was read together with it as one roll of
        names belonging to nobody.
        """
        for places in tournament_result_announcements(events):
            seen = frozenset((place["player"], place["rank"]) for place in places)
            if seen in self._announcements_seen:
                continue
            self._announcements_seen.add(seen)
            self._pending_results.append(
                {
                    "places": places,
                    "done": set(),
                    "given_up": set(),
                    "tour_no": None,
                    "state": UNASSIGNED,
                    "tries": 0,
                },
            )

    def record_tournament_results(self, events: list[tuple]) -> int:
        """Store where each paid player finished, once the room announces it.

        The announcement arrives after the last hand, so it cannot ride in on
        one: the places are written straight onto the tournament's players.
        Each announcement is answered on its own -- an evening holds more than
        one tournament, and the second's places are not the first's.
        Returns how many were recorded.
        """
        self._remember_tournaments(events)
        self._take_announcements(events)
        if self.db is None or self.dry_run:
            return 0
        filed = sum(self._file_announcement(pending) for pending in self._pending_results)
        # An announcement that has been answered, one way or the other, is not
        # work any more. Dropping it keeps the sweep proportional to what is
        # still outstanding rather than to everything the room has ever said.
        self._pending_results = [
            pending for pending in self._pending_results if pending["state"] not in (SETTLED, REJECTED)
        ]
        return filed

    def _assign_tournament(self, pending: dict) -> str | None:
        """Name the tournament this announcement closes, once and for good.

        Answered once because the two wrong answers are symmetrical: an
        announcement half filed must not move to another tournament, and one
        that could not be placed must not be picked up later by a tournament
        that happens to seat those players. The lobby broadcasts the results
        of tournaments this capture never played -- a real one carried twenty
        such places -- and left waiting they would land on the next tournament
        to come along. A few sweeps are allowed for hands still being
        imported; after that the refusal is the answer.
        """
        if pending["state"] != UNASSIGNED:
            return pending["tour_no"]
        pending["tries"] += 1
        tour_no = self._the_tournament_being_finished(pending["places"])
        if tour_no is not None:
            pending["tour_no"], pending["state"] = tour_no, ASSIGNED
        elif pending["tries"] >= MAX_RESULT_ATTEMPTS:
            pending["state"] = REJECTED
            print(f"[WARN] {len(pending['places'])} announced place(s) belong to no tournament seen here; dropped")
        return pending["tour_no"]

    def _file_announcement(self, pending: dict) -> int:
        """Write whatever of one announcement's places can still be written."""
        places = pending["places"]
        tour_no = self._assign_tournament(pending)
        if tour_no is None:
            return 0

        done, given_up = pending["done"], pending["given_up"]
        settled = done | given_up
        outstanding = [place for place in places if place["player"] not in settled]
        if not outstanding:
            pending["state"] = SETTLED
            return 0

        # Each place stands on its own transaction, so one that cannot be
        # written costs nobody else theirs, and a player is marked as filed
        # only once their own commit has returned. Whoever is left is offered
        # again on the next sweep rather than being taken as filed.
        written = (self._write_one_place(tour_no, place, given_up) for place in outstanding)
        filed = [player for player in written if player is not None]

        if filed:
            done.update(filed)
            print(f"[IMPORTED] tournament {tour_no}: {len(filed)} finishing place(s)")
        missing = len(places) - len(done) - len(given_up)
        if missing:
            print(f"[WARN] tournament {tour_no}: {missing} place(s) still unfiled; will retry")
        return len(filed)

    def _answered_for(self, hid: str) -> bool:
        """True once this hand has been imported, failed, or set aside."""
        return hid in self.imported or hid in self.failed or hid in self.capture_only

    def _is_capture_only(self, hand_data: dict) -> bool:
        """True for a hand of a game fpdb has no model for, which is terminal.

        Nothing about it will change on a later sweep, so it is finished with
        here. Left unanswered it reads as a hand still being dealt and its
        events are never dropped from the buffer -- one all-in-or-fold Hold'em
        hand was enough to keep sixty-six events for the rest of the run. The
        raw archive keeps it, to be imported if fpdb learns the game.
        """
        if hand_data.get("game", {}).get("fpdb_supported", True):
            return False
        hid = hand_data["hand_id"]
        self.capture_only.add(hid)
        print(f"[CAPTURE-ONLY] hand #{hid} ({hand_data['gametype']['category']}) — archived, not imported")
        return True

    def process(self, events: list[tuple]) -> int:
        new = 0
        self._remember_tournaments(events)
        for hand_data in build_hands(
            events,
            self.table_category,
            session_context=self._session_context,
            session_tables=self._session_tables,
            session_aof=self._session_aof,
            session_shape=self._session_shape,
        ):
            hid = hand_data["hand_id"]
            if self._answered_for(hid):
                continue
            if self._is_capture_only(hand_data):
                continue
            self._stamp_capture_time(hand_data)
            try:
                hand = build_fpdb_hand(hand_data, config=self.config)
            except CaptureNotImportableError:
                continue  # hand not complete yet (no winner/collection); retry later
            except Exception as exc:  # noqa: BLE001 - one malformed hand must not kill the feed
                self.failed.add(hid)
                print(f"[WARN] skipped hand #{hid}: {exc}")
                self._log_failed_hand(hand_data, exc)
                continue
            self._archive_hand(hand)
            # Tell fpdb who the hero is (needed for hero stats and the HUD).
            hero = hand_data.get("hero")
            if hero and any(p[1] == hero for p in hand.players):
                hand.hero = hero
            self.imported.add(hid)
            self._remember_tournament_players(hand_data)
            new += 1
            self._insert_hand(hand, hid)
        return new

    def _insert_hand(self, hand: Any, hid: str) -> None:
        """Write one built hand to the database and tell the HUD about it."""
        if self.dry_run or self.db is None:
            print(f"[DRY-RUN] hand #{hid} built ({len(hand.players)} players) — not inserted")
            return
        try:
            # Each hand is flushed immediately (doinsert=True); reset the
            # shared bulk buffers first so we don't re-insert prior hands.
            self.db.resetBulkCache()
            import_fpdb_hand(hand, self.db, file_id=self.file_id, doinsert=True)
            self.db.commit()
            print(f"[IMPORTED] hand #{hid}")
            # Ping HUD_main (if running) with the DB hand id so it can pop
            # or refresh the HUD for this table.
            if self.notify is not None:
                with contextlib.suppress(Exception):
                    self.notify.send_hand_id(hand.dbid_hands)
            if self.equity_coordinator is not None:
                decisions = getattr(hand, "aof_decisions", ()) or ()
                decision_ids = getattr(hand, "aof_decision_ids", ()) or ()
                try:
                    self.equity_coordinator.submit_hand(hand, decisions, decision_ids)
                except Exception:
                    log.exception("known-card equity was not queued for hand %s", hand.dbid_hands)
        except FpdbHandDuplicate:
            # Replayed packets or a capture restart can legitimately expose
            # a hand already committed by this or another importer.
            with contextlib.suppress(Exception):
                self.db.rollback()
            print(f"[DUPLICATE] hand #{hid} already imported — skipped")
        except Exception as exc:  # noqa: BLE001
            # Roll back so an aborted transaction doesn't block later hands.
            with contextlib.suppress(Exception):
                self.db.rollback()
            self.failed.add(hid)
            print(f"[ERROR] import of #{hid} failed: {exc}")

    @staticmethod
    def _log_failed_hand(hand_data: dict, exc: Exception) -> None:
        """Persist rejected normalized data so live-only protocol cases are diagnosable."""
        path = os.path.expanduser("~/.fpdb/coinpoker-failed-hands.jsonl")
        record = {"error": f"{type(exc).__name__}: {exc}", "hand": hand_data}
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
        except OSError as log_exc:
            print(f"[WARN] could not write failed-hand diagnostic: {log_exc}")

    def prune(self, events: list[tuple]) -> list[tuple]:
        """Keep only the hands still being assembled.

        An event naming no hand used to stay in the buffer for the rest of the
        run, since it belonged to no hand that could be finished. The lobby
        sends thousands of them, so the buffer only ever grew and every sweep
        re-read all of it -- and the announcements among them accumulated
        until two tournaments' places were read as one. What is worth keeping
        from them has already been taken: the joins and markers into the
        session context, the announcements into their own pending entries.
        """
        return [e for e in events if e[1] is not None and not self._answered_for(e[1])]


def _resolve_config_file() -> str | None:
    """Find HUD_config.xml even when running elevated (sudo resets $HOME)."""
    import os

    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and hasattr(os, "geteuid") and os.geteuid() == 0:
        try:
            import pwd

            home = pwd.getpwnam(sudo_user).pw_dir
        except (ImportError, KeyError):
            return None
        candidate = os.path.join(home, ".fpdb", "HUD_config.xml")
        if os.path.exists(candidate):
            return candidate
    return None


def _ensure_capture_file(db) -> int:
    """Return a valid Files row id to attach imported hands to (FK requirement)."""
    name = "coinpoker-live-capture"
    try:
        file_id = db.get_id(name)
        if not file_id:
            now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            file_id = db.storeFile([name, "CoinPoker", now, now, 0, 0, 0, 0, 0, 0, 0, False])
        # get_id() also opens a PostgreSQL transaction.  Never leave it idle
        # while the capture waits indefinitely for network traffic.
        db.commit()
        return int(file_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not create capture Files row: {exc}")
        with contextlib.suppress(Exception):
            db.rollback()
        return 0


def _make_hud_notifier():
    """Return a ZMQSender that pings a running HUD_main, or None if unavailable."""
    try:
        from fpdb_3_legacy.Importer import ZMQSender

        return ZMQSender()  # PUSH to 127.0.0.1:5555 (HUD_main's port)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] HUD notifier unavailable: {exc}")
        return None


def _open_db(config_file: str | None = None):
    from fpdb_3_legacy import Configuration, Database

    config = Configuration.Config(file=config_file or _resolve_config_file())
    db = Database.Database(config)
    ensure_coinpoker_site(db)
    # nextHandId() computes max(id)+1, but store_hand lets the serial assign the
    # id. If the sequence is out of sync with max(id) the two disagree and the
    # HandsPlayers FK fails, so realign every id sequence with its table first.
    try:
        db.repair_sequences()
        # PostgreSQL sequence repair takes ShareRowExclusive locks across the
        # schema.  The live capture may then wait for hours, so release those
        # locks before opening the packet stream.
        db.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] repair_sequences failed: {exc}")
        with contextlib.suppress(Exception):
            db.rollback()
    return db, config


def _make_equity_coordinator(config, notify) -> KnownCardsAnalysisCoordinator:
    """Build the live worker with a fresh database connection per result."""
    from fpdb_3_legacy import Database

    notify_hand = notify.send_hand_id if notify is not None else None
    return KnownCardsAnalysisCoordinator(
        AsyncEquityService(),
        lambda: Database.Database(config),
        notify_hand=notify_hand,
        population_model=PopulationObservedRange(),
        action_model=PopulationActionModel(),
    )


def run(events: Iterable[tuple], *, dry_run: bool, table_category: str, config_file: str | None = None) -> None:
    file_id = 0
    notify = None
    known_aof_tables: dict[str, Any] = {}
    if dry_run:
        db, config = (
            None,
            HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID}),
        )
    else:
        db, config = _open_db(config_file)
        file_id = _ensure_capture_file(db)
        known_aof_tables = _known_aof_tables(db)
        notify = _make_hud_notifier()

    equity_coordinator = None if dry_run else _make_equity_coordinator(config, notify)
    pump = HandPump(
        db,
        config,
        table_category=table_category,
        dry_run=dry_run,
        file_id=file_id,
        notify=notify,
        equity_coordinator=equity_coordinator,
        known_aof_tables=known_aof_tables,
    )
    raw_archive = RawEventArchive()
    print("[INFO] === CoinPoker live feed active ===")
    accumulated: list[tuple] = []
    since_check = 0
    try:
        for event in events:
            raw_archive.append(event)
            accumulated.append(event)
            since_check += 1
            # Re-evaluate hands periodically (the server pushes many small events).
            if since_check >= 20:
                since_check = 0
                pump.process(accumulated)
                # The closing announcement arrives after the last hand, so it is
                # read on every sweep rather than waiting for a hand to carry it.
                pump.record_tournament_results(accumulated)
                accumulated = pump.prune(accumulated)
        pump.process(accumulated)  # final sweep (covers replay / shutdown)
        pump.record_tournament_results(accumulated)
    finally:
        if equity_coordinator is not None:
            equity_coordinator.close()
    print(f"[INFO] Done. Hands imported/built this run: {len(pump.imported)}")


def _print_devices() -> None:
    from fpdb_3_legacy.coinpoker_pcap import list_devices

    print("Available capture devices:")
    for name, desc, flags in list_devices():
        print(f"  {name:20} {desc}  (flags=0x{flags:x})")


# Byte locked to claim the instance lock on Windows. Kept far past the PID
# payload so readers (and the holder diagnostic) never touch a locked range.
_LOCK_BYTE_OFFSET = 4096


def _acquire_instance_lock(path: str | None = None):
    """Hold a non-blocking process lock so only one live importer can run.

    The returned handle owns the lock: keep it alive for the process lifetime.
    The file itself holds the holder's PID in plain text, readable at any time
    on every platform, so a rejected second instance can name the holder.
    """
    import os

    lock_path = path or os.path.expanduser("~/.fpdb/coinpoker-capture.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    handle = open(lock_path, "a+b")  # noqa: SIM115 - caller retains the lock for process lifetime
    try:
        if os.name == "nt":
            import msvcrt

            # Windows byte-range locks deny the range to every other handle, so
            # locking byte 0 would make the PID written below unreadable -- the
            # "already running (PID n)" diagnostic could never report a holder,
            # and any inspection of the file failed with PermissionError. Lock a
            # dedicated byte well past the payload instead; Windows explicitly
            # allows locking a range beyond end-of-file.
            handle.seek(_LOCK_BYTE_OFFSET)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        handle.close()
        holder = ""
        try:
            with open(lock_path, encoding="ascii") as holder_file:
                holder_pid = holder_file.read().strip()
            if holder_pid.isdigit():
                holder = f" (PID {holder_pid})"
        except OSError:
            pass
        raise RuntimeError(f"another CoinPoker live capture is already running{holder}") from None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()).encode("ascii"))
    handle.flush()
    return handle


def main() -> None:
    parser = argparse.ArgumentParser(description="CoinPoker live HUD capture feed (native libpcap/Npcap)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="Capture live traffic (needs root/Administrator).")
    src.add_argument("--replay", metavar="PCAP", help="Read a saved pcap/pcapng file (no privileges needed).")
    src.add_argument("--stdin", action="store_true", help="Read tcpdump -S -x text from stdin (portable fallback).")
    src.add_argument("--list-ifaces", action="store_true", help="List capture devices and exit.")
    parser.add_argument("--iface", help="Capture device (default: auto; 'any' on Linux).")
    parser.add_argument("--dry-run", action="store_true", help="Build/validate hands without DB insert.")
    parser.add_argument("--game", default="PLO4", help="Table category hint (PLO4, NLHE, ...).")
    parser.add_argument("--log-file", help="Tee all output to this file (used by the GUI tab).")
    parser.add_argument("--stop-file", help="Exit cleanly once this file exists (GUI stop signal).")
    parser.add_argument("--config-file", help="Explicit HUD_config.xml path (needed when launched elevated).")
    args = parser.parse_args()

    if args.log_file:
        _logf = open(args.log_file, "a", buffering=1, encoding="utf-8")  # noqa: SIM115
        sys.stdout = _Tee(sys.__stdout__, _logf)
        sys.stderr = _Tee(sys.__stderr__, _logf)

    if args.list_ifaces:
        _print_devices()
        return

    import os

    from fpdb_3_legacy.coinpoker_pcap import capture_live, open_offline

    stop = (lambda: bool(args.stop_file) and os.path.exists(args.stop_file)) if args.stop_file else None

    # Keep the handle alive for the whole capture.  The OS releases the lock on
    # normal exit and crashes, so stale lock files do not block future starts.
    _instance_lock = None
    if not args.dry_run and (args.live or args.stdin):
        try:
            _instance_lock = _acquire_instance_lock()
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)

    if args.live:
        events = _events_from_segments(capture_live(args.iface, BPF_FILTER, stop=stop))
    elif args.replay:
        events = _events_from_segments(open_offline(args.replay, BPF_FILTER))
    else:
        events = _events_from_lines(sys.stdin)

    try:
        run(events, dry_run=args.dry_run, table_category=args.game, config_file=args.config_file)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
        sys.exit(0)
    except OSError as exc:
        print(f"[ERROR] Capture failed: {exc}")
        print("[HINT] Live capture needs root/Administrator privileges (and Npcap on Windows).")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - surface any startup error into the log
        import traceback

        print(f"[ERROR] {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
