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
Live (needs root)::

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
from fpdb_3_legacy.coinpoker_protocol import iter_game_events
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    HttpCaptureHandConfig,
    build_fpdb_hand,
    import_fpdb_hand,
)

COINPOKER_SITE_ID = 140
GAME_PORTS = ("9000", "7002")
_HDR_RE = re.compile(r"\.(?P<sport>\d+) > \S+?\.(?P<dport>\d+):.* length (?P<len>\d+)$")
_HEX_RE = re.compile(r"\s+0x[0-9a-f]+:\s+((?:[0-9a-f]{2,4}\s?)+)")


class StreamReassembler:
    """Reassemble server->client TCP payloads from ``tcpdump -x`` text lines.

    We only need the server->client direction (game state pushes). Payload is the
    trailing ``length`` bytes of each packet (tcpdump prints from the IP header,
    so the app payload is the tail). Buffers are keyed per connection so a
    reconnect starts a fresh stream.
    """

    def __init__(self) -> None:
        self.buffers: dict[str, bytearray] = {}
        self._cur_key: str | None = None
        self._cur_len = 0
        self._hex: list[str] = []

    def _flush(self) -> bytes | None:
        if self._cur_key is None:
            return None
        allb = bytes.fromhex("".join(self._hex))
        payload = allb[-self._cur_len :] if 0 < self._cur_len <= len(allb) else b""
        key = self._cur_key
        self._cur_key, self._cur_len, self._hex = None, 0, []
        if payload:
            self.buffers.setdefault(key, bytearray()).extend(payload)
            return payload
        return None

    def feed_line(self, line: str) -> str | None:
        """Feed one tcpdump text line. Returns the connection key that grew, if any."""
        if line and not line[0].isspace():
            grew = self._flush()
            m = _HDR_RE.search(line)
            grown_key = self._cur_key if grew else None
            if m and m.group("sport") in GAME_PORTS:
                self._cur_key = f"{m.group('sport')}->{m.group('dport')}"
                self._cur_len = int(m.group("len"))
                self._hex = []
            else:
                self._cur_key = None
            return grown_key
        m = _HEX_RE.match(line)
        if m and self._cur_key is not None:
            self._hex.append(m.group(1).replace(" ", ""))
        return None


def _events_from_buffers(reassembler: StreamReassembler) -> list[tuple]:
    """Decode all game events currently present across every connection buffer."""
    events: list[tuple] = []
    for buf in reassembler.buffers.values():
        events.extend(iter_game_events(bytes(buf)))
    return events


def _iter_tcpdump_lines_live() -> Iterator[str]:
    cmd = [
        "tcpdump", "-i", "any", "-l", "-n", "-x",
        f"tcp port {GAME_PORTS[0]} or tcp port {GAME_PORTS[1]}",
    ]
    print(f"[INFO] Starting: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)  # noqa: S603
    if proc.stdout is None:
        raise RuntimeError("tcpdump produced no stdout (is it installed / are you root?)")
    yield from proc.stdout


def _iter_tcpdump_lines_replay(pcap: str) -> Iterator[str]:
    cmd = ["tcpdump", "-r", pcap, "-n", "-x", f"tcp port {GAME_PORTS[0]} or tcp port {GAME_PORTS[1]}"]
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
    since_check = 0
    for line in lines:
        grew = reassembler.feed_line(line.rstrip("\n"))
        since_check += 1
        # Re-evaluate hands periodically (server pushes many small frames).
        if grew and since_check >= 20:
            since_check = 0
            pump.process(_events_from_buffers(reassembler))
    # Final sweep (covers replay mode / shutdown).
    pump.process(_events_from_buffers(reassembler))
    print(f"[INFO] Done. Hands imported/built this run: {len(pump.imported)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CoinPoker live HUD capture feed")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="Sniff live traffic (requires root/sudo).")
    src.add_argument("--replay", metavar="PCAP", help="Replay a saved pcap instead of sniffing.")
    parser.add_argument("--dry-run", action="store_true", help="Build/validate hands without DB insert.")
    parser.add_argument("--game", default="PLO4", help="Table category hint (PLO4, NLHE, ...).")
    args = parser.parse_args()

    if args.live:
        lines = _iter_tcpdump_lines_live()
    else:
        lines = _iter_tcpdump_lines_replay(args.replay)

    try:
        run(lines, dry_run=args.dry_run, table_category=args.game)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
