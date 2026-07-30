"""Tests for the CoinPoker live-capture reassembly and import pump.

These exercise the offline-testable parts of ``coinpoker_live_capture`` (the
sequence-tracked TCP reassembler and the hand pump's build/import gating)
without needing root or a live client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from fpdb_3_legacy.coinpoker_hand_builder import _build_one, build_hands
from fpdb_3_legacy.coinpoker_live_capture import (
    COINPOKER_SITE_ID,
    MAX_RESULT_ATTEMPTS,
    HandPump,
    RawEventArchive,
    StreamReassembler,
    _acquire_instance_lock,
    _Conn,
    _ensure_capture_file,
    _is_game_port,
    _known_aof_tables,
    _make_equity_coordinator,
    _open_db,
    _Tee,
    run,
)
from fpdb_3_legacy.Exceptions import FpdbHandDuplicate
from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig

FIXTURE = Path(__file__).parent / "data" / "coinpoker_hand_events.json"

FRAME_A = b"\x80\x00\x03\x12\x00\x00"  # flags 0x80, len 3, body "\x12\x00\x00"
FRAME_B = b"\x80\x00\x02\xaa\xbb"  # flags 0x80, len 2, body "\xaa\xbb"


@pytest.fixture(autouse=True)
def _isolate_hand_archive(tmp_path, monkeypatch):
    """Keep the captured-hand archive out of the real ~/.fpdb during tests."""
    monkeypatch.setattr(
        "fpdb_3_legacy.coinpoker_live_capture._default_archive_dir",
        lambda: str(tmp_path / "capture-archive"),
    )


def _events() -> list[tuple]:
    return [tuple(e) for e in json.loads(FIXTURE.read_text())]


def test_ante_seat_refresh_is_not_imported_as_negative_raise() -> None:
    """A stale Raise caption on the ante snapshot is protocol state, not action."""
    info = {
        "gameId": 1234500001,
        "sbAmount": 1000,
        "bbAmount": 2000,
        "anteAmount": 250,
        "sbSeatId": 1,
        "bbSeatId": 2,
        "initTimeStamp": 1_700_000_000_000,
    }
    seats = {
        "seatResponseDataList": [
            {"seatId": 1, "userName": "sb", "userChips": 10000, "betAmout": 0},
            {"seatId": 2, "userName": "bb", "userChips": 10000, "betAmout": 0},
            {"seatId": 3, "userName": "raiser", "userChips": 10000, "betAmout": 0},
        ],
    }
    events = [
        ("game.pre_hand_start_info", 0, info),
        ("game.seatInfo", 0, seats),
        ("game.seat", 0, {"seatId": 1, "userName": "sb", "caption": "Raise", "betAmout": 250}),
        ("game.seat", 0, {"seatId": 2, "userName": "bb", "caption": "Raise", "betAmout": 250}),
        ("game.seat", 0, {"seatId": 3, "userName": "raiser", "caption": "Raise", "betAmout": 250}),
        ("game.seat", 0, {"seatId": 3, "userName": "raiser", "caption": "Raise", "betAmout": 5000}),
        ("game.seat", 0, {"seatId": 2, "userName": "bb", "caption": "Allin", "betAmout": 5000}),
    ]

    hand = _build_one("1234500001", events, "holdem")

    assert hand is not None
    assert [a for a in hand["actions"] if a["type"] == "raises"] == [
        {"type": "raises", "player": "raiser", "street": "PREFLOP", "to": "5000"},
    ]
    assert [a for a in hand["actions"] if a["type"] == "calls"] == [
        {"type": "calls", "player": "bb", "street": "PREFLOP", "amount": "2750"},
    ]


def test_raw_event_archive_preserves_event_payload(tmp_path) -> None:
    archive = RawEventArchive(str(tmp_path))
    event = ("tournament.result", "123", {"rank": 90, "winnings": 0})

    archive.append(event)

    files = list(tmp_path.glob("coinpoker-raw-*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text())
    assert record["event"] == "tournament.result"
    assert record["hand_id"] == "123"
    assert record["payload"] == {"rank": 90, "winnings": 0}
    assert record["captured_at"]


def test_reassembler_keeps_non_game_tournament_envelope(monkeypatch) -> None:
    monkeypatch.setattr(
        "fpdb_3_legacy.coinpoker_live_capture.decode_frame",
        lambda _flags, _body: {"decoded": True},
    )
    reassembler = StreamReassembler()
    reassembler._protocol_event = lambda _obj: (  # noqa: SLF001
        "tournament.result",
        None,
        {"rank": 535, "winnings": 0},
    )
    reassembler.conns["3001->50000"] = Mock(
        add=Mock(),
        pop_frames=Mock(return_value=[(0x80, b"\x00")]),
    )

    events = reassembler.add_segment("3001->50000", 1, b"x")

    assert events == [
        (
            "tournament.result",
            None,
            {"rank": 535, "winnings": 0, "_coinpokerServerPort": 3001},
        ),
    ]


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


def test_tournament_ports_are_captured() -> None:
    assert _is_game_port(3000)
    assert _is_game_port(3001)

    r = StreamReassembler()
    r.feed_line("01:00:00.0 IP6 2606::1.3001 > 2a01::2.55291: Flags [P.], seq 1000:1006, length 6")
    r.feed_line("\t0x0000:  aabb" + FRAME_B.hex())
    r.feed_line("01:00:00.1 IP6 next")
    assert "3001->55291" in r.conns


def test_tournament_port_is_attached_to_decoded_event(monkeypatch) -> None:
    monkeypatch.setattr(
        "fpdb_3_legacy.coinpoker_live_capture.decode_frame",
        lambda _flags, _body: {"decoded": True},
    )
    reassembler = StreamReassembler()
    reassembler._protocol_event = lambda _obj: ("game.pre_hand_start_info", "H", {"sbAmount": 10})

    events = reassembler.add_segment("3001->55291", 1000, FRAME_A)

    assert events[0][2]["_coinpokerServerPort"] == 3001


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


def test_hand_pump_imports_complete_hands_and_dedupes(tmp_path) -> None:
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=None, config=config, table_category="PLO4", dry_run=True, archive_dir=str(tmp_path))
    events = _events()

    first = pump.process(events)
    assert first == 2  # both captured hands are complete
    assert pump.imported == {"91426500343", "91426500344"}

    assert pump.process(events) == 0  # no re-import
    assert pump.prune(events) == []  # imported hands' events pruned


def test_pump_stamps_capture_time_instead_of_epoch(monkeypatch, tmp_path) -> None:
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
    pump = HandPump(db=None, config=config, table_category="PLO4", dry_run=True, archive_dir=str(tmp_path))

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


def test_instance_lock_never_locks_the_pid_bytes_on_windows(tmp_path, monkeypatch) -> None:
    """The Windows branch must lock a byte past the PID payload.

    Windows byte-range locks deny the range to every *other* handle, so locking
    byte 0 made the PID unreadable: reading the lock file raised PermissionError
    and the "already running (PID n)" diagnostic could never name the holder.
    Forced here with a fake msvcrt so the regression is caught on any platform.
    """
    import sys
    import types

    locked_offsets: list[int] = []

    fake_msvcrt = types.ModuleType("msvcrt")
    fake_msvcrt.LK_NBLCK = 2

    def _locking(fd: int, _mode: int, _nbytes: int) -> None:
        locked_offsets.append(os.lseek(fd, 0, os.SEEK_CUR))

    fake_msvcrt.locking = _locking
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(os, "name", "nt")

    lock_path = str(tmp_path / "coinpoker-capture.lock")
    handle = _acquire_instance_lock(lock_path)
    try:
        # Plain open(): pathlib would reinterpret the POSIX path under os.name="nt".
        with open(lock_path, encoding="ascii") as holder_file:
            pid = holder_file.read()
        assert pid == str(os.getpid())  # payload stays plainly readable
        assert locked_offsets, "the Windows branch must take a byte-range lock"
        assert locked_offsets[0] >= len(pid), "locked byte overlaps the PID payload"
    finally:
        handle.close()


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


def test_live_hand_is_notified_before_its_equity_job_is_queued(monkeypatch) -> None:
    order = []
    db = Mock()
    db.resetBulkCache.side_effect = lambda: order.append("reset")
    db.commit.side_effect = lambda: order.append("commit")
    notify = Mock()
    notify.send_hand_id.side_effect = lambda _hand_id: order.append("hand-notify")
    coordinator = Mock()
    coordinator.submit_hand.side_effect = lambda *_args: order.append("equity-queue")
    hand = Mock(players=[(1, "hero", 2)])

    def imported(built_hand, *_args, **_kwargs):
        order.append("import")
        built_hand.dbid_hands = 41
        built_hand.aof_decisions = ("decision",)
        built_hand.aof_decision_ids = (7,)

    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture.import_fpdb_hand", imported)
    pump = HandPump(
        db,
        Mock(),
        notify=notify,
        equity_coordinator=coordinator,
    )

    pump._insert_hand(hand, "site-41")

    assert order == ["reset", "import", "commit", "hand-notify", "equity-queue"]
    coordinator.submit_hand.assert_called_once_with(hand, ("decision",), (7,))


def test_live_worker_enables_range_and_action_models_without_a_second_service(monkeypatch) -> None:
    captured = {}
    service = object()

    def coordinator(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "fpdb_3_legacy.coinpoker_live_capture.AsyncEquityService",
        lambda: service,
    )
    monkeypatch.setattr(
        "fpdb_3_legacy.coinpoker_live_capture.KnownCardsAnalysisCoordinator",
        coordinator,
    )
    notify = Mock()

    _make_equity_coordinator(Mock(), notify)

    assert captured["args"][0] is service
    assert captured["kwargs"]["notify_hand"] is notify.send_hand_id
    assert captured["kwargs"]["population_model"].identifier == "population_observed"
    assert captured["kwargs"]["action_model"].identifier == "population_action_frequency"


def test_an_equity_queue_failure_never_marks_a_committed_hand_failed(monkeypatch) -> None:
    db = Mock()
    hand = Mock(players=[(1, "hero", 2)], dbid_hands=42, aof_decisions=(), aof_decision_ids=())
    coordinator = Mock()
    coordinator.submit_hand.side_effect = RuntimeError("worker unavailable")
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture.import_fpdb_hand", lambda *_args, **_kwargs: None)
    pump = HandPump(db, Mock(), equity_coordinator=coordinator)

    pump._insert_hand(hand, "site-42")

    assert pump.failed == set()
    db.rollback.assert_not_called()


def test_captured_hands_are_archived_as_text(tmp_path) -> None:
    """A live capture has no source file, so the built hand must be archived.

    Once the packets are consumed nothing remains to check winnings against the
    room: the hand text is not stored in the database either (Hands has no text
    column and RawHands is never written). Each built hand is therefore rendered
    to a dated file so it stays auditable and re-importable.
    """
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(
        db=None,
        config=config,
        table_category="PLO4",
        dry_run=True,
        archive_dir=str(tmp_path),
    )

    assert pump.process(_events()) == 2

    archives = sorted(tmp_path.glob("coinpoker-*.txt"))
    assert archives, "the built hands must be written to a dated archive"
    text = archives[0].read_text(encoding="utf-8")
    assert "91426500343" in text and "91426500344" in text  # both hands
    assert "*** SUMMARY ***" in text  # full rendering
    assert "collected" in text  # winnings are auditable


def test_archive_failure_never_breaks_the_feed(tmp_path) -> None:
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("", encoding="utf-8")  # a file where a directory is needed
    pump = HandPump(db=None, config=config, table_category="PLO4", dry_run=True, archive_dir=str(blocked))

    assert pump.process(_events()) == 2  # hands still processed


# --- the finishing places -----------------------------------------------------
#
# The room announces where everyone finished once the tournament closes, after
# the last hand. Nothing is left to carry it, so the pump writes the places
# straight onto the tournament's players.

from fpdb_3_legacy.coinpoker_hand_builder import TOURNAMENT_RESULT_EVENT


def _winner_event(*winners: tuple) -> tuple:
    return (
        TOURNAMENT_RESULT_EVENT,
        None,
        {"winnerList": [{"rank": rank, "name": name, "prize": prize} for rank, name, prize in winners]},
    )


def _join(table: str, tournament: str, name: str = "Step [3] to 565 Main Event [1E]") -> tuple:
    return (
        "tournamentlobby.join_table",
        None,
        {"tableName": f"{name} {table}", "roomProperties": {"id": tournament, "tournamentName": name}},
    )


_REGULARS = ("jeje1976", "Alisey", "a", "b", "c", "boom")


def _pump_that_knows_a_tournament(db, *joins: tuple, seated: dict[str, tuple[str, ...]] | None = None) -> HandPump:
    """A pump told which tournament it is playing, the way the room tells it.

    A tournament is known by its join *and* by who was seen playing it, since
    the closing announcement is tied back to a tournament through its players.
    Unless a test says otherwise, everyone it names was at every table.
    """
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=db, config=config, table_category="PLO4")
    pump._remember_tournaments(list(joins) or [_join("1160391", "1160377")])
    for table, tour_no in pump._tournaments_by_table.items():
        names = (seated or {}).get(tour_no, _REGULARS)
        pump._remember_tournament_players(
            {
                "tournament": {"tour_no": tour_no, "table_id": table},
                "players": [{"name": name} for name in names],
            },
        )
    return pump


def test_the_places_reach_the_tournament_players() -> None:
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db)

    recorded = pump.record_tournament_results([_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))])

    assert recorded == 2
    db.updateTourneyPlayerResult.assert_any_call("CoinPoker", "1160377", "jeje1976", 1)
    assert db.commit.call_count == 2


def test_only_the_place_is_written(capsys) -> None:
    """No winnings, whatever the prize reads like.

    The unit and currency a number here would be in are not established, and
    the update coalesces, so the winnings column keeps whatever it held.
    """
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db)

    pump.record_tournament_results([_winner_event((1, "jeje1976", "565.50"), (2, "Alisey", "282.75"))])

    db.updateTourneyPlayerResult.assert_any_call("CoinPoker", "1160377", "jeje1976", 1)
    assert all(len(c.args) == 4 for c in db.updateTourneyPlayerResult.call_args_list)


def test_the_places_are_written_once_however_many_sweeps_see_them() -> None:
    # Every sweep re-reads the same events, and the announcement stays in them.
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db)
    events = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]

    assert pump.record_tournament_results(events) == 2
    assert pump.record_tournament_results(events) == 0
    assert db.updateTourneyPlayerResult.call_count == 2


def test_a_player_the_database_does_not_know_is_stepped_over() -> None:
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [False, True, True]
    pump = _pump_that_knows_a_tournament(db)

    recorded = pump.record_tournament_results(
        [_winner_event((1, "a stranger", "Ticket"), (2, "jeje1976", "Ticket"), (3, "Alisey", "Ticket"))],
    )

    assert recorded == 2


def test_one_failing_player_does_not_cost_the_others_their_place(capsys) -> None:
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [RuntimeError("gone"), True]
    pump = _pump_that_knows_a_tournament(db)

    recorded = pump.record_tournament_results([_winner_event((1, "boom", "Ticket"), (2, "jeje1976", "Ticket"))])

    assert recorded == 1
    assert "could not record boom" in capsys.readouterr().out


def test_places_announced_without_a_tournament_are_reported(capsys) -> None:
    db = Mock()
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=db, config=config, table_category="PLO4")

    assert pump.record_tournament_results([_winner_event((1, "jeje1976", "Ticket"))]) == 0
    assert "seen in no tournament" in capsys.readouterr().out
    assert not db.updateTourneyPlayerResult.called


def test_places_announced_matching_two_tournaments_are_refused(capsys) -> None:
    """The announcement names neither a tournament nor a table, only players.

    When the same player was seen in two of the capture's tournaments, the
    players no longer say which one is finishing. Filing the places on a guess
    would land them on someone else's entry and look like a real result, so
    nothing is filed until it is certain.
    """
    db = Mock()
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
    )

    assert pump.record_tournament_results([_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]) == 0
    assert "too close to tell them apart" in capsys.readouterr().out
    assert not db.updateTourneyPlayerResult.called


def test_a_regular_seen_in_both_does_not_make_the_announcement_ambiguous() -> None:
    """Sharing a player is not sharing a tournament.

    Regulars turn up in several of an evening's tournaments -- a real
    announcement of 35 places brushed against three of them, on 9, 3 and 2
    shared players. The one these people were actually playing is the one
    that shares the most of them.
    """
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
        seated={"81499": ("jeje1976", "Alisey", "Silwin"), "81498": ("jeje1976", "Kandinsky")},
    )

    # Announced: the three of 81499, of whom one also played 81498.
    places = pump.record_tournament_results(
        [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"), (3, "Silwin", "Ticket"))],
    )

    assert places == 3
    assert {c.args[1] for c in db.updateTourneyPlayerResult.call_args_list} == {"81499"}


def test_a_lead_of_one_player_is_not_a_correlation(capsys) -> None:
    """Three shared against two is a regular's whim, not an identification.

    The strict maximum alone would file the whole announcement on that, and a
    place filed on the wrong tournament lands on someone else's entry and
    reads as a real result.
    """
    db = Mock()
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
        seated={"81499": ("jeje1976", "Alisey", "Silwin"), "81498": ("jeje1976", "Alisey", "Mirek")},
    )

    places = pump.record_tournament_results(
        [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"), (3, "Silwin", "Ticket"))],
    )

    assert places == 0
    assert "too close to tell them apart" in capsys.readouterr().out
    assert not db.updateTourneyPlayerResult.called


def test_a_single_shared_player_is_not_a_correlation(capsys) -> None:
    # One regular in common with the only tournament on the books says nothing
    # about whose announcement this is.
    db = Mock()
    pump = _pump_that_knows_a_tournament(db, seated={"1160377": ("jeje1976", "Alisey")})

    places = pump.record_tournament_results(
        [_winner_event((1, "jeje1976", "Ticket"), (2, "Kandinsky", "Ticket"), (3, "Mirek", "Ticket"))],
    )

    assert places == 0
    assert "too close to tell them apart" in capsys.readouterr().out


def test_a_clear_lead_over_a_shared_regular_is_filed() -> None:
    # The shape of the real capture: 35 places announced, brushing three
    # tournaments on 9, 3 and 2 shared players. Nine is the obvious answer.
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
        seated={
            "81499": ("jeje1976", "Alisey", "Silwin", "Mirek", "Kandinsky"),
            "81498": ("jeje1976", "Alisey"),
        },
    )

    places = pump.record_tournament_results(
        [
            _winner_event(
                (1, "jeje1976", "Ticket"),
                (2, "Alisey", "Ticket"),
                (3, "Silwin", "Ticket"),
                (4, "Mirek", "Ticket"),
                (5, "Kandinsky", "Ticket"),
            ),
        ],
    )

    assert places == 5
    assert {c.args[1] for c in db.updateTourneyPlayerResult.call_args_list} == {"81499"}


def test_two_tournaments_sharing_the_lead_are_refused(capsys) -> None:
    # Nothing tells them apart, so nothing is filed.
    db = Mock()
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
        seated={"81499": ("jeje1976", "Alisey"), "81498": ("jeje1976", "Alisey")},
    )

    assert pump.record_tournament_results([_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]) == 0
    assert "too close to tell them apart" in capsys.readouterr().out
    assert not db.updateTourneyPlayerResult.called


def test_two_announcements_in_one_sweep_are_answered_separately() -> None:
    """Both can land inside the same twenty events.

    Read as one list their players name no tournament -- half belong to each
    -- so the correlation refuses and both tournaments lose their places.
    """
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
        seated={"81499": ("jeje1976", "Alisey"), "81498": ("Kandinsky", "Mirek")},
    )

    places = pump.record_tournament_results(
        [
            _winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket")),
            _winner_event((1, "Kandinsky", "Ticket"), (2, "Mirek", "Ticket")),
        ],
    )

    assert places == 4
    assert db.updateTourneyPlayerResult.call_args_list == [
        call("CoinPoker", "81499", "jeje1976", 1),
        call("CoinPoker", "81499", "Alisey", 2),
        call("CoinPoker", "81498", "Kandinsky", 1),
        call("CoinPoker", "81498", "Mirek", 2),
    ]


def test_a_better_correlation_later_does_not_move_a_filed_announcement() -> None:
    """Correlation only sharpens as hands come in, and it can change its mind.

    An announcement tied to one tournament and already written there must not
    follow it: the places would end up split across two tournaments, half
    right and half wrong, which is worse than either.
    """
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [True, True, False]
    pump = _pump_that_knows_a_tournament(db, seated={"1160377": ("jeje1976", "Alisey")})
    announcement = [
        _winner_event(
            (1, "jeje1976", "Ticket"),
            (2, "Alisey", "Ticket"),
            (3, "Silwin", "Ticket"),
            (4, "Mirek", "Ticket"),
            (5, "Kandinsky", "Ticket"),
        ),
    ]

    # Two of the five were seen at 1160377; nothing else is known, so it wins.
    assert pump.record_tournament_results(announcement) == 2

    # A tournament turns up that seated all five -- a clearly better match.
    pump._remember_tournaments([_join("1161142", "81498", name="Step [2] to 565 Main Event [1E]")])
    pump._remember_tournament_players(
        {
            "tournament": {"tour_no": "81498", "table_id": "1161142"},
            "players": [{"name": n} for n in ("jeje1976", "Alisey", "Silwin", "Mirek", "Kandinsky")],
        },
    )

    db.updateTourneyPlayerResult.side_effect = [True, True, True]
    pump.record_tournament_results([])

    assert {c.args[1] for c in db.updateTourneyPlayerResult.call_args_list} == {"1160377"}


def test_an_answered_announcement_stops_being_work() -> None:
    # Filed or refused, it is done: kept on the books it would be re-read on
    # every sweep for the rest of the run, and re-offered to the database.
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db)
    filed = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]
    foreign = [_winner_event((1, "carol", "Ticket"), (2, "dave", "Ticket"))]

    assert pump.record_tournament_results(filed) == 2
    for _ in range(MAX_RESULT_ATTEMPTS):
        pump.record_tournament_results(foreign)

    assert pump._pending_results == []
    # And neither is taken up again when the same events come round.
    assert pump.record_tournament_results([*filed, *foreign]) == 0
    assert db.updateTourneyPlayerResult.call_count == 2


def test_a_refused_announcement_is_never_claimed_by_a_later_tournament() -> None:
    """The lobby broadcasts the results of tournaments you did not play.

    A real capture picked up a 20-place announcement for one of them. Kept
    waiting for a correlation, it stays on the books for the rest of the run
    and the next tournament with those players takes it -- writing twenty
    strangers' places onto a tournament they were never in. A refusal has to
    be final.
    """
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db, seated={"1160377": ("jeje1976", "Alisey")})
    foreign = [_winner_event((1, "carol", "Ticket"), (2, "dave", "Ticket"))]

    for _ in range(MAX_RESULT_ATTEMPTS):
        assert pump.record_tournament_results(foreign) == 0

    # A later tournament happens to seat exactly those players.
    pump._remember_tournaments([_join("1161142", "81498", name="Step [2] to 565 Main Event [1E]")])
    pump._remember_tournament_players(
        {
            "tournament": {"tour_no": "81498", "table_id": "1161142"},
            "players": [{"name": "carol"}, {"name": "dave"}],
        },
    )

    assert pump.record_tournament_results([]) == 0
    assert not db.updateTourneyPlayerResult.called


def test_an_announcement_keeps_the_tournament_it_was_first_filed_on() -> None:
    """Half an announcement here and half there would be the worst outcome.

    The capture keeps learning who played what, so the same players can
    correlate differently a few sweeps later. Whatever the answer becomes, the
    places left over belong with the ones already written.
    """
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [True, False]
    pump = _pump_that_knows_a_tournament(db, _join("1160391", "81499"), seated={"81499": ("jeje1976", "Alisey")})
    announcement = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]

    assert pump.record_tournament_results(announcement) == 1

    # A second tournament turns up with the very same players, which would
    # leave the correlation unable to choose.
    pump._remember_tournaments([_join("1161142", "81498", name="Step [2] to 565 Main Event [1E]")])
    pump._remember_tournament_players(
        {
            "tournament": {"tour_no": "81498", "table_id": "1161142"},
            "players": [{"name": "jeje1976"}, {"name": "Alisey"}],
        },
    )

    db.updateTourneyPlayerResult.side_effect = [True]
    assert pump.record_tournament_results(announcement) == 1
    assert db.updateTourneyPlayerResult.call_args_list[-1] == call("CoinPoker", "81499", "Alisey", 2)


def _aof_hand_at(table: str) -> tuple[list[tuple], tuple]:
    """A real All-in or Fold hand moved to `table`, with the join naming it."""
    raw = json.loads((Path(__file__).parent / "data" / "coinpoker_aof_hand_events.json").read_text())
    hand = [(name, str(hid).replace("123144", table) if hid else hid, data) for name, hid, data in raw["hand"]]
    join = tuple(raw["join"])
    return hand, join


def test_a_hand_of_a_game_fpdb_cannot_store_leaves_the_buffer() -> None:
    """A hand nobody ever answers for is a hand whose events are never dropped.

    Not importable and not failed, it read as a hand still being dealt: the
    sweep offered it again every time, and its sixty-six events stayed in the
    buffer for the rest of the run.
    """
    hand, _join = _aof_hand_at("123144")
    # The room says this table deals All-in or Fold Hold'em, which fpdb has no
    # model for.
    holdem_join = (
        "lobby.join_game_table",
        None,
        {
            "tablesToJoin": [
                {
                    "tableName": "17th-TX AOF 0.10-0.25 123144",
                    "roomProperties": {"tournamentTypeId": 14, "lobbyId": 12, "miniGameTypeId": 1},
                },
            ],
        },
    )
    db = Mock()
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=db, config=config, table_category="PLO4", dry_run=True)

    accumulated = [holdem_join, *hand]
    assert pump.process(accumulated) == 0
    assert pump.imported == set()
    assert pump.capture_only == {"12314400005"}

    accumulated = pump.prune(accumulated)
    assert accumulated == []

    # And it is not offered to the database on a later sweep either.
    assert pump.process(accumulated) == 0
    assert not db.method_calls


def test_a_hand_fpdb_can_store_is_not_set_aside() -> None:
    # The control: the same hand at an All-in or Fold Omaha table is imported.
    hand, join = _aof_hand_at("123144")
    db = Mock()
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=db, config=config, table_category="PLO4", dry_run=True)

    assert pump.process([join, *hand]) == 1
    assert pump.capture_only == set()


def test_the_all_in_or_fold_catalogue_survives_the_sweep_it_arrived_in() -> None:
    """The room says which tables are All-in or Fold once, in a huge catalogue.

    It names no hand, so pruning drops it -- and every test that handed the
    catalogue and the hand to one call could not see that. In the live loop
    the hands arrive over many sweeps after it: without keeping what it said,
    the game is recognised on that one sweep and the same table is All-in or
    Fold and then ordinary Omaha.
    """
    aof = json.loads((Path(__file__).parent / "data" / "coinpoker_aof_hand_events.json").read_text())
    catalogue = tuple(aof["catalogue"])
    at_123108 = [(name, str(hid).replace("123144", "123108") if hid else hid, data) for name, hid, data in aof["hand"]]
    db = Mock()
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=db, config=config, table_category="PLO4", dry_run=True)

    # Sweep one carries the catalogue and no hand at all.
    accumulated = [catalogue]
    pump.process(accumulated)
    accumulated = pump.prune(accumulated)
    assert accumulated == []

    # The hand arrives later, long after the catalogue is gone.
    built = build_hands(
        at_123108,
        "PLO4",
        session_context=pump._session_context,
        session_tables=pump._session_tables,
        session_aof=pump._session_aof,
    )

    assert [hand["gametype"]["category"] for hand in built] == ["aof_omaha"]


def test_a_restart_while_seated_restores_the_aof_table_from_the_database() -> None:
    """A table already proved AoF stays AoF without a new lobby catalogue."""
    hand, _join = _aof_hand_at("124115")
    db = Mock()
    db.sql.query = {"placeholder": "?"}
    db.get_cursor.return_value.fetchall.return_value = [("124115",)]
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    known_aof_tables = _known_aof_tables(db)
    pump = HandPump(
        db=db,
        config=config,
        table_category="PLO4",
        archive_dir="",
        known_aof_tables=known_aof_tables,
    )
    pump._insert_hand = Mock()

    assert pump.process(hand) == 1
    imported = pump._insert_hand.call_args.args[0]
    assert imported.gametype["category"] == "aof_omaha"
    db.get_cursor.return_value.execute.assert_called_once()
    assert db.get_cursor.return_value.execute.call_args.args[1] == (COINPOKER_SITE_ID, "aof_omaha")
    db.rollback.assert_called_once()


def test_live_run_hydrates_the_new_pump_with_known_aof_tables(monkeypatch) -> None:
    """The durable lookup is wired into the production run, not only callable."""
    db = Mock()
    config = Mock()
    coordinator = Mock()
    captured: dict = {}

    class RecordingPump:
        imported: set[str] = set()

        def __init__(self, *_args, **kwargs) -> None:
            captured.update(kwargs)

        def process(self, _events) -> int:
            return 0

        def record_tournament_results(self, _events) -> int:
            return 0

    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture._open_db", lambda _path: (db, config))
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture._ensure_capture_file", lambda _db: 7)
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture._known_aof_tables", lambda _db: {"124115": 2})
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture._make_hud_notifier", lambda: None)
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture._make_equity_coordinator", lambda *_args: coordinator)
    monkeypatch.setattr("fpdb_3_legacy.coinpoker_live_capture.HandPump", RecordingPump)

    run([], dry_run=False, table_category="PLO4")

    assert captured["known_aof_tables"] == {"124115": 2}
    coordinator.close.assert_called_once()


def test_the_buffer_keeps_only_hands_still_being_assembled() -> None:
    """Events naming no hand belong to no hand that can ever be finished.

    They used to stay for the rest of the run, so the buffer only grew and
    every sweep re-read all of it. What is worth keeping has been taken out
    already: joins and markers into the session context, announcements into
    their own entries.
    """
    db = Mock()
    pump = _pump_that_knows_a_tournament(db)
    pump.imported.add("98127900001")
    events = [
        _join("1160391", "81499"),
        _winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket")),
        ("game.seat", "98127900001", {"seatId": 1}),
        ("game.seat", "98127900002", {"seatId": 1}),
    ]

    assert pump.prune(events) == [("game.seat", "98127900002", {"seatId": 1})]


def test_an_announcement_outlives_the_events_it_arrived_on() -> None:
    """A place that could not be written is retried after the buffer is pruned.

    The announcement is answered over several sweeps, so holding it only in
    the event buffer meant pruning the buffer would drop it -- and whoever was
    left unfiled would never be offered again.
    """
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [True, False]
    pump = _pump_that_knows_a_tournament(db)
    announcement = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]

    assert pump.record_tournament_results(announcement) == 1

    # The buffer is emptied, exactly as the loop empties it.
    assert pump.prune(announcement) == []
    db.updateTourneyPlayerResult.side_effect = [True]
    assert pump.record_tournament_results([]) == 1
    assert db.updateTourneyPlayerResult.call_args_list[-1] == call("CoinPoker", "1160377", "Alisey", 2)


def test_successive_announcements_stay_separate_under_the_real_loop() -> None:
    """The capture loop hands the same buffer back, announcement and all.

    Events naming no hand were never pruned, so the first tournament's
    announcement was still in the buffer when the second arrived and the two
    were read as one list of places: 35 names from two tournaments, correlated
    as a single announcement and filed on whichever won. Passing each sweep a
    fresh list is what hid this.
    """
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
        seated={"81499": ("jeje1976", "Alisey"), "81498": ("Kandinsky", "Mirek")},
    )
    first = _winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))
    second = _winner_event((1, "Kandinsky", "Ticket"), (2, "Mirek", "Ticket"))

    # The buffer the loop actually carries: pruned, then appended to.
    accumulated = [first]
    assert pump.record_tournament_results(accumulated) == 2
    accumulated = [*pump.prune(accumulated), second]
    assert pump.record_tournament_results(accumulated) == 2

    assert db.updateTourneyPlayerResult.call_args_list == [
        call("CoinPoker", "81499", "jeje1976", 1),
        call("CoinPoker", "81499", "Alisey", 2),
        call("CoinPoker", "81498", "Kandinsky", 1),
        call("CoinPoker", "81498", "Mirek", 2),
    ]


def test_a_second_tournament_does_not_claim_the_first_one_s_places() -> None:
    """A capture that plays one tournament after another files each on its own.

    Both are on the books when the second announcement arrives, so counting
    the tournaments known would refuse it -- and counting them at the first
    announcement would have accepted it for whichever one happened to be the
    only one so far. The players settle it.
    """
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(
        db,
        _join("1160391", "81499"),
        _join("1161142", "81498", name="Step [2] to 565 Main Event [1E]"),
        seated={"81499": ("jeje1976", "Alisey"), "81498": ("Kandinsky", "Mirek")},
    )

    first = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]
    second = [_winner_event((1, "Kandinsky", "Ticket"), (2, "Mirek", "Ticket"))]

    assert pump.record_tournament_results(first) == 2
    assert pump.record_tournament_results(second) == 2

    assert db.updateTourneyPlayerResult.call_args_list == [
        call("CoinPoker", "81499", "jeje1976", 1),
        call("CoinPoker", "81499", "Alisey", 2),
        call("CoinPoker", "81498", "Kandinsky", 1),
        call("CoinPoker", "81498", "Mirek", 2),
    ]


def test_the_same_tournament_at_two_tables_is_still_one_tournament() -> None:
    # Being moved is not playing two tournaments.
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db, _join("1160391", "81499"), _join("1160377", "81499"))

    places = pump.record_tournament_results([_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))])

    assert places == 2
    assert {c.args[1] for c in db.updateTourneyPlayerResult.call_args_list} == {"81499"}


def test_a_stream_with_no_announcement_writes_nothing() -> None:
    db = Mock()
    pump = _pump_that_knows_a_tournament(db)

    assert pump.record_tournament_results(_events()) == 0
    assert not db.updateTourneyPlayerResult.called


def test_a_dry_run_writes_nothing(tmp_path) -> None:
    db = Mock()
    config = HttpCaptureHandConfig(site_ids={"CoinPoker": COINPOKER_SITE_ID, "default": COINPOKER_SITE_ID})
    pump = HandPump(db=db, config=config, table_category="PLO4", dry_run=True, archive_dir=str(tmp_path))
    pump._tour_no = "1160377"

    assert pump.record_tournament_results([_winner_event((1, "jeje1976", "Ticket"))]) == 0
    assert not db.updateTourneyPlayerResult.called


def test_a_place_that_could_not_be_filed_is_tried_again() -> None:
    """A player whose entry is not there yet must not be taken as filed.

    The tournament used to be marked done as soon as one place landed, so
    everyone behind a failure stayed missing for good.
    """
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [True, False]
    pump = _pump_that_knows_a_tournament(db)
    events = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]

    assert pump.record_tournament_results(events) == 1

    db.updateTourneyPlayerResult.side_effect = [True]
    assert pump.record_tournament_results(events) == 1
    assert db.updateTourneyPlayerResult.call_args_list[-1] == call("CoinPoker", "1160377", "Alisey", 2)


def test_a_place_already_filed_is_not_written_again() -> None:
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db)
    events = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]

    assert pump.record_tournament_results(events) == 2
    assert pump.record_tournament_results(events) == 0
    assert db.updateTourneyPlayerResult.call_count == 2


def test_a_player_that_keeps_failing_is_reported_each_sweep(capsys) -> None:
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = RuntimeError("gone")
    pump = _pump_that_knows_a_tournament(db)

    pump.record_tournament_results([_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))])

    printed = capsys.readouterr().out
    assert "could not record jeje1976" in printed
    assert "2 place(s) still unfiled" in printed


def test_a_commit_that_fails_files_nobody(capsys) -> None:
    """A statement is not a result until the transaction holding it is accepted.

    Players used to be marked as filed on the strength of the statement alone,
    so a commit that then failed lost their places for good: the next sweep
    skipped them as already done.
    """
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    db.commit.side_effect = [RuntimeError("connection lost"), None, None]
    pump = _pump_that_knows_a_tournament(db)
    events = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]

    # The first player's commit fails; the second is unaffected.
    assert pump.record_tournament_results(events) == 1
    db.rollback.assert_called_once_with()
    assert "could not record jeje1976" in capsys.readouterr().out

    # The next sweep offers the place that did not land, and it does.
    assert pump.record_tournament_results(events) == 1
    assert db.updateTourneyPlayerResult.call_args_list[-1] == call("CoinPoker", "1160377", "jeje1976", 1)


def test_a_failing_statement_does_not_poison_the_rest_of_the_sweep() -> None:
    """A raised statement leaves the transaction aborted on PostgreSQL.

    Every later place in the sweep would then fail too and the closing commit
    would write nobody -- while the error named only the first player, so the
    log read as a single casualty. Each place is rolled back on its own so the
    next one starts on a transaction the database will still accept.
    """
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [RuntimeError("aborted"), True, True]
    pump = _pump_that_knows_a_tournament(db)

    recorded = pump.record_tournament_results(
        [_winner_event((1, "boom", "Ticket"), (2, "jeje1976", "Ticket"), (3, "Alisey", "Ticket"))],
    )

    assert recorded == 2
    # Rolled back before the next statement, not left open behind it.
    assert db.method_calls.index(call.rollback()) < db.method_calls.index(
        call.updateTourneyPlayerResult("CoinPoker", "1160377", "jeje1976", 2),
    )


def test_a_player_with_no_entry_stops_being_retried(capsys) -> None:
    """The announcement lands after the last hand, so an absence is final.

    A player never dealt in at a captured table has no row to write a place
    on, and none is coming. Retried every sweep, they would be re-queried for
    the rest of the run -- for a table of strangers, that is most of the
    announcement.
    """
    db = Mock()
    # The regular has an entry; the stranger, never dealt in, has none.
    db.updateTourneyPlayerResult.side_effect = lambda _s, _t, player, _r: player != "a stranger"
    pump = _pump_that_knows_a_tournament(db)
    events = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"), (3, "a stranger", "Ticket"))]

    assert pump.record_tournament_results(events) == 2
    for _ in range(5):
        assert pump.record_tournament_results(events) == 0

    tried = [c.args[2] for c in db.updateTourneyPlayerResult.call_args_list]
    assert tried.count("a stranger") == MAX_RESULT_ATTEMPTS
    printed = capsys.readouterr().out
    assert "has no entry to record a place on" in printed
    assert "still unfiled" not in printed.rsplit("giving up", 1)[-1]


def test_a_player_whose_entry_arrives_before_the_limit_is_still_filed() -> None:
    # Giving up is for an absence that has had its chances, not the first miss.
    db = Mock()
    db.updateTourneyPlayerResult.side_effect = [False, False, True, True]
    pump = _pump_that_knows_a_tournament(db)
    events = [_winner_event((1, "jeje1976", "Ticket"), (2, "Alisey", "Ticket"))]

    assert pump.record_tournament_results(events) == 0
    assert pump.record_tournament_results(events) == 2


def test_each_place_stands_on_its_own_transaction() -> None:
    # One place, one transaction: a place is durable the moment it lands, and
    # none of them is hostage to the worst of the sweep.
    db = Mock()
    db.updateTourneyPlayerResult.return_value = True
    pump = _pump_that_knows_a_tournament(db)

    pump.record_tournament_results([_winner_event((1, "a", "Ticket"), (2, "b", "Ticket"), (3, "c", "Ticket"))])

    assert db.updateTourneyPlayerResult.call_count == 3
    assert db.commit.call_count == 3
