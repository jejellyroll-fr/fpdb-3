"""Three defects a review found in the live SwC capture path.

1. A deferred hand was only ever re-offered while the archive was still growing,
   but hands are deferred precisely when they are *finished* and something else
   refused them -- so the retry could not fire.
2. A failed native import left its uncommitted Hands row on the connection, and
   the retry then saw its own row as a duplicate and retired the hand.
3. Records from different injected clients carried no stream identity, so the
   reassembler spliced one client's plaintext onto another's partial message.
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.swc_native_capture import (
    NativeCaptureRecord,
    iter_capture_records,
    iter_protocol_messages,
)

HEADER = struct.Struct("=IHBBHHIQ")


def _record(payload: bytes, *, source_id: int = 0, connection_id: int = 0, port: int = 20013) -> bytes:
    """One capture record; source_id/connection_id are the stream identity."""
    return HEADER.pack(0x53574354, 1, 0, source_id, port, connection_id, len(payload), 1_750_000_000_123_456) + payload


def _framed(body: bytes) -> bytes:
    """A native protocol message: a little-endian u32 length then the body."""
    return len(body).to_bytes(4, "little") + body


# --------------------------------------------------------------------------
# 1. The retry has to be reachable on an idle archive.
# --------------------------------------------------------------------------


def _tailer(tmp_path, monkeypatch, hands):
    from fpdb_3_legacy import swc_native_capture
    from fpdb_3_legacy.GuiAutoImport import SwCNativeTailingThread

    monkeypatch.setattr(swc_native_capture, "iter_protocol_messages", lambda records: list(records))
    monkeypatch.setattr(swc_native_capture, "normalize_native_hands", lambda messages, raw_ref=None: hands)
    raw = tmp_path / "swc-native.raw"
    raw.write_bytes(_record(b"game-state"))
    return SwCNativeTailingThread(raw_path=raw), raw


def test_a_deferred_hand_is_re_offered_without_new_records(tmp_path, monkeypatch) -> None:
    """The reported defect: a finished hand writes no more records, ever."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailer(tmp_path, monkeypatch, [hand])

    assert thread.poll_once() == [hand]  # first offer
    assert thread.poll_once() == []  # unchanged snapshot, nothing due

    thread.retry_hand(hand)
    # The archive is idle from here on: no bytes are appended.
    monkeypatch.setattr(thread, "_retry_after", {thread._hand_key(hand): 0.0})

    assert thread.poll_once() == [hand], "a due retry must fire even with no new records"


def test_an_idle_archive_with_nothing_due_stays_cheap(tmp_path, monkeypatch) -> None:
    """The early return still guards the expensive normalize when nothing is due."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailer(tmp_path, monkeypatch, [hand])
    thread.poll_once()

    calls = []
    from fpdb_3_legacy import swc_native_capture

    monkeypatch.setattr(
        swc_native_capture,
        "normalize_native_hands",
        lambda messages, raw_ref=None: calls.append(1) or [hand],
    )
    assert thread.poll_once() == []
    assert calls == [], "no records and no due retry must not re-normalize"


def test_a_retired_hand_does_not_keep_waking_the_poll(tmp_path, monkeypatch) -> None:
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailer(tmp_path, monkeypatch, [hand])
    thread.poll_once()
    key = thread._hand_key(hand)
    thread._completed_keys.add(key)
    thread._retry_after[key] = 0.0

    assert thread._retry_is_due(1.0) is False


# --------------------------------------------------------------------------
# 2. A failed import must not leave an uncommitted row for the retry to trip on.
# --------------------------------------------------------------------------


def _native_hand() -> dict:
    return {"site": "SealsWithClubs", "hand_id": 42, "table_id": 1, "native_capture": True}


def _reaches_the_import(monkeypatch, mod):
    """Get past the completeness gate so the import itself runs."""
    monkeypatch.setattr(mod, "_enrich_existing_native_boards", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_native_public_import_copy", lambda h: dict(h))
    monkeypatch.setattr(mod, "build_fpdb_hand", lambda *a, **k: SimpleNamespace(dbid_hands=1))


def test_a_failed_native_import_rolls_back_before_the_retry(monkeypatch) -> None:
    """Otherwise the retry sees its own uncommitted Hands row as a duplicate."""
    from fpdb_3_legacy import http_capture_db_import as mod

    db = MagicMock()
    _reaches_the_import(monkeypatch, mod)

    def boom(*_a, **_k):
        msg = "HandsPlayers insert failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(mod, "import_fpdb_hand", boom)

    with pytest.raises(RuntimeError, match="HandsPlayers"):
        mod._import_native_hand(db, _native_hand(), doinsert=True)

    db.rollback.assert_called_once()


def test_a_rollback_that_fails_does_not_mask_the_real_error(monkeypatch) -> None:
    from fpdb_3_legacy import http_capture_db_import as mod

    db = MagicMock()
    db.rollback.side_effect = OSError("connection gone")
    _reaches_the_import(monkeypatch, mod)

    def boom(*_a, **_k):
        msg = "the original failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(mod, "import_fpdb_hand", boom)

    with pytest.raises(RuntimeError, match="the original failure"):
        mod._import_native_hand(db, _native_hand(), doinsert=True)


def test_a_successful_native_import_does_not_roll_back(monkeypatch) -> None:
    from fpdb_3_legacy import http_capture_db_import as mod

    db = MagicMock()
    _reaches_the_import(monkeypatch, mod)
    monkeypatch.setattr(mod, "import_fpdb_hand", lambda *a, **k: None)

    result = mod._import_native_hand(db, _native_hand(), doinsert=True)

    assert result.status == "imported"
    db.rollback.assert_not_called()


# --------------------------------------------------------------------------
# 3. Streams from different clients must not be spliced together.
# --------------------------------------------------------------------------


def test_records_carry_the_stream_identity_the_tap_writes() -> None:
    raw = _record(b"x", source_id=7, connection_id=1234)
    record = next(iter(iter_capture_records(__import__("io").BytesIO(raw))))

    assert record.source_id == 7
    assert record.connection_id == 1234


def test_two_clients_on_one_port_do_not_splice_into_one_message() -> None:
    """The observed corruption: one client's payload completing another's frame.

    Client A writes the first half of a 20-byte message and stops (its process
    ended). Client B, a different process that reused the same peer port, then
    writes a complete 4-byte message. Keyed only by peer port, B's bytes finish
    A's frame and both messages are lost; keyed by stream, B's message decodes.
    """
    message_a = _framed(b"A" * 20)
    whole_of_b = _framed(b"BBBB")

    records = [
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, message_a[:12], connection_id=0, source_id=1),
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, whole_of_b, connection_id=0, source_id=2),
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, message_a[12:], connection_id=0, source_id=1),
    ]
    messages = list(iter_protocol_messages(iter(records)))

    assert [m.payload for m in messages] == [b"BBBB", b"A" * 20]
    assert [m.source_id for m in messages] == [2, 1]


def test_one_client_still_reassembles_across_records() -> None:
    """The split-message path a single stream depends on must keep working."""
    body = _framed(b"C" * 10)
    records = [
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[:6], connection_id=5, source_id=1),
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[6:], connection_id=5, source_id=1),
    ]

    assert [m.payload for m in iter_protocol_messages(iter(records))] == [b"C" * 10]


def test_two_sockets_in_one_client_stay_separate() -> None:
    """Two connections of one process can share a peer port; the socket differs."""
    message_d = _framed(b"D" * 20)
    whole_e = _framed(b"EEEE")
    records = [
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, message_d[:12], connection_id=11, source_id=1),
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, whole_e, connection_id=12, source_id=1),
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, message_d[12:], connection_id=11, source_id=1),
    ]

    assert [m.payload for m in iter_protocol_messages(iter(records))] == [b"EEEE", b"D" * 20]


def test_an_archive_written_before_stream_ids_still_decodes() -> None:
    """Old records carry zeros in both fields and must behave exactly as before."""
    body = _framed(b"F" * 8)
    records = [
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[:5], connection_id=0, source_id=0),
        NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[5:], connection_id=0, source_id=0),
    ]

    assert [m.payload for m in iter_protocol_messages(iter(records))] == [b"F" * 8]
