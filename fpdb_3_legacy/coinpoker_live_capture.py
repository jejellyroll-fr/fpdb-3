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
import re
import sys
from typing import Iterable, Iterator

from fpdb_3_legacy.coinpoker_hand_builder import build_hands
from fpdb_3_legacy.coinpoker_protocol import decode_frame
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    HttpCaptureHandConfig,
    build_fpdb_hand,
    import_fpdb_hand,
)

COINPOKER_SITE_ID = 140
# CoinPoker game servers: TCP 9000 (poker cluster) plus a per-table 70xx range
# (7001, 7002, ... vary by table), so match the whole range rather than fixed ports.
GAME_PORTS = ("9000", "7002")  # kept for reference; see _is_game_port / BPF_FILTER
_GAME_PORT_RANGE = range(7000, 7101)


def _is_game_port(port: int) -> bool:
    return port == 9000 or port in _GAME_PORT_RANGE
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
    """Write to several streams at once (used to mirror output to a log file)."""

    def __init__(self, *streams) -> None:
        self._streams = streams

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
        from fpdb_3_legacy.coinpoker_protocol import game_event_from_object

        self._game_event = game_event_from_object
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
        for flags, body in conn.pop_frames():
            try:
                obj = decode_frame(flags, body)
            except Exception:  # noqa: BLE001 - best-effort decode; skip malformed frames
                continue
            ev = self._game_event(obj) if obj is not None else None
            if ev is not None:
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


BPF_FILTER = "tcp portrange 7000-7100 or tcp port 9000"


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

    def __init__(self, db, config, *, table_category: str = "PLO4", dry_run: bool = False, file_id: int = 0) -> None:
        self.db = db
        self.config = config
        self.table_category = table_category
        self.dry_run = dry_run
        self.file_id = file_id
        self.imported: set[str] = set()
        self.failed: set[str] = set()

    def process(self, events: list[tuple]) -> int:
        new = 0
        for hand_data in build_hands(events, self.table_category):
            hid = hand_data["hand_id"]
            if hid in self.imported or hid in self.failed:
                continue
            try:
                hand = build_fpdb_hand(hand_data, config=self.config)
            except CaptureNotImportableError:
                continue  # hand not complete yet (no winner/collection); retry later
            except Exception as exc:  # noqa: BLE001 - one malformed hand must not kill the feed
                self.failed.add(hid)
                print(f"[WARN] skipped hand #{hid}: {exc}")
                continue
            self.imported.add(hid)
            new += 1
            if self.dry_run or self.db is None:
                print(f"[DRY-RUN] hand #{hid} built ({len(hand.players)} players) — not inserted")
                continue
            try:
                import_fpdb_hand(hand, self.db, file_id=self.file_id, doinsert=True)
                self.db.commit()
                print(f"[IMPORTED] hand #{hid}")
            except Exception as exc:  # noqa: BLE001
                # Roll back so an aborted transaction doesn't block later hands.
                with contextlib.suppress(Exception):
                    self.db.rollback()
                self.failed.add(hid)
                print(f"[ERROR] import of #{hid} failed: {exc}")
        return new

    def prune(self, events: list[tuple]) -> list[tuple]:
        """Drop events of already-handled (imported or failed) hands to bound memory."""
        done = self.imported | self.failed
        return [e for e in events if e[1] not in done]


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
            import datetime

            now = datetime.datetime.utcnow()
            file_id = db.storeFile([name, "CoinPoker", now, now, 0, 0, 0, 0, 0, 0, 0, False])
            db.commit()
        return int(file_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not create capture Files row: {exc}")
        with contextlib.suppress(Exception):
            db.rollback()
        return 0


def _open_db(config_file: str | None = None):
    from fpdb_3_legacy import Configuration, Database

    config = Configuration.Config(file=config_file or _resolve_config_file())
    db = Database.Database(config)
    ensure_coinpoker_site(db)
    return db, config


def run(events: Iterable[tuple], *, dry_run: bool, table_category: str, config_file: str | None = None) -> None:
    file_id = 0
    if dry_run:
        db, config = None, HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    else:
        db, config = _open_db(config_file)
        file_id = _ensure_capture_file(db)

    pump = HandPump(db, config, table_category=table_category, dry_run=dry_run, file_id=file_id)
    print("[INFO] === CoinPoker live feed active ===")
    accumulated: list[tuple] = []
    since_check = 0
    for event in events:
        accumulated.append(event)
        since_check += 1
        # Re-evaluate hands periodically (the server pushes many small events).
        if since_check >= 20:
            since_check = 0
            pump.process(accumulated)
            accumulated = pump.prune(accumulated)
    pump.process(accumulated)  # final sweep (covers replay / shutdown)
    print(f"[INFO] Done. Hands imported/built this run: {len(pump.imported)}")


def _print_devices() -> None:
    from fpdb_3_legacy.coinpoker_pcap import list_devices

    print("Available capture devices:")
    for name, desc, flags in list_devices():
        print(f"  {name:20} {desc}  (flags=0x{flags:x})")


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
