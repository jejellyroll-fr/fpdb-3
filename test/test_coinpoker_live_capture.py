"""Tests for the CoinPoker live-capture reassembly and import pump.

These exercise the offline-testable parts of ``coinpoker_live_capture`` (TCP
payload reassembly from tcpdump text, and the hand pump's build/import gating)
without needing root or a live client.
"""

from __future__ import annotations

import json
from pathlib import Path

from fpdb_3_legacy.coinpoker_live_capture import (
    COINPOKER_SITE_ID,
    HandPump,
    StreamReassembler,
)
from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig

FIXTURE = Path(__file__).parent / "data" / "coinpoker_hand_events.json"


def _events() -> list[tuple]:
    return [tuple(e) for e in json.loads(FIXTURE.read_text())]


def test_reassembler_takes_trailing_payload_from_server_stream() -> None:
    # A server->client packet (source port 9000), payload = trailing `length` bytes.
    header = "01:00:00.0 IP6 2606::1.9000 > 2a01::2.55291: Flags [P.], seq 1:5, length 4"
    hexline = "\t0x0000:  deadbeef aabbccdd"  # 8 bytes; last 4 == payload
    r = StreamReassembler()
    r.feed_line(header)
    r.feed_line(hexline)
    r.feed_line("01:00:00.1 IP6 x")  # boundary line flushes the previous packet
    assert bytes(r.buffers["9000->55291"]) == bytes.fromhex("aabbccdd")


def test_reassembler_ignores_non_game_ports() -> None:
    r = StreamReassembler()
    r.feed_line("01:00:00.0 IP6 2606::1.443 > 2a01::2.55291: Flags [P.], length 4")
    r.feed_line("\t0x0000:  deadbeef aabbccdd")
    r.feed_line("01:00:00.1 IP6 x")
    assert r.buffers == {}


def test_hand_pump_imports_complete_hand_once() -> None:
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=None, config=config, table_category="PLO4", dry_run=True)
    events = _events()

    first = pump.process(events)
    assert first == 1  # complete hand 343 built; incomplete 344 gated out
    assert "91426500343" in pump.imported
    assert "91426500344" not in pump.imported

    # Re-processing the same events must not re-import.
    assert pump.process(events) == 0
