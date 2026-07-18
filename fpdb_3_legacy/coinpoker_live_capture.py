#!/usr/bin/env python3
"""Live CoinPoker HUD feed: sniff the poker TCP stream, decode, import to DB.

CoinPoker's poker protocol is a plaintext binary stream on raw TCP
(poker-nlb:9000 and :7002), opened by the Electron main process. This module
sniffs that traffic with ``tcpdump`` (root required, like DriveHUD's capture),
reassembles the server->client byte stream, decodes game events
(``coinpoker_protocol``), builds fpdb hands (``coinpoker_hand_builder`` ->
``http_capture_hand_builder``) and imports each completed hand into the
configured fpdb database so the existing HUD can read it.

Modes
-----
Live, recommended (only tcpdump runs as root; the importer keeps your $HOME and
DB config)::

    sudo tcpdump -i any -l -n -S -x 'tcp port 9000 or tcp port 7002' \
        | python -m fpdb_3_legacy.coinpoker_live_capture --stdin

Live, self-spawned tcpdump (needs to run the whole process as root)::

    sudo -E python -m fpdb_3_legacy.coinpoker_live_capture --live

Replay a saved pcap (no root; for testing the decode/build/import path)::

    python -m fpdb_3_legacy.coinpoker_live_capture --replay /tmp/cp9000.pcap --dry-run

``--dry-run`` builds and validates hands without writing to the database.
"""

from __future__ import annotations

import argparse
import re
import subprocess
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
GAME_PORTS = ("9000", "7002")
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

    def _flush(self) -> list[tuple]:
        if self._cur_key is None:
            return []
        allb = bytes.fromhex("".join(self._hex))
        payload = allb[-self._cur_len :] if 0 < self._cur_len <= len(allb) else b""
        key, seq = self._cur_key, self._cur_seq
        self._cur_key, self._cur_len, self._hex = None, 0, []
        if not payload:
            return []
        conn = self.conns.setdefault(key, _Conn())
        conn.add(seq, payload)
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

    def feed_line(self, line: str) -> list[tuple]:
        """Feed one tcpdump text line; return newly decoded game events."""
        if line and not line[0].isspace():
            events = self._flush()
            m = _HDR_RE.search(line)
            if m and m.group("sport") in GAME_PORTS:
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


def _iter_tcpdump_lines_live() -> Iterator[str]:
    cmd = [
        "tcpdump", "-i", "any", "-l", "-n", "-S", "-x",
        f"tcp port {GAME_PORTS[0]} or tcp port {GAME_PORTS[1]}",
    ]
    print(f"[INFO] Starting: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)  # noqa: S603
    if proc.stdout is None:
        raise RuntimeError("tcpdump produced no stdout (is it installed / are you root?)")
    yield from proc.stdout


def _iter_tcpdump_lines_replay(pcap: str) -> Iterator[str]:
    cmd = ["tcpdump", "-r", pcap, "-n", "-S", "-x", f"tcp port {GAME_PORTS[0]} or tcp port {GAME_PORTS[1]}"]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)  # noqa: S603
    yield from out.stdout.splitlines()


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

    def __init__(self, db, config, *, table_category: str = "PLO4", dry_run: bool = False) -> None:
        self.db = db
        self.config = config
        self.table_category = table_category
        self.dry_run = dry_run
        self.imported: set[str] = set()

    def process(self, events: list[tuple]) -> int:
        new = 0
        for hand_data in build_hands(events, self.table_category):
            hid = hand_data["hand_id"]
            if hid in self.imported:
                continue
            try:
                hand = build_fpdb_hand(hand_data, config=self.config)
            except CaptureNotImportableError:
                continue  # hand not complete yet (no winner/collection)
            self.imported.add(hid)
            new += 1
            if self.dry_run or self.db is None:
                print(f"[DRY-RUN] hand #{hid} built ({len(hand.players)} players) — not inserted")
                continue
            try:
                import_fpdb_hand(hand, self.db, file_id=0, doinsert=True)
                self.db.commit()
                print(f"[IMPORTED] hand #{hid}")
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] import of #{hid} failed: {exc}")
        return new

    def prune(self, events: list[tuple]) -> list[tuple]:
        """Drop events belonging to already-imported hands to bound memory."""
        return [e for e in events if e[1] not in self.imported]


def _open_db():
    from fpdb_3_legacy import Configuration, Database

    config = Configuration.Config()
    db = Database.Database(config)
    ensure_coinpoker_site(db)
    return db, config


def run(lines: Iterable[str], *, dry_run: bool, table_category: str) -> None:
    if dry_run:
        db, config = None, HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    else:
        db, config = _open_db()

    reassembler = StreamReassembler()
    pump = HandPump(db, config, table_category=table_category, dry_run=dry_run)
    print("[INFO] === CoinPoker live feed active ===")
    events: list[tuple] = []
    since_check = 0
    for line in lines:
        new_events = reassembler.feed_line(line.rstrip("\n"))
        if not new_events:
            continue
        events.extend(new_events)
        since_check += len(new_events)
        # Re-evaluate hands periodically (server pushes many small events).
        if since_check >= 20:
            since_check = 0
            if pump.process(events):
                events = pump.prune(events)
    # Final sweep (covers replay mode / shutdown).
    pump.process(events)
    print(f"[INFO] Done. Hands imported/built this run: {len(pump.imported)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CoinPoker live HUD capture feed")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="Sniff live traffic (runs tcpdump itself; whole process needs root).")
    src.add_argument("--stdin", action="store_true", help="Read tcpdump -x output from stdin (pipe a root tcpdump into this).")
    src.add_argument("--replay", metavar="PCAP", help="Replay a saved pcap instead of sniffing.")
    parser.add_argument("--dry-run", action="store_true", help="Build/validate hands without DB insert.")
    parser.add_argument("--game", default="PLO4", help="Table category hint (PLO4, NLHE, ...).")
    args = parser.parse_args()

    if args.live:
        lines: Iterable[str] = _iter_tcpdump_lines_live()
    elif args.stdin:
        lines = sys.stdin
    else:
        lines = _iter_tcpdump_lines_replay(args.replay)

    try:
        run(lines, dry_run=args.dry_run, table_category=args.game)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
