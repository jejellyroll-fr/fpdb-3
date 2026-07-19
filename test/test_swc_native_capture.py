import io
import struct
import threading
from datetime import UTC, datetime

import pytest

from fpdb_3_legacy.swc_native_capture import (
    NativeAnimationEvent,
    NativeCaptureRecord,
    NativeGameStateSnapshot,
    NativePlayerIdentity,
    NativeProtocolMessage,
    NativeSeatEvidence,
    _collect_native_game_changes,
    _native_street_profile,
    _retain_bijective_native_seat_evidence,
    audit_native_hand,
    build_native_ofc_summary,
    classify_native_ofc_deal_pattern,
    derive_native_used_hole_cards,
    diff_game_states,
    extract_dealer_message,
    extract_game_state,
    extract_native_animation_events,
    extract_native_board,
    extract_native_collections,
    extract_native_ofc_showdown_rows,
    extract_native_stud_upcards,
    extract_table_info,
    follow_dealer_history,
    infer_native_seat_evidence,
    iter_capture_records,
    iter_protocol_messages,
    match_native_foldout_winner_seat_evidence,
    match_native_return_seat_evidence,
    native_action_street,
    native_client_environment,
    normalize_native_hands,
    parse_native_card_mnemonic,
    parse_native_dealer_draw,
    parse_native_dealer_return,
    parse_native_dealer_win,
    parse_native_game_change,
    parse_native_ofc_fantasy_land,
    parse_native_ofc_game_complete,
    parse_native_ofc_game_start,
    parse_native_ofc_payout,
    parse_native_ofc_scores,
    parse_native_ofc_showdown_row,
    summarize_native_hands,
)

HEADER = struct.Struct("=IHBBHHIQ")


def _record(payload=b"game-state", *, direction=0, port=20013, timestamp_us=1_750_000_000_123_456):
    return HEADER.pack(0x53574354, 1, direction, 0, port, 0, len(payload), timestamp_us) + payload


def test_iter_capture_records_preserves_native_plaintext_metadata():
    records = list(iter_capture_records(io.BytesIO(_record())))

    assert len(records) == 1
    assert records[0].direction == "received"
    assert records[0].peer_port == 20013
    assert records[0].payload == b"game-state"
    assert records[0].captured_at == datetime.fromtimestamp(1_750_000_000.123456, tz=UTC)


def test_iter_capture_records_supports_multiple_directions():
    records = list(iter_capture_records(io.BytesIO(_record(b"in") + _record(b"out", direction=1))))

    assert [record.direction for record in records] == ["received", "sent"]
    assert [record.payload for record in records] == [b"in", b"out"]


def test_native_client_environment_removes_terminal_locale(monkeypatch, tmp_path):
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("LC_NUMERIC", "fr_FR.UTF-8")

    archive = tmp_path / "capture.raw"
    tap = tmp_path / "tap.dylib"
    env = native_client_environment(archive, tap, port=0, include_outbound=False)

    assert "LANG" not in env
    assert "LC_ALL" not in env
    assert "LC_NUMERIC" not in env
    assert env["SWC_CAPTURE_PATH"] == str(archive)
    assert env["SWC_CAPTURE_STATUS_PATH"] == str(archive.with_suffix(".status"))
    assert env["SWC_CAPTURE_PORT"] == "0"
    assert env["SWC_CAPTURE_OUTBOUND"] == "0"


def test_protocol_decoder_reassembles_header_and_split_body():
    framed = struct.pack("<I", 5) + b"hello"
    captured_at = datetime.now(UTC)
    records = iter(
        [
            NativeCaptureRecord(captured_at, "received", 20013, framed[:4]),
            NativeCaptureRecord(captured_at, "received", 20013, framed[4:7]),
            NativeCaptureRecord(captured_at, "received", 20013, framed[7:]),
        ]
    )

    messages = list(iter_protocol_messages(records))

    assert [message.payload for message in messages] == [b"hello"]


def test_protocol_decoder_keeps_concurrent_ports_separate():
    captured_at = datetime.now(UTC)
    first = struct.pack("<I", 3) + b"one"
    second = struct.pack("<I", 3) + b"two"
    records = iter(
        [
            NativeCaptureRecord(captured_at, "received", 20013, first[:4]),
            NativeCaptureRecord(captured_at, "received", 20020, second[:4]),
            NativeCaptureRecord(captured_at, "received", 20013, first[4:]),
            NativeCaptureRecord(captured_at, "received", 20020, second[4:]),
        ]
    )

    messages = list(iter_protocol_messages(records))

    assert [(message.peer_port, message.payload) for message in messages] == [(20013, b"one"), (20020, b"two")]


def test_extract_dealer_message_strips_native_rich_text():
    payload = b"\0\0prefix\0" + (
        b'2026-07-18 19:13:14\0DealerX\0<nick s="1">Rekegutt</nick> wins (<money a="120">1.20</money>)\0'
    )

    result = extract_dealer_message(NativeProtocolMessage(datetime.now(UTC), payload))

    assert result is not None
    assert result.timestamp == "2026-07-18 19:13:14"
    assert result.text == "Rekegutt wins (1.20)"


def test_follow_dealer_history_skips_messages_already_in_archive(tmp_path, capsys):
    archive = tmp_path / "capture.raw"
    payload = b"\0\0prefix\0" + b"2026-07-18 19:13:14\0Dealer\0Hand complete\0"
    archive.write_bytes(_record(struct.pack("<I", len(payload)) + payload))
    stop = threading.Event()
    stop.set()

    follow_dealer_history(archive, stop, poll_seconds=0.001)

    assert capsys.readouterr().out == ""


def test_summarize_native_hands_uses_table_and_hand_ids():
    captured_at = datetime.now(UTC)
    table_id = 238733636
    hand_id = 298327973
    table_name = b"Drawmaha Table"
    table_info = (
        b"\x22\0"
        + (b"\0" * 4)
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + (b"\0" * 4)
        + b"D"
        + len(table_name).to_bytes(2, "little")
        + table_name
    )
    snapshot = (
        b"\x16\0state"
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x03"
        + b"tail"
    )

    hands = summarize_native_hands(
        [
            NativeProtocolMessage(captured_at, table_info),
            NativeProtocolMessage(captured_at, snapshot),
            NativeProtocolMessage(captured_at, snapshot),
        ]
    )

    assert len(hands) == 1
    assert hands[0].table_id == table_id
    assert hands[0].hand_id == hand_id
    assert hands[0].table_name == "Drawmaha Table"
    assert hands[0].snapshot_count == 2
    assert hands[0].rounds == (3,)
    assert hands[0].players == ()


def test_extract_table_info_reads_stable_native_header():
    table_id = 24812
    name = b"No-Rake Micro Stakes PLO"
    payload = (
        b"\x22\0"
        + (123).to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + (0).to_bytes(4, "little")
        + b"O"
        + len(name).to_bytes(2, "little")
        + name
    )

    info = extract_table_info(NativeProtocolMessage(datetime.now(UTC), payload))

    assert info is not None
    assert info.table_id == table_id
    assert info.name == name.decode()
    assert info.tournament_id is None
    assert info.family == "omaha"


def test_extract_table_info_prioritizes_single_draw_name_over_cash_signature():
    table_id = 183514740
    name = b"No-Rake Micro Stakes 2-7 Single Draw"
    payload = (
        b"\x22\0"
        + (123).to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + (0).to_bytes(4, "little")
        + b"H"
        + len(name).to_bytes(2, "little")
        + name
        + b"UR"
    )

    info = extract_table_info(NativeProtocolMessage(datetime.now(UTC), payload))

    assert info.family == "draw"


def test_extract_table_info_keeps_drawmaha_separate_from_single_draw():
    table_id = 238733636
    name = b"No-Rake Micro Stakes Drawmaha"
    payload = (
        b"\x22\0"
        + (123).to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + (0).to_bytes(4, "little")
        + b"D"
        + len(name).to_bytes(2, "little")
        + name
    )

    info = extract_table_info(NativeProtocolMessage(datetime.now(UTC), payload))

    assert info.family == "drawmaha"


def test_native_action_street_maps_observed_drawmaha_rounds():
    assert native_action_street("drawmaha", 0, (9, 6)) == "BLINDSANTES"
    assert native_action_street("drawmaha", 1, (9, 1)) == "DEAL"
    assert native_action_street("drawmaha", 3, (9,)) == "DRAWTWO"
    assert native_action_street("drawmaha", 4, (9,)) == "DRAWTHREE"


def test_native_action_street_resolves_stud_and_draw_by_category():
    assert native_action_street("stud", 1, (), "razz") == "THIRD"
    assert native_action_street("stud", 5, (), "studhi") == "SEVENTH"
    # Draw games never take the community-card round shift, even with a type-2 event.
    assert native_action_street("draw", 2, (2,), "27_3draw") == "DRAWONE"
    assert native_action_street("draw", 6, (), "27_3draw") == "DRAWTHREE"
    assert native_action_street("draw", 2, (), "27_1draw") == "DRAWONE"


def test_native_street_profile_is_category_specific():
    assert _native_street_profile("stud", "razz") == ["BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
    assert _native_street_profile("draw", "27_1draw") == ["BLINDSANTES", "DEAL", "DRAWONE"]
    assert _native_street_profile("draw", "badugi") == [
        "BLINDSANTES",
        "DEAL",
        "DRAWONE",
        "DRAWTWO",
        "DRAWTHREE",
    ]
    # Unknown category falls back to the family profile.
    assert _native_street_profile("holdem", "holdem") == ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]


def test_extract_game_state_preserves_confirmed_ids_players_and_raw_payload():
    table_id = 28248
    hand_id = 298328340
    player_id = 255385813
    name = b"Mahyar"
    player = player_id.to_bytes(4, "little") + len(name).to_bytes(2, "little") + name + (b"\0" * 24)
    payload = (
        b"\x16\0header"
        + player
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x03"
        + b"tail"
    )
    message = NativeProtocolMessage(datetime.now(UTC), payload, peer_port=20013)

    snapshot = extract_game_state(message, {table_id})

    assert snapshot is not None
    assert snapshot.table_id == table_id
    assert snapshot.hand_id == hand_id
    assert snapshot.round_number == 3
    assert snapshot.players[0].player_id == player_id
    assert snapshot.players[0].name == "Mahyar"
    assert snapshot.raw_payload == payload
    assert snapshot.peer_port == 20013


def test_extract_game_state_reads_observed_three_byte_stack_units():
    table_id = 28248
    hand_id = 298328340
    name = b"Mahyar"
    player = (
        (255385813).to_bytes(4, "little")
        + len(name).to_bytes(2, "little")
        + name
        + b"\0\0prefix"
        + b"\xf0\xbf"
        + b"\0\x16\x80"
        + b"\0\x40"
        + (b"\0" * 4)
        + (580).to_bytes(3, "little")
        + b"suffix"
    )
    payload = (
        b"\x16\0" + player + hand_id.to_bytes(4, "little") + table_id.to_bytes(4, "little") + (b"\0" * 5) + b"\x01"
    )

    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert snapshot is not None
    assert snapshot.players[0].stack_units == 580
    assert snapshot.players[0].is_active is True


@pytest.mark.parametrize(
    ("round_number", "card_ids", "expected"),
    [
        (2, [30, 24, 14], ("9h", "8c", "5h")),
        (3, [30, 24, 14, 47], ("9h", "8c", "5h", "Ks")),
        (4, [30, 24, 14, 47, 46], ("9h", "8c", "5h", "Ks", "Kh")),
    ],
)
def test_extract_native_board_reads_observed_pre_footer_cards(round_number, card_ids, expected):
    table_id = 24812
    hand_id = 298328325
    prefix = b"\x16\0state\xf0\xbf\0\0\0"
    board = bytes([len(card_ids), *card_ids])
    footer = b"\0" * 14
    payload = (
        prefix
        + board
        + footer
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + bytes([round_number])
    )
    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert snapshot is not None
    assert extract_native_board(snapshot, "omaha") == expected


def test_extract_native_animation_events_reads_observed_type_9_suffix():
    table_id = 28248
    hand_id = 298328340
    payload = (
        b"\x16\0state"
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x01"
        + (b"\0" * 32)
        + (3).to_bytes(2, "little")
        + b"\x04\0\x04\x08"
        + b"\x09\x03\x04\x08"
        + (b"\0" * 8)
        + b"\x06\0\0\x01"
        + (b"\0" * 4)
    )

    events = extract_native_animation_events(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert [(event.type_code, event.action_code, event.funds, event.seat_idx) for event in events] == [
        (4, 0, 4, 8),
        (9, 3, 4, 8),
        (6, 0, 0, 1),
    ]
    assert events[1].raw_payload == b"\x09\x03\x04\x08" + (b"\0" * 8)


def test_extract_native_animation_events_recovers_unique_type_9_from_unknown_list():
    table_id = 28248
    hand_id = 298328340
    action = b"\x09\x08\x50\x02" + (b"\0" * 8)
    payload = (
        b"\x16\0state"
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x02unknown-prefix"
        + action
        + b"unknown-suffix"
    )

    events = extract_native_animation_events(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert [(event.type_code, event.action_code, event.funds, event.seat_idx) for event in events] == [(9, 8, 80, 2)]


def test_extract_native_animation_events_walks_observed_four_byte_auxiliary_types():
    table_id = 28248
    hand_id = 298328340
    events_raw = (
        (5).to_bytes(2, "little")
        + b"\x04\0\x10\x03"
        + b"\x09\x03\x10\x03"
        + (b"\0" * 8)
        + b"\x06\0\0\x04"
        + b"\x03\0\0\xff"
        + b"\x02\0\0\xff"
        + (b"\0" * 6)
    )
    payload = (
        b"\x16\0state"
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x02tail"
        + events_raw
    )

    events = extract_native_animation_events(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert [event.type_code for event in events] == [4, 9, 6, 3, 2]


def test_native_action_street_uses_previous_street_before_board_reveal():
    assert native_action_street("holdem", 2, (4, 9, 6, 3, 2, 2, 2)) == "PREFLOP"
    assert native_action_street("holdem", 2, (4, 9, 6)) == "FLOP"
    assert native_action_street("omaha", 4, (9, 6, 3, 2)) == "TURN"


def test_extract_native_animation_events_reads_variable_showdown_mnemonic_and_trailing_empty_list():
    table_id = 24812
    hand_id = 298328325
    mnemonic = b"D.47;46;45;26;24.O.H"
    type_10 = b"\x0a\0\x58\x08" + (b"\0" * 2) + len(mnemonic).to_bytes(2, "little") + mnemonic + (b"\0" * 10)
    payload = (
        b"\x16\0state"
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x06"
        + b"tail"
        + (1).to_bytes(2, "little")
        + type_10
        + b"\0\0"
    )

    events = extract_native_animation_events(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert len(events) == 1
    assert events[0].type_code == 10
    assert events[0].card_mnemonic == mnemonic.decode()


def test_parse_native_card_mnemonic_uses_swc_card_ids():
    assert parse_native_card_mnemonic("D.47;46;45;26;24.O.H") == ("Ks", "Kh", "Kd", "8h", "8c")
    assert parse_native_card_mnemonic("invalid") == ()


def _game_change_msg(table_id: int, text: str) -> NativeProtocolMessage:
    body = text.encode()
    payload = (
        b"\x1a\x00"  # class 26
        + b"\x00\x00\x00\x00"  # sequence
        + table_id.to_bytes(4, "little")
        + b"\x00\x11"
        + len(body).to_bytes(2, "little")
        + body
    )
    return NativeProtocolMessage(datetime.now(UTC), payload)


def test_parse_native_game_change_resolves_shared_definitions():
    msg = _game_change_msg(298377427, "Game changes to FL 2-7 Triple Draw 40/80")
    parsed = parse_native_game_change(msg.payload)

    assert parsed["table_id"] == 298377427
    assert parsed["game_label"] == "2-7 Triple Draw"
    assert parsed["base"] == "draw"
    assert parsed["category"] == "27_3draw"
    assert parsed["limit_type"] == "fl"
    assert parsed["small_bet"] == "40"
    assert parsed["big_bet"] == "80"


def test_parse_native_game_change_maps_each_family():
    cases = {
        "Game changes to NL Hold'em 25/50": ("holdem" not in "", "hold", "holdem", "nl"),
        "Game changes to PL Omaha 15/30": (True, "hold", "omahahi", "pl"),
        "Game changes to FL Razz 25/50": (True, "stud", "razz", "fl"),
        "Game changes to FL Badugi 75/150": (True, "draw", "badugi", "fl"),
    }
    for text, (_flag, base, category, limit) in cases.items():
        parsed = parse_native_game_change(_game_change_msg(1, text).payload)
        assert (parsed["base"], parsed["category"], parsed["limit_type"]) == (base, category, limit)


def test_parse_native_game_change_ignores_other_messages():
    assert parse_native_game_change(_game_change_msg(1, "Dealer says hi").payload) is None
    assert parse_native_game_change(b"\x00\x00not-a-change") is None


def test_collect_native_game_changes_binds_latest_change_to_hand():
    table_id = 298377427
    name = b"Sunday Mini 12-Game Mix"
    info_payload = (
        b"\x22\x00"
        + (0).to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + (0).to_bytes(4, "little")
        + b"F"
        + len(name).to_bytes(2, "little")
        + name
    )
    info_msg = NativeProtocolMessage(datetime.now(UTC), info_payload)
    table_infos = {table_id: extract_table_info(info_msg)}

    def snapshot(hand_id):
        payload = b"\x16\x00state" + hand_id.to_bytes(4, "little") + table_id.to_bytes(4, "little") + b"\x00" * 6
        return NativeProtocolMessage(datetime.now(UTC), payload)

    messages = [
        info_msg,
        _game_change_msg(table_id, "Game changes to FL Razz 25/50"),
        snapshot(1001),
        _game_change_msg(table_id, "Game changes to NL Hold'em 25/50"),
        snapshot(1002),
    ]

    changes = _collect_native_game_changes(messages, table_infos)

    assert changes[(table_id, 1001)]["game_label"] == "Razz"
    assert changes[(table_id, 1002)]["game_label"] == "Hold'em"


def _stud_snapshot(records):
    """Build a stud snapshot from [(name, [slot bytes]), ...] player records."""
    body = b"start"
    players = []
    for index, (name, slots) in enumerate(records):
        total = len(slots) + 2  # two hole cards plus the shown board slots
        body += name.encode() + b"\x00\x00\xf0\xbf" + bytes([total]) + b"\xff\xff" + bytes(slots) + b"\x00\x00"
        players.append(NativePlayerIdentity(index + 1, name, None, False, None))
    return NativeGameStateSnapshot(datetime.now(UTC), 1, 1, 5, tuple(players), body)


def test_extract_native_stud_upcards_maps_streets_and_hidden_slots():
    snap = _stud_snapshot([("BingoBob", [37, 40, 43, 0xFF])])
    rows = extract_native_stud_upcards([snap])

    assert len(rows) == 1
    row = rows[0]
    assert row["player"] == "BingoBob"
    assert row["seat_idx"] is None
    assert list(row["up_cards"]) == ["THIRD", "FOURTH", "FIFTH", "SIXTH"]
    assert all(isinstance(row["up_cards"][s], str) for s in ("THIRD", "FOURTH", "FIFTH"))
    assert row["up_cards"]["SIXTH"] is None  # 0xFF is a hidden card


def test_extract_native_stud_upcards_picks_richest_snapshot():
    early = _stud_snapshot([("BingoBob", [37])])
    late = _stud_snapshot([("BingoBob", [37, 40, 43])])
    rows = extract_native_stud_upcards([early, late])

    assert list(rows[0]["up_cards"]) == ["THIRD", "FOURTH", "FIFTH"]


def test_extract_native_stud_upcards_rejects_duplicate_cards():
    # The same card id in two players means a false match, so nothing decodes.
    snap = _stud_snapshot([("BingoBob", [37, 40]), ("Allinred", [37, 44])])
    assert extract_native_stud_upcards([snap]) == []


def test_parse_native_dealer_draw_decodes_counts_and_stands_pat():
    assert parse_native_dealer_draw("First draw: BingoBob draws 3") == {
        "draw": "first",
        "player": "BingoBob",
        "seat_idx": None,
        "cards_drawn": 3,
        "stands_pat": False,
        "source": "swc_native_dealer_chat",
        "text": "First draw: BingoBob draws 3",
    }
    pat = parse_native_dealer_draw("Final draw: Yx2kolm stands pat")
    assert pat["draw"] == "final"
    assert pat["player"] == "Yx2kolm"
    assert pat["cards_drawn"] == 0
    assert pat["stands_pat"] is True


def test_parse_native_dealer_draw_keeps_each_ordinal():
    assert parse_native_dealer_draw("Second draw: Tw4rriorz draws 2")["draw"] == "second"


def test_parse_native_dealer_draw_ignores_non_draw_lines():
    assert parse_native_dealer_draw("New hand started") is None
    assert parse_native_dealer_draw("BingoBob wins (1.20)") is None


def test_parse_native_ofc_showdown_row_decodes_valid_rows():
    assert parse_native_ofc_showdown_row("43;40;37") == ("Qs", "Qc", "Jd")
    assert parse_native_ofc_showdown_row("42;19;16;14;13") == ("Qh", "6s", "6c", "5h", "5d")


def test_parse_native_ofc_showdown_row_rejects_invalid_rows():
    assert parse_native_ofc_showdown_row("1;2") == ()  # only 3- or 5-card rows
    assert parse_native_ofc_showdown_row("1;2;3;4") == ()
    assert parse_native_ofc_showdown_row("1;2;52") == ()  # id out of range
    assert parse_native_ofc_showdown_row("5;5;6") == ()  # duplicate card


def _ofc_snapshot(payload: bytes, round_number: int = 6):
    return NativeGameStateSnapshot(
        datetime.now(UTC), 297862828, 298330169, round_number, (), payload
    )


def test_extract_native_ofc_showdown_rows_labels_top_only():
    payload = b"..H.42;19;16;14;13.M.H..I.43;40;37.M.H.."
    rows = extract_native_ofc_showdown_rows([_ofc_snapshot(payload)])

    assert rows == [
        {"cards": ["Qh", "6s", "6c", "5h", "5d"], "card_count": 5, "row": None},
        {"cards": ["Qs", "Qc", "Jd"], "card_count": 3, "row": "top"},
    ]


def test_extract_native_ofc_showdown_rows_picks_richest_snapshot():
    partial = _ofc_snapshot(b"..I.43;40;37.M.H..", round_number=5)
    full = _ofc_snapshot(b"..H.42;19;16;14;13.M.H..I.43;40;37.M.H..", round_number=6)
    rows = extract_native_ofc_showdown_rows([partial, full])

    assert len(rows) == 2


def test_extract_native_ofc_showdown_rows_rejects_duplicate_cards():
    # The same card in two rows means a false-positive match, so nothing decodes.
    payload = b"..I.43;40;37.M.H..H.43;19;16;14;13.M.H.."
    assert extract_native_ofc_showdown_rows([_ofc_snapshot(payload)]) == []


def test_derive_native_used_hole_cards_subtracts_board_multiset():
    evaluated = ("Ks", "Kh", "Kd", "8h", "8c")
    board = ("9h", "8c", "5h", "Ks", "Kh")

    assert derive_native_used_hole_cards(evaluated, board) == ("Kd", "8h")


def test_diff_game_states_reports_exact_delta_without_inferred_action():
    captured_at = datetime.now(UTC)
    previous = NativeGameStateSnapshot(
        captured_at, 28248, 298328340, 1, (NativePlayerIdentity(7, "Player", 584),), b"old"
    )
    current = NativeGameStateSnapshot(
        captured_at, 28248, 298328340, 1, (NativePlayerIdentity(7, "Player", 580),), b"new"
    )

    transitions = diff_game_states(previous, current)

    assert len(transitions) == 1
    assert transitions[0].previous_stack == 584
    assert transitions[0].current_stack == 580
    assert transitions[0].delta == -4


def test_infer_native_seat_evidence_rejects_opaque_funds_correlation():
    captured_at = datetime.now(UTC)
    table_id = 28248
    hand_id = 298328340

    def state_payload(value, events=b"\0\0"):
        name = b"Player"
        player = (
            (7).to_bytes(4, "little")
            + len(name).to_bytes(2, "little")
            + name
            + b"\0\0prefix\xf0\xbf\0\x16\x80"
            + (b"\0" * 6)
            + value.to_bytes(3, "little")
            + b"suffix"
        )
        return (
            b"\x16\0"
            + player
            + hand_id.to_bytes(4, "little")
            + table_id.to_bytes(4, "little")
            + (b"\0" * 5)
            + b"\x01"
            + events
        )

    action = (1).to_bytes(2, "little") + b"\x09\x03\x04\x08" + (b"\0" * 8)
    messages = [
        NativeProtocolMessage(captured_at, state_payload(584)),
        NativeProtocolMessage(captured_at, state_payload(580, action)),
        NativeProtocolMessage(
            captured_at,
            state_payload(570).replace(hand_id.to_bytes(4, "little"), (hand_id + 1).to_bytes(4, "little"), 1),
        ),
        NativeProtocolMessage(
            captured_at,
            state_payload(570, (1).to_bytes(2, "little") + b"\x09\x02\0\x08" + (b"\0" * 8)).replace(
                hand_id.to_bytes(4, "little"), (hand_id + 1).to_bytes(4, "little"), 1
            ),
        ),
        NativeProtocolMessage(
            captured_at,
            state_payload(560, (1).to_bytes(2, "little") + b"\x01\0\0\x07").replace(
                hand_id.to_bytes(4, "little"), (hand_id + 2).to_bytes(4, "little"), 1
            ),
        ),
        NativeProtocolMessage(
            captured_at,
            state_payload(560, (1).to_bytes(2, "little") + b"\x09\x02\0\x08" + (b"\0" * 8)).replace(
                hand_id.to_bytes(4, "little"), (hand_id + 2).to_bytes(4, "little"), 1
            ),
        ),
    ]

    evidence = infer_native_seat_evidence(messages, {table_id})

    assert evidence == {}


def test_normalize_native_hands_builds_capture_only_snapshot_envelope():
    captured_at = datetime.now(UTC)
    table_id = 28248
    hand_id = 298328340
    name = b"Player"
    table_name = b"No-Rake Micro Stakes #1"
    table_payload = (
        b"\x22\0"
        + (b"\0" * 4)
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + (b"\0" * 4)
        + b"H"
        + len(table_name).to_bytes(2, "little")
        + table_name
        + b"UR"
    )

    def state_payload(stack):
        player = (
            (7).to_bytes(4, "little")
            + len(name).to_bytes(2, "little")
            + name
            + b"\0\0prefix\xf0\xbf\0\x16\x80"
            + (b"\0" * 6)
            + stack.to_bytes(3, "little")
            + b"suffix"
        )
        return (
            b"\x16\0" + player + hand_id.to_bytes(4, "little") + table_id.to_bytes(4, "little") + (b"\0" * 5) + b"\x01"
        )

    hands = normalize_native_hands(
        [
            NativeProtocolMessage(captured_at, table_payload),
            NativeProtocolMessage(captured_at, state_payload(584), peer_port=20013),
            NativeProtocolMessage(captured_at, state_payload(580), peer_port=20013),
        ],
        raw_ref="capture.raw",
    )

    assert len(hands) == 1
    hand = hands[0]
    assert hand["gametype"]["base"] == "hold"
    assert hand["gametype"]["currency"] == "room_native"
    assert hand["players"][0]["starting_stack"] == 584
    assert hand["players"][0]["seat_idx"] is None
    assert hand["players"][0]["roster_index"] == 0
    assert hand["players"][0]["native_status_values"] == [0]
    assert hand["steps"][1]["stacks"] == {"Player": 580}
    assert hand["steps"][1]["diff"]["candidates"][0]["amount_delta"] == "-4"
    assert hand["steps"][1]["native_events"] == []
    assert hand["metadata"]["player_funds_field"] == "opaque_native_value_not_money"
    assert hand["metadata"]["importability"]["status"] == "capture_only"
    assert hand["actions"] == []
    assert hand["action_evidence"] == []
    assert hand["metadata"]["importability"]["poker_event_count"] == 0
    assert "hand start is not fully observed" in hand["metadata"]["importability"]["reasons"][0]


def test_audit_native_hand_reports_unresolved_actions_and_missing_settlement():
    steps = [
        {
            "native_events": [
                {"action_name_evidence": "small_blind", "player_name_evidence": "Alice"},
                {"type_code": 9, "action_name_evidence": "big_blind", "player_name_evidence": "Bob"},
                {"type_code": 9, "action_name_evidence": "fold"},
            ]
        }
    ]

    audit = audit_native_hand(steps, [])

    assert audit["resolved_poker_event_count"] == 2
    assert audit["unresolved_poker_event_count"] == 1
    assert audit["unresolved_by_action"] == {"fold": 1}
    assert audit["has_small_blind"] is True
    assert audit["has_big_blind"] is True
    assert audit["has_collection"] is False
    assert audit["dealer_hand_started"] is False
    assert audit["dealer_hand_complete"] is False
    assert audit["importable"] is False
    assert audit["resolved_native_type_9_player_count"] == 1
    assert audit["native_type_9_event_count"] == 2


def test_native_seat_evidence_rejects_player_assigned_to_multiple_seats():
    evidence = {
        (10, 20, 1): NativeSeatEvidence(10, 20, 1, 7, "Alice", "active_player_flag"),
        (10, 20, 4): NativeSeatEvidence(10, 20, 4, 7, "Alice", "active_player_flag"),
        (10, 20, 2): NativeSeatEvidence(10, 20, 2, 8, "Bob", "unique_raw_funds_decrease"),
    }

    retained = _retain_bijective_native_seat_evidence(evidence)

    assert set(retained) == {(10, 20, 2)}


def test_match_native_return_seat_evidence_anchors_unique_cash_bet():
    event = NativeAnimationEvent(10, 20, 2, 0, 9, 8, 16, 8, b"raw")
    players = (NativePlayerIdentity(7, "unebu"),)
    returned = [{"player": "unebu", "amount_native": 16, "money_type": "R"}]

    evidence = match_native_return_seat_evidence(10, 20, [event], players, returned)

    assert evidence[(10, 20, 8)].player_name == "unebu"
    assert evidence[(10, 20, 8)].source == "unique_returned_cash_bet"


def test_match_native_foldout_winner_seat_evidence_anchors_only_remaining_index():
    events = [
        *(NativeAnimationEvent(10, 20, 1, index, 1, 0, 0, 3, b"deal") for index in range(2)),
        *(NativeAnimationEvent(10, 20, 1, index + 2, 1, 0, 0, 8, b"deal") for index in range(2)),
        NativeAnimationEvent(10, 20, 1, 4, 9, 1, 0, 3, b"fold"),
    ]
    players = (NativePlayerIdentity(7, "Winner"), NativePlayerIdentity(8, "Folder"))
    collections = [{"player": "Winner", "text": "Winner wins (0.10): doesn't show cards"}]

    evidence = match_native_foldout_winner_seat_evidence(10, 20, "holdem", events, players, collections)

    assert evidence[(10, 20, 8)].player_name == "Winner"
    assert evidence[(10, 20, 8)].source == "unique_non_folded_no_show_winner"


def test_extract_native_collections_reads_explicit_type_15_native_amount():
    table_id = 28248
    hand_id = 298328340
    rich = b'<nick s="3">Winner</nick> wins (<money a="42" mt="R">0.42</money>)'
    payload = (
        b"\x16\0state"
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x06tail"
        + (1).to_bytes(2, "little")
        + b"\x0f\0\0\x03"
        + len(rich).to_bytes(2, "little")
        + rich
    )

    events = extract_native_collections(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert len(events) == 1
    assert events[0].player_name == "Winner"
    assert events[0].player_index == 3
    assert events[0].amount_native == 42
    assert events[0].amount_displayed == "0.42"
    assert events[0].money_type == "R"
    assert events[0].native_units_per_display_unit == 100
    assert events[0].text == "Winner wins (0.42)"


@pytest.mark.parametrize(
    ("text", "tournament", "native", "displayed", "money_type"),
    [
        ("Winner wins (0.72) with Two Pairs", False, 72, "0.72", "R"),
        ("Winner wins (2,782) with Two Pairs", True, 2782, "2,782", "T"),
    ],
)
def test_parse_native_dealer_win_preserves_cash_and_tournament_scale(text, tournament, native, displayed, money_type):
    collection = parse_native_dealer_win(text, tournament=tournament)

    assert collection["amount_native"] == native
    assert collection["amount_displayed"] == displayed
    assert collection["money_type"] == money_type
    assert collection["seat_idx"] is None


@pytest.mark.parametrize(
    ("text", "tournament", "native", "player"),
    [
        ("Uncalled bet (0.48) returned to CAAD1", False, 48, "CAAD1"),
        ("Uncalled bet (2,782) returned to Winner", True, 2782, "Winner"),
    ],
)
def test_parse_native_dealer_return_preserves_exact_amount(text, tournament, native, player):
    returned = parse_native_dealer_return(text, tournament=tournament)

    assert returned["amount_native"] == native
    assert returned["player"] == player


@pytest.mark.parametrize(
    ("text", "kind", "scores", "hand_number"),
    [
        ("Hand #3 finished - retsamkert: +15, Oldrgooner: -15", "hand", {"retsamkert": 15, "Oldrgooner": -15}, 3),
        ("TOTAL - retsamkert: +9, Oldrgooner: -9", "total", {"retsamkert": 9, "Oldrgooner": -9}, None),
    ],
)
def test_parse_native_ofc_scores_preserves_signed_points(text, kind, scores, hand_number):
    result = parse_native_ofc_scores(text)

    assert result["kind"] == kind
    assert result["scores"] == scores
    assert result.get("hand_number") == hand_number


def test_parse_native_ofc_payout_preserves_exact_cash_amount():
    payout = parse_native_ofc_payout("DyckensCider wins 82.56")

    assert payout["player"] == "DyckensCider"
    assert payout["amount_displayed"] == "82.56"
    assert payout["amount_native"] == 8256


def test_parse_native_ofc_fantasy_land_preserves_player_and_button_rule():
    fantasy = parse_native_ofc_fantasy_land("retsamkert is in fantasy land. The button will not be moved")

    assert fantasy["player"] == "retsamkert"
    assert fantasy["button_moved"] is False


def test_parse_native_ofc_game_complete_preserves_hand_count():
    complete = parse_native_ofc_game_complete("Game complete, 8 hands played")

    assert complete["complete"] is True
    assert complete["hands_played"] == 8


def test_parse_native_ofc_game_start_preserves_planned_hand_count():
    start = parse_native_ofc_game_start("New game started (2 hands)")

    assert start["planned_hands"] == 2


def test_classify_native_ofc_deal_pattern_requires_five_then_three():
    assert classify_native_ofc_deal_pattern(has_initial_five=True, has_later_three=True) == "pineapple"
    assert classify_native_ofc_deal_pattern(has_initial_five=True, has_later_three=False) == "unresolved"


def test_build_native_ofc_summary_excludes_non_ofc_hands():
    hands = [
        {
            "table_id": 1,
            "table_name": "OFC",
            "hand_id": 2,
            "game": {"category": "ofc", "ofc_variant": "pineapple"},
            "ofc_result": {"scores": {"Alice": 3}},
            "ofc_total": None,
            "ofc_fantasy_land": [],
            "ofc_payouts": [],
            "ofc_game_start": None,
            "ofc_game_complete": None,
            "ofc_showdown_rows": [],
        },
        {"game": {"category": "holdem"}},
    ]

    summary = build_native_ofc_summary(hands)

    assert len(summary) == 1
    assert summary[0]["variant"] == "pineapple"
    assert summary[0]["result"]["scores"] == {"Alice": 3}


@pytest.mark.parametrize(
    "data, message",
    [
        (_record()[:-1], "truncated SwC native capture payload"),
        (b"short", "truncated SwC native capture header"),
        (HEADER.pack(0, 1, 0, 0, 20013, 0, 0, 0), "invalid SwC native capture header"),
        (HEADER.pack(0x53574354, 1, 2, 0, 20013, 0, 0, 0), "invalid SwC native capture direction"),
    ],
)
def test_iter_capture_records_rejects_corruption(data, message):
    with pytest.raises(ValueError, match=message):
        list(iter_capture_records(io.BytesIO(data)))
