"""Tests for the CoinPoker live-capture reassembly and import pump.

These exercise the offline-testable parts of ``coinpoker_live_capture`` (the
sequence-tracked TCP reassembler and the hand pump's build/import gating)
without needing root or a live client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from fpdb_3_legacy.coinpoker_live_capture import (
    COINPOKER_SITE_ID,
    HandPump,
    StreamReassembler,
    _acquire_instance_lock,
    _Conn,
    _ensure_capture_file,
    _open_db,
    _Tee,
)
from fpdb_3_legacy.Exceptions import FpdbHandDuplicate
from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig

FIXTURE = Path(__file__).parent / "data" / "coinpoker_hand_events.json"

FRAME_A = b"\x80\x00\x03\x12\x00\x00"  # flags 0x80, len 3, body "\x12\x00\x00"
FRAME_B = b"\x80\x00\x02\xaa\xbb"  # flags 0x80, len 2, body "\xaa\xbb"


def _events() -> list[tuple]:
    return [tuple(e) for e in json.loads(FIXTURE.read_text())]


# --- sequence-tracked reassembly ---------------------------------------------


def test_conn_in_order_yields_frames() -> None:
    c = _Conn()
    c.add(100, FRAME_A + FRAME_B)
    assert c.pop_frames() == [(0x80, b"\x12\x00\x00"), (0x80, b"\xaa\xbb")]


def test_conn_reorders_out_of_order_segments() -> None:
    c = _Conn()
    c.add(100, FRAME_A)  # baseline; next_seq -> 106
    assert c.pop_frames() == [(0x80, b"\x12\x00\x00")]
    # FRAME_C after FRAME_B, but FRAME_C's segment arrives first.
    c.add(106 + len(FRAME_B), FRAME_A)  # stand-in "C" at seq 111 (ahead -> pending)
    assert c.pop_frames() == []
    c.add(106, FRAME_B)  # fills the gap; both drain in order
    assert c.pop_frames() == [(0x80, b"\xaa\xbb"), (0x80, b"\x12\x00\x00")]


def test_conn_drops_retransmission_duplicate() -> None:
    c = _Conn()
    c.add(100, FRAME_A)
    c.add(100, FRAME_A)  # exact retransmission -> ignored
    assert c.pop_frames() == [(0x80, b"\x12\x00\x00")]


def test_conn_trims_overlapping_retransmission() -> None:
    c = _Conn()
    c.add(100, b"ABCDEF")  # next_seq -> 106
    c.add(104, b"EFGH")  # overlaps last 2 bytes; only "GH" is new
    assert bytes(c.buf) == b"ABCDEFGH"
    assert c.next_seq == 108


def test_pop_frames_realigns_after_garbage() -> None:
    c = _Conn()
    c.buf.extend(b"\x11\x22" + FRAME_B)  # leading garbage before a valid marker
    assert c.pop_frames() == [(0x80, b"\xaa\xbb")]


def test_reassembler_ignores_non_game_ports() -> None:
    r = StreamReassembler()
    r.feed_line("01:00:00.0 IP6 2606::1.443 > 2a01::2.55291: Flags [P.], seq 1:5, length 4")
    r.feed_line("\t0x0000:  deadbeef aabbccdd")
    r.feed_line("01:00:00.1 IP6 x")
    assert r.conns == {}


def test_reassembler_routes_game_port_payload_into_conn() -> None:
    r = StreamReassembler()
    # payload = trailing `length` bytes of the packet hex.
    r.feed_line("01:00:00.0 IP6 2606::1.9000 > 2a01::2.55291: Flags [P.], seq 1000:1006, length 6")
    r.feed_line("\t0x0000:  aabb" + FRAME_B.hex())  # 2 junk + FRAME_B (5) = 7; last 6 keeps FRAME_B
    r.feed_line("01:00:00.1 IP6 next")  # boundary flush
    assert "9000->55291" in r.conns


# --- output tee (pythonw / no-console safety) --------------------------------


def test_tee_ignores_none_streams(tmp_path) -> None:
    # Under pythonw.exe (Windows GUI launch) sys.__stdout__ is None; the log
    # file must still receive output instead of the capture dying on write.
    log_path = tmp_path / "capture.log"
    with log_path.open("w", encoding="utf-8") as handle:
        tee = _Tee(None, handle)
        assert tee.write("hello\n") == len("hello\n")
        tee.flush()
    assert log_path.read_text(encoding="utf-8") == "hello\n"


def test_tee_writes_to_all_present_streams() -> None:
    import io

    a, b = io.StringIO(), io.StringIO()
    tee = _Tee(a, None, b)
    tee.write("x")
    assert a.getvalue() == "x"
    assert b.getvalue() == "x"


# --- import pump --------------------------------------------------------------


def test_hand_pump_imports_complete_hands_and_dedupes() -> None:
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=None, config=config, table_category="PLO4", dry_run=True)
    events = _events()

    first = pump.process(events)
    assert first == 2  # both captured hands are complete
    assert pump.imported == {"91426500343", "91426500344"}

    assert pump.process(events) == 0  # no re-import
    assert pump.prune(events) == []  # imported hands' events pruned


def test_pump_stamps_capture_time_instead_of_epoch(monkeypatch) -> None:
    # The stream carries no per-hand clock; an unstamped hand would default to
    # 1970 and vanish from the GUI's date-filtered graphs. The pump must stamp it.
    import datetime

    from fpdb_3_legacy.http_capture_hand_builder import CaptureNotImportableError

    seen: dict = {}

    def spy(hand_data, config):  # noqa: ANN001, ANN202 - test double
        seen["timestamp"] = hand_data.get("timestamp")
        raise CaptureNotImportableError  # stop after capturing the stamped value

    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture.build_fpdb_hand", spy)
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=None, config=config, table_category="PLO4", dry_run=True)

    pump.process(_events())

    assert isinstance(seen["timestamp"], datetime.datetime)
    assert seen["timestamp"].year >= 2020  # capture time, not the 1970 epoch


def test_live_capture_instance_lock_rejects_second_process(tmp_path) -> None:
    lock_path = str(tmp_path / "coinpoker-capture.lock")
    first = _acquire_instance_lock(lock_path)
    try:
        assert Path(lock_path).read_text() == str(os.getpid())
        with pytest.raises(RuntimeError, match=r"already running \(PID \d+\)"):
            _acquire_instance_lock(lock_path)
    finally:
        first.close()

    replacement = _acquire_instance_lock(lock_path)
    replacement.close()


def test_existing_capture_file_transaction_is_committed() -> None:
    db = Mock()
    db.get_id.return_value = 42

    assert _ensure_capture_file(db) == 42
    db.commit.assert_called_once_with()


def test_open_db_commits_sequence_repairs(monkeypatch) -> None:
    db = Mock()
    config = Mock()
    monkeypatch.setattr("fpdb_3_legacy.Configuration.Config", Mock(return_value=config))
    monkeypatch.setattr("fpdb_3_legacy.Database.Database", Mock(return_value=db))
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture.ensure_coinpoker_site", Mock())

    assert _open_db() == (db, config)
    db.repair_sequences.assert_called_once_with()
    db.commit.assert_called_once_with()


def test_hand_pump_treats_database_duplicate_as_skipped(monkeypatch, capsys) -> None:
    class Database:
        def resetBulkCache(self):
            return None

        def rollback(self):
            return None

    def duplicate(*_args, **_kwargs):
        raise FpdbHandDuplicate("140-existing")

    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture.import_fpdb_hand", duplicate)
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=Database(), config=config, table_category="PLO4")

    assert pump.process(_events()) == 2
    assert pump.failed == set()
    assert capsys.readouterr().out.count("[DUPLICATE]") == 2
