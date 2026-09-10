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
import time
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

    monkeypatch.setattr(swc_native_capture.NativeProtocolStream, "feed", lambda _self, records: list(records))
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


# --------------------------------------------------------------------------
# 4. A duplicate must be reported as a duplicate, not as a fresh import.
# --------------------------------------------------------------------------


def test_a_duplicate_native_hand_is_reported_as_a_duplicate(monkeypatch) -> None:
    """The generic rollback handler must not swallow the duplicate's own result."""
    from fpdb_3_legacy import http_capture_db_import as mod
    from fpdb_3_legacy.Exceptions import FpdbHandDuplicate

    db = MagicMock()
    _reaches_the_import(monkeypatch, mod)

    def already_there(*_a, **_k):
        raise FpdbHandDuplicate("already imported")

    monkeypatch.setattr(mod, "import_fpdb_hand", already_there)

    result = mod._import_native_hand(db, _native_hand(), doinsert=True)

    assert result.status == "duplicate"
    db.rollback.assert_called_once()


def test_a_repaired_existing_hand_is_reported_as_updated(monkeypatch) -> None:
    from fpdb_3_legacy import http_capture_db_import as mod
    from fpdb_3_legacy.Exceptions import FpdbHandDuplicate

    db = MagicMock()
    _reaches_the_import(monkeypatch, mod)
    monkeypatch.setattr(mod, "_enrich_existing_native_boards", lambda *_a, **_k: 4242)

    def already_there(*_a, **_k):
        raise FpdbHandDuplicate("already imported")

    monkeypatch.setattr(mod, "import_fpdb_hand", already_there)

    result = mod._import_native_hand(db, _native_hand(), doinsert=True)

    assert result.status == "updated"
    assert result.row_id == 4242


# --------------------------------------------------------------------------
# 5. A layout is as unusable off the top-left as off the bottom-right.
# --------------------------------------------------------------------------


def test_positions_far_before_the_origin_are_rejected() -> None:
    from fpdb_3_legacy.Configuration import layout_reference_fits

    assert layout_reference_fits(792, 546, [(-5000, -5000)]) is False
    assert layout_reference_fits(792, 546, [(100, -5000)]) is False
    assert layout_reference_fits(792, 546, [(-5000, 100)]) is False


def test_a_block_parked_just_off_the_top_left_is_still_accepted() -> None:
    """The shipped layouts carry x="-4"; that is a user choice, not corruption."""
    from fpdb_3_legacy.Configuration import layout_reference_fits

    assert layout_reference_fits(792, 546, [(-4, -4), (681, 221)]) is True


def test_the_load_repair_lifts_blocks_back_onto_the_table() -> None:
    from xml.dom import minidom

    from fpdb_3_legacy.Configuration import Layout

    node = minidom.parseString(
        """<layout max="2" height="546" width="792">
             <location seat="1" x="-5000" y="-5000"/>
             <location seat="2" x="400" y="300"/>
           </layout>""",
    ).documentElement
    layout = Layout(node)

    # Lifted to the allowed underhang rather than left thousands of pixels away.
    assert layout.location[1][0] >= -792 * 0.5
    assert layout.location[1][1] >= -546 * 0.5
    assert layout.location[2] == (400, 300)


# --------------------------------------------------------------------------
# 6. A client that could not be injected has to be named.
# --------------------------------------------------------------------------


def test_stream_ids_are_distinct_per_client(tmp_path) -> None:
    from fpdb_3_legacy import swc_windows_inject as inj

    assignment = inj.write_stream_ids(tmp_path, [1024, 4])

    assert len(set(assignment.values())) == 2
    assert 0 not in assignment.values(), "0 means 'unassigned' to the tap"
    for pid, stream_id in assignment.items():
        # The sidecar also records the process start time, so only the id line is
        # pinned here (see test_a_recycled_pid_does_not_inherit_an_id).
        assert f"stream={stream_id}\n" in (tmp_path / f"swc-native-{pid}.cfg").read_text(encoding="ascii")


def test_a_partly_injected_client_set_says_which_client_was_missed(monkeypatch, tmp_path) -> None:
    """Otherwise "capture active" hides a client whose hands never arrive."""
    from fpdb_3_legacy import swc_native_capture, swc_tap_build
    from fpdb_3_legacy import swc_windows_inject as inj

    monkeypatch.setattr(swc_native_capture.platform, "system", lambda: "Windows")
    monkeypatch.setattr(swc_native_capture, "build_tap", lambda **_: tmp_path / "tap.dll")
    monkeypatch.setattr(swc_tap_build, "build_injector", lambda **_: tmp_path / "inj.exe")
    monkeypatch.setattr(swc_native_capture, "BUILD_DIR", tmp_path, raising=False)
    monkeypatch.setattr(inj, "write_capture_config", lambda *_a, **_k: tmp_path / "c.cfg")
    monkeypatch.setattr(inj, "write_stream_ids", lambda *_a, **_k: {})
    monkeypatch.setattr(inj, "find_client_pids", lambda *_a, **_k: [11, 22])
    monkeypatch.setattr(
        inj,
        "inject_into_pid",
        lambda _i, _d, pid: inj.InjectionResult(pid=pid, ok=(pid == 11), detail="ok" if pid == 11 else "access denied"),
    )
    monkeypatch.setattr(inj, "wait_for_hooks", lambda _p, pids: dict.fromkeys(pids, "tap-hooked"))

    status = swc_native_capture.attach_to_windows_client()

    assert "22" in status, "the client that was not injected must be named"
    assert "access denied" in status


# --------------------------------------------------------------------------
# 7. Hands.fileId is a real foreign key on the server backends.
# --------------------------------------------------------------------------


def test_a_native_hand_is_attached_to_a_real_files_row(monkeypatch) -> None:
    """file_id=0 violates Hands.fileId -> Files.id on MySQL/PostgreSQL."""
    from fpdb_3_legacy import http_capture_db_import as mod

    mod._native_capture_file_ids.clear()
    db = MagicMock()
    db.get_id.return_value = None
    db.storeFile.return_value = 77
    _reaches_the_import(monkeypatch, mod)
    seen = {}
    monkeypatch.setattr(mod, "import_fpdb_hand", lambda _h, _db, file_id, doinsert: seen.update(file_id=file_id))

    mod._import_native_hand(db, _native_hand(), doinsert=True)

    assert seen["file_id"] == 77
    db.storeFile.assert_called_once()


def test_the_files_row_is_created_once_per_connection(monkeypatch) -> None:
    from fpdb_3_legacy import http_capture_db_import as mod

    mod._native_capture_file_ids.clear()
    db = MagicMock()
    db.get_id.return_value = 5
    _reaches_the_import(monkeypatch, mod)
    monkeypatch.setattr(mod, "import_fpdb_hand", lambda *a, **k: None)

    mod._import_native_hand(db, _native_hand(), doinsert=True)
    mod._import_native_hand(db, _native_hand(), doinsert=True)

    assert db.get_id.call_count == 1, "the Files row is looked up once and reused"


def test_a_database_without_files_helpers_still_imports(monkeypatch) -> None:
    """A stub connection must not become an error path of its own."""
    from fpdb_3_legacy import http_capture_db_import as mod

    mod._native_capture_file_ids.clear()
    assert mod._ensure_capture_file(object()) == 0


# --------------------------------------------------------------------------
# 8. Board repair writes, so its failure needs a rollback too.
# --------------------------------------------------------------------------


def test_a_failing_board_repair_rolls_back(monkeypatch) -> None:
    """Otherwise PostgreSQL keeps the shared connection in an aborted transaction."""
    from fpdb_3_legacy import http_capture_db_import as mod

    db = MagicMock()

    def boom(*_a, **_k):
        msg = "board UPDATE failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(mod, "_enrich_existing_native_boards", boom)

    with pytest.raises(RuntimeError, match="board UPDATE"):
        mod._import_native_hand(db, _native_hand(), doinsert=True)

    db.rollback.assert_called_once()


# --------------------------------------------------------------------------
# 9. An imported live hand has to reach the HUD.
# --------------------------------------------------------------------------


def test_an_imported_live_hand_is_pushed_to_the_hud() -> None:
    """HUD_main queues hands only from its ZMQ receiver."""
    from fpdb_3_legacy.GuiAutoImport import GuiAutoImport

    sent = []

    class _Importer:
        callHud = True
        zmq_sender = SimpleNamespace(send_hand_id=sent.append)

    gui = SimpleNamespace(importer=_Importer())
    GuiAutoImport._notify_hud_of_hand(gui, 4321)

    assert sent == [4321]


def test_nothing_is_pushed_when_the_hud_is_switched_off() -> None:
    from fpdb_3_legacy.GuiAutoImport import GuiAutoImport

    sent = []

    class _Importer:
        callHud = False
        zmq_sender = SimpleNamespace(send_hand_id=sent.append)

    gui = SimpleNamespace(importer=_Importer())
    GuiAutoImport._notify_hud_of_hand(gui, 4321)
    GuiAutoImport._notify_hud_of_hand(SimpleNamespace(importer=None), 4321)

    assert sent == []


# --------------------------------------------------------------------------
# 10. A stream id already handed out must stay with its process.
# --------------------------------------------------------------------------


def test_a_reattach_keeps_the_id_an_injected_client_already_holds(tmp_path) -> None:
    """LoadLibraryW does not re-run DllMain, so that client keeps its old id."""
    from fpdb_3_legacy import swc_windows_inject as inj

    first = inj.write_stream_ids(tmp_path, [100, 200])
    # 100 exits; a new client appears. 200 is still injected and still in memory.
    second = inj.write_stream_ids(tmp_path, [200, 300])

    assert second[200] == first[200], "an injected client keeps the id it is using"
    assert second[300] != second[200], "the new client must not reuse a live id"


def test_stream_ids_survive_a_repeated_attach(tmp_path) -> None:
    from fpdb_3_legacy import swc_windows_inject as inj

    first = inj.write_stream_ids(tmp_path, [7, 9])
    assert inj.write_stream_ids(tmp_path, [7, 9]) == first


# --------------------------------------------------------------------------
# 11. A message split across two polls must survive the batch boundary.
# --------------------------------------------------------------------------


def test_a_message_split_across_batches_is_reassembled() -> None:
    """SwC sends the 4-byte length in an SSL_read of its own, so this is routine."""
    from fpdb_3_legacy.swc_native_capture import NativeProtocolStream

    body = _framed(b"Z" * 30)
    stream = NativeProtocolStream()

    first = stream.feed([NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[:4])])
    second = stream.feed([NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[4:])])

    assert [m.payload for m in first] == [], "the length prefix alone completes nothing"
    assert [m.payload for m in second] == [b"Z" * 30]


def test_a_half_message_does_not_raise_at_a_batch_boundary() -> None:
    """iter_protocol_messages finish()es and raises; a tailer must not."""
    from fpdb_3_legacy.swc_native_capture import NativeProtocolStream

    stream = NativeProtocolStream()
    assert stream.feed([NativeCaptureRecord(datetime.now(UTC), "received", 20013, _framed(b"Q" * 9)[:6])]) == []


def test_the_tailer_keeps_its_decoders_between_polls(tmp_path, monkeypatch) -> None:
    """End to end: the archive grows by half a message, then by the rest."""
    from fpdb_3_legacy import swc_native_capture
    from fpdb_3_legacy.GuiAutoImport import SwCNativeTailingThread

    seen: list[bytes] = []
    monkeypatch.setattr(
        swc_native_capture,
        "normalize_native_hands",
        lambda messages, raw_ref=None: seen.extend(m.payload for m in messages) or [],
    )

    body = _framed(b"W" * 24)
    raw = tmp_path / "swc-native.raw"
    raw.write_bytes(_record(body[:4]))
    thread = SwCNativeTailingThread(raw_path=raw)

    thread.poll_once()
    assert seen == [], "nothing is complete yet"

    with raw.open("ab") as handle:
        handle.write(_record(body[4:]))
    thread.poll_once()

    assert seen == [b"W" * 24], "the second batch completed the message"


# --------------------------------------------------------------------------
# 12. Trimming the history must not drop a live table's descriptor.
# --------------------------------------------------------------------------


def test_a_table_descriptor_survives_the_rolling_trim(tmp_path, monkeypatch) -> None:
    """normalize_native_hands rebuilds its table map from the retained list alone."""
    from fpdb_3_legacy import swc_native_capture
    from fpdb_3_legacy.GuiAutoImport import SwCNativeTailingThread

    descriptor = SimpleNamespace(payload=b"table-info", peer_port=1, connection_id=0, source_id=0)
    filler = [SimpleNamespace(payload=b"x", peer_port=1, connection_id=0, source_id=0) for _ in range(5)]

    monkeypatch.setattr(
        swc_native_capture,
        "extract_table_info",
        lambda m: SimpleNamespace(table_id=42) if m.payload == b"table-info" else None,
    )
    monkeypatch.setattr(
        swc_native_capture.NativeProtocolStream,
        "feed",
        lambda _self, _records: [descriptor, *filler],
    )
    handed: list[list] = []
    monkeypatch.setattr(
        swc_native_capture,
        "normalize_native_hands",
        lambda messages, raw_ref=None: handed.append(list(messages)) or [],
    )

    raw = tmp_path / "swc-native.raw"
    raw.write_bytes(_record(b"anything"))
    thread = SwCNativeTailingThread(raw_path=raw)
    thread.MAX_RETAINED_MESSAGES = 2  # force the trim to eat the descriptor
    thread.poll_once()

    assert descriptor in handed[0], "the descriptor must outlive the trimmed history"


# --------------------------------------------------------------------------
# 13. A repaired reference must be usable, and stale options must be announced.
# --------------------------------------------------------------------------


def test_a_zero_reference_with_no_positive_coordinate_is_still_repaired() -> None:
    """Aux_Base refuses to scale by zero, so the repair has to leave a usable one."""
    from xml.dom import minidom

    from fpdb_3_legacy.Configuration import Layout

    node = minidom.parseString(
        """<layout max="2" height="0" width="0">
             <location seat="1" x="0" y="0"/>
             <location seat="2" x="-10" y="-10"/>
           </layout>""",
    ).documentElement
    layout = Layout(node)

    assert layout.width >= 1
    assert layout.height >= 1


def test_changed_capture_options_are_reported_as_needing_a_restart(tmp_path) -> None:
    from fpdb_3_legacy import swc_windows_inject as inj

    assert inj.capture_config_changed(tmp_path, port=0, include_outbound=False) is False

    inj.write_capture_config(tmp_path, port=0, include_outbound=False)
    assert inj.capture_config_changed(tmp_path, port=0, include_outbound=False) is False
    assert inj.capture_config_changed(tmp_path, port=20020, include_outbound=False) is True
    assert inj.capture_config_changed(tmp_path, port=0, include_outbound=True) is True


# --------------------------------------------------------------------------
# 14. Attaching mid-connection must not poison the stream forever.
# --------------------------------------------------------------------------


def test_a_stream_joined_mid_message_realigns() -> None:
    """The in-flight SSL_read returned before the hook, so we start mid-payload."""
    from fpdb_3_legacy.swc_native_capture import NativeProtocolStream

    stream = NativeProtocolStream()
    orphan = b"\xff\xff\xff\x7f" + b"payload-with-no-length-in-front"
    dropped = stream.feed([NativeCaptureRecord(datetime.now(UTC), "received", 20013, orphan)])
    assert dropped == [], "unframed bytes yield nothing"

    good = stream.feed([NativeCaptureRecord(datetime.now(UTC), "received", 20013, _framed(b"REAL"))])
    assert [m.payload for m in good] == [b"REAL"], "the next framed record is decoded"


def test_realigning_does_not_raise_on_every_later_poll() -> None:
    """Persistent decoders made an unreadable length permanent; it must not be."""
    from fpdb_3_legacy.swc_native_capture import NativeProtocolStream

    stream = NativeProtocolStream()
    bad = NativeCaptureRecord(datetime.now(UTC), "received", 20013, b"\xff\xff\xff\x7f" + b"junk")
    for _ in range(3):
        assert stream.feed([bad]) == []

    assert [m.payload for m in stream.feed([NativeCaptureRecord(datetime.now(UTC), "received", 20013, _framed(b"OK"))])] == [b"OK"]


def test_reading_a_finished_archive_still_reports_a_bad_length() -> None:
    """Resynchronising is for a live tap; an archive's corruption is worth seeing."""
    records = [NativeCaptureRecord(datetime.now(UTC), "received", 20013, b"\xff\xff\xff\x7f" + b"junk")]
    with pytest.raises(ValueError, match="too large"):
        list(iter_protocol_messages(iter(records)))


# --------------------------------------------------------------------------
# 15. An id must not be recycled while the archive still carries its records.
# --------------------------------------------------------------------------


def test_an_id_is_not_reused_after_its_client_exits(tmp_path) -> None:
    """The archive is append-only: the departed client's records still hold it."""
    from fpdb_3_legacy import swc_windows_inject as inj

    first = inj.write_stream_ids(tmp_path, [100])
    second = inj.write_stream_ids(tmp_path, [200])  # 100 has exited

    assert second[200] != first[100]


def test_a_fresh_archive_releases_the_id_pool(tmp_path) -> None:
    from fpdb_3_legacy import swc_windows_inject as inj

    first = inj.write_stream_ids(tmp_path, [100])
    assert inj.reset_stream_ids(tmp_path) == 1

    assert inj.write_stream_ids(tmp_path, [200])[200] == first[100], "ids start over"


# --------------------------------------------------------------------------
# 16. A bomb pot is what the hand did, not what the table is called.
# --------------------------------------------------------------------------


def test_an_ordinary_blind_hand_on_a_bomb_pot_table_is_not_a_bomb_pot() -> None:
    """Only 8 of 72 captured hands on such a table were actually bomb pots."""
    from fpdb_3_legacy.swc_native_capture import _native_board_output

    blinds = [{"action": "small_blind", "amount_native": 2}, {"action": "big_blind", "amount_native": 4}]
    output = _native_board_output((("9s", "Jh", "4h", "Kh", "5c"),), blinds)

    assert output["bomb_pot"] == 0


def test_a_bomb_pot_reports_its_ante_total_in_cents() -> None:
    """The same unit the hand-history importer stores, not a boolean 1."""
    from fpdb_3_legacy.swc_native_capture import _native_board_output

    antes = [{"action": "ante", "amount_native": 12} for _ in range(3)]
    output = _native_board_output((("2c", "7h", "Ad", "Ac", "6d"),), antes)

    assert output["bomb_pot"] == 36


def test_antes_alongside_blinds_are_a_tournament_level_not_a_bomb_pot() -> None:
    from fpdb_3_legacy.swc_native_capture import _native_board_output

    evidence = [
        {"action": "ante", "amount_native": 5},
        {"action": "small_blind", "amount_native": 10},
        {"action": "big_blind", "amount_native": 20},
    ]

    assert _native_board_output((("2c", "7h", "Ad"),), evidence)["bomb_pot"] == 0


# --------------------------------------------------------------------------
# 17. An outage longer than the retry budget must not retire a hand.
# --------------------------------------------------------------------------


def test_a_transient_refusal_keeps_its_place_past_the_budget(tmp_path, monkeypatch) -> None:
    """A database that is away comes back; the hand has to still be waiting."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailer(tmp_path, monkeypatch, [hand])
    thread.poll_once()
    key = thread._hand_key(hand)

    for _ in range(thread.MAX_RETRY_OFFERS + 5):
        thread.retry_hand(hand, transient=True)

    assert key in thread._retry_after, "a transient refusal never gives up on the hand"
    assert thread._retry_after[key] - time.monotonic() <= thread.RETRY_BACKOFF_CAP_SECONDS


def test_a_hand_the_importer_judged_unusable_still_stops(tmp_path, monkeypatch) -> None:
    """Its verdict cannot change while its snapshot does not, so the budget holds."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailer(tmp_path, monkeypatch, [hand])
    thread.poll_once()
    key = thread._hand_key(hand)

    for _ in range(thread.MAX_RETRY_OFFERS + 1):
        thread.retry_hand(hand)

    assert key not in thread._retry_after


def test_a_transient_retry_is_re_offered_after_the_budget(tmp_path, monkeypatch) -> None:
    """End to end: the outage outlasts the budget, the hand still comes back."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailer(tmp_path, monkeypatch, [hand])
    thread.poll_once()

    for _ in range(thread.MAX_RETRY_OFFERS + 3):
        thread.retry_hand(hand, transient=True)
    thread._retry_after[thread._hand_key(hand)] = 0.0  # its delay has elapsed

    assert thread.poll_once() == [hand]


# --------------------------------------------------------------------------
# 18. Resetting the id pool must not renumber a resident DLL.
# --------------------------------------------------------------------------


def test_a_running_client_keeps_its_id_through_a_pool_reset(tmp_path) -> None:
    """Its DLL is resident and goes on stamping the id it read at load time."""
    from fpdb_3_legacy import swc_windows_inject as inj

    assigned = inj.write_stream_ids(tmp_path, [100, 200])
    inj.reset_stream_ids(tmp_path, keep_pids=[200])  # 100 exited, 200 still runs

    after = inj.write_stream_ids(tmp_path, [200, 300])
    assert after[200] == assigned[200], "the resident client keeps its id"
    assert after[300] != after[200]


def test_a_reset_with_no_client_running_frees_everything(tmp_path) -> None:
    from fpdb_3_legacy import swc_windows_inject as inj

    inj.write_stream_ids(tmp_path, [100, 200])
    assert inj.reset_stream_ids(tmp_path) == 2


# --------------------------------------------------------------------------
# 19. Two clients watching one table must not be merged into one timeline.
# --------------------------------------------------------------------------


def test_two_sources_are_normalized_separately(monkeypatch) -> None:
    """Merged, their independently timed copies become one impossible timeline."""
    from fpdb_3_legacy import swc_native_capture

    seen: list[set[int]] = []

    def fake_one_source(messages, *, raw_ref):
        seen.append({m.source_id for m in messages})
        return [{"table_id": 1, "hand_id": 9, "steps": [1] * len(messages)}]

    monkeypatch.setattr(swc_native_capture, "_normalize_native_hands_one_source", fake_one_source)

    messages = [
        swc_native_capture.NativeProtocolMessage(datetime.now(UTC), b"a", source_id=1),
        swc_native_capture.NativeProtocolMessage(datetime.now(UTC), b"b", source_id=2),
        swc_native_capture.NativeProtocolMessage(datetime.now(UTC), b"c", source_id=2),
    ]
    hands = swc_native_capture.normalize_native_hands(messages, raw_ref="x")

    assert seen == [{1}, {2}], "each source is normalized on its own"
    assert len(hands) == 1, "the same hand is emitted once"
    assert len(hands[0]["steps"]) == 2, "the more complete copy wins"


def test_a_single_source_takes_the_direct_path(monkeypatch) -> None:
    """The normal case must not pay for the partitioning."""
    from fpdb_3_legacy import swc_native_capture

    calls = []
    monkeypatch.setattr(
        swc_native_capture,
        "_normalize_native_hands_one_source",
        lambda messages, *, raw_ref: calls.append(len(messages)) or [],
    )
    messages = [swc_native_capture.NativeProtocolMessage(datetime.now(UTC), b"a", source_id=3) for _ in range(3)]

    assert swc_native_capture.normalize_native_hands(messages, raw_ref="x") == []
    assert calls == [3], "one pass over every message"


# --------------------------------------------------------------------------
# 20. Alignment must be proven, not guessed from a plausible length.
# --------------------------------------------------------------------------


def test_a_plausible_but_wrong_length_does_not_swallow_later_records() -> None:
    """A class-22 body starting 16 00 07 00 announces a 458,774-byte frame."""
    from fpdb_3_legacy.swc_native_capture import NativeProtocolStream

    stream = NativeProtocolStream()
    mid_message = b"\x16\x00\x07\x00" + b"body bytes with no length in front"
    assert stream.feed([NativeCaptureRecord(datetime.now(UTC), "received", 20013, mid_message)]) == []

    # The correctly framed records that follow must still decode, not be eaten as
    # filler for the 458 KB frame that was never really there.
    body = _framed(b"REAL MESSAGE")
    got = stream.feed(
        [
            NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[:4]),
            NativeCaptureRecord(datetime.now(UTC), "received", 20013, body[4:]),
        ],
    )
    assert [m.payload for m in got] == [b"REAL MESSAGE"]


def test_a_length_only_record_anchors_the_stream() -> None:
    """Half the records in a real capture are exactly a 4-byte length."""
    from fpdb_3_legacy.swc_native_capture import NativeProtocolDecoder

    assert NativeProtocolDecoder._anchors_a_message((12).to_bytes(4, "little")) is True


def test_a_whole_message_in_one_record_anchors_the_stream() -> None:
    from fpdb_3_legacy.swc_native_capture import NativeProtocolDecoder

    assert NativeProtocolDecoder._anchors_a_message(_framed(b"abcd")) is True


def test_a_record_that_proves_nothing_is_not_an_anchor() -> None:
    from fpdb_3_legacy.swc_native_capture import NativeProtocolDecoder

    anchors = NativeProtocolDecoder._anchors_a_message
    assert anchors(b"\x16\x00\x07\x00" + b"x" * 10) is False, "length disagrees with the record"
    assert anchors(b"\x00\x00\x00\x00") is False, "a zero length proves nothing"
    assert anchors(b"ab") is False, "too short to hold a length"


# --------------------------------------------------------------------------
# 21. The duplicate that wins must be the one that can be imported.
# --------------------------------------------------------------------------


def _envelope(*, steps: int, importable: bool = False, collections: int = 0) -> dict:
    return {
        "table_id": 1,
        "hand_id": 9,
        "steps": [1] * steps,
        "collections": [1] * collections,
        "metadata": {"importability": {"importable": importable}},
        "game": {"fpdb_supported": importable},
    }


def test_the_importable_copy_wins_over_an_equally_long_one(monkeypatch) -> None:
    """Collections and actions arrive in their own messages and add no steps."""
    from fpdb_3_legacy import swc_native_capture

    per_source = {1: _envelope(steps=5), 2: _envelope(steps=5, importable=True, collections=2)}
    monkeypatch.setattr(
        swc_native_capture,
        "_normalize_native_hands_one_source",
        lambda messages, *, raw_ref: [per_source[next(iter({m.source_id for m in messages}))]],
    )
    messages = [
        swc_native_capture.NativeProtocolMessage(datetime.now(UTC), b"a", source_id=1),
        swc_native_capture.NativeProtocolMessage(datetime.now(UTC), b"b", source_id=2),
    ]

    [hand] = swc_native_capture.normalize_native_hands(messages, raw_ref="x")
    assert hand["metadata"]["importability"]["importable"] is True


def test_evidence_breaks_a_tie_before_snapshot_count() -> None:
    from fpdb_3_legacy.swc_native_capture import _native_envelope_rank

    assert _native_envelope_rank(_envelope(steps=5, collections=2)) > _native_envelope_rank(_envelope(steps=9))


# --------------------------------------------------------------------------
# 22. A recycled pid is not the same client.
# --------------------------------------------------------------------------


def test_a_recycled_pid_does_not_inherit_an_id(tmp_path, monkeypatch) -> None:
    """Windows reuses pids, and a sidecar outlives the process it was written for."""
    from fpdb_3_legacy import swc_windows_inject as inj

    monkeypatch.setattr(inj, "process_start_time", lambda _pid: 1000.0)
    first = inj.write_stream_ids(tmp_path, [4242])

    # Same pid, different run: a later process that Windows handed the number to.
    monkeypatch.setattr(inj, "process_start_time", lambda _pid: 5000.0)
    second = inj.write_stream_ids(tmp_path, [4242])

    assert second[4242] != first[4242], "the new process must not inherit the id"


def test_the_same_run_keeps_its_id(tmp_path, monkeypatch) -> None:
    from fpdb_3_legacy import swc_windows_inject as inj

    monkeypatch.setattr(inj, "process_start_time", lambda _pid: 1000.0)
    first = inj.write_stream_ids(tmp_path, [4242])

    assert inj.write_stream_ids(tmp_path, [4242])[4242] == first[4242]


def test_a_sidecar_without_a_start_time_keeps_its_id(tmp_path, monkeypatch) -> None:
    """Written before start times were recorded; renumbering a resident DLL is worse."""
    from fpdb_3_legacy import swc_windows_inject as inj

    (tmp_path / "swc-native-4242.cfg").write_text("stream=7\n", encoding="ascii")
    monkeypatch.setattr(inj, "process_start_time", lambda _pid: 1000.0)

    assert inj.write_stream_ids(tmp_path, [4242])[4242] == 7
