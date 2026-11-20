import io
import platform
import shutil
import struct
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from fpdb_3_legacy.capture.swc_client import native_client_environment, parse_args
from fpdb_3_legacy.swc_native_capture import (
    NativeAnimationEvent,
    NativeCaptureRecord,
    NativeGameStateSnapshot,
    NativePlayerIdentity,
    NativeProtocolMessage,
    NativeSeatEvidence,
    _build_native_action_evidence,
    _collect_native_game_changes,
    _native_board_output,
    _native_hand_seat_map,
    _native_street_profile,
    _native_table_family,
    _resolve_native_hand_game,
    _retain_bijective_native_seat_evidence,
    add_native_funds_byte_amounts_if_conserved,
    audit_native_hand,
    audit_native_stud_accounting,
    build_native_canonical_actions,
    build_native_ofc_summary,
    card_id_to_str,
    classify_native_ofc_deal_pattern,
    decode_native_amount,
    derive_native_stud_betting_structure,
    derive_native_used_hole_cards,
    diff_game_states,
    extract_dealer_message,
    extract_game_state,
    extract_native_animation_events,
    extract_native_blind_structure,
    extract_native_board,
    extract_native_boards,
    extract_native_collections,
    extract_native_hero_hole_cards,
    extract_native_ofc_showdown_rows,
    extract_native_outbound_login_name,
    extract_native_stud_forced_bets,
    extract_native_stud_upcards,
    extract_native_table_player_stacks,
    extract_table_info,
    follow_dealer_history,
    infer_native_seat_evidence,
    iter_capture_records,
    iter_protocol_messages,
    match_native_foldout_winner_seat_evidence,
    match_native_outbound_seat_evidence,
    match_native_return_seat_evidence,
    native_action_street,
    native_seat_cards,
    native_stud_hole_cards,
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
    parse_native_outbound_action,
    parse_native_outbound_seat_request,
    summarize_native_hands,
)
from tests.helpers.swc_native_payloads import (
    encode_native_amount,
    native_action_event,
    native_event_list,
    native_player_record,
    native_seat_block,
    native_state_payload,
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


def test_parse_args_enables_bidirectional_capture_by_default():
    assert parse_args([]).include_outbound is True
    assert parse_args(["--no-include-outbound"]).include_outbound is False


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


def test_protocol_decoder_can_reassemble_outbound_separately():
    captured_at = datetime.now(UTC)
    incoming = struct.pack("<I", 2) + b"in"
    outgoing = struct.pack("<I", 3) + b"out"
    records = iter(
        [
            NativeCaptureRecord(captured_at, "received", 20013, incoming),
            NativeCaptureRecord(captured_at, "sent", 20013, outgoing),
        ]
    )

    messages = list(iter_protocol_messages(records, include_outbound=True))

    assert [(message.direction, message.payload) for message in messages] == [
        ("received", b"in"),
        ("sent", b"out"),
    ]


def test_extract_native_outbound_login_name_does_not_expose_credentials():
    payload = b"\x04\x00\x01\x00\x00\x00\x05\x00HeroX" + b"secret-token"
    message = NativeProtocolMessage(datetime.now(UTC), payload, direction="sent")

    assert extract_native_outbound_login_name(message) == "HeroX"
    assert extract_native_outbound_login_name(replace(message, direction="received")) is None


def test_parse_native_outbound_action_preserves_opaque_argument():
    payload = b"\x33\x01\x01\x00\x00\x00" + struct.pack("<I", 24812) + b"\x09\x08" + b"\0" * 6
    message = NativeProtocolMessage(datetime.now(UTC), payload, direction="sent")

    assert parse_native_outbound_action(message) == {
        "timestamp": message.captured_at.isoformat(),
        "table_id": 24812,
        "action_code": 9,
        "action": "raise",
        "native_argument": 8,
        "raw_hex": payload.hex(),
        "source": "swc_native_outbound_type_307",
    }


def test_match_native_outbound_seat_evidence_anchors_echoed_local_index():
    players = (NativePlayerIdentity(7, "Hero"), NativePlayerIdentity(8, "Villain"))
    actions = [
        {"player": "Hero", "server_native_index": 4},
        {"player": "Hero", "server_native_index": 4},
    ]

    evidence = match_native_outbound_seat_evidence(10, 20, actions, players)

    assert evidence == {(10, 20, 4): NativeSeatEvidence(10, 20, 4, 7, "Hero", "confirmed_outbound_action_echo")}


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


def test_drawmadugi_is_a_drawmaha_family_with_a_distinct_capture_only_category():
    table_id = 238733637
    name = b"No-Rake Micro Stakes Drawmadugi"
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

    assert info is not None
    assert info.family == "drawmaha"
    assert _resolve_native_hand_game(None, info, table_id, set()) == (
        "drawmaha",
        "draw",
        "drawmadugi",
        "unknown",
    )


@pytest.mark.parametrize(
    ("name", "family"),
    [
        ("2-7 Pineapple OFC Poker", "ofc"),
        ("Progressive Pineapple OFC Poker", "ofc"),
        ("Pineapple OFC Poker", "ofc"),
        ("Open Face Chinese Poker", "ofc"),
        ("Chinese Poker", "ofc"),
        ("Badacey Poker", "draw"),
        ("Badeucy Poker", "draw"),
        ("Badugi Poker", "draw"),
        ("2-7 Single Draw Poker", "draw"),
        ("2-7 Triple Draw Poker", "draw"),
        ("5-Card Draw Poker", "draw"),
        ("Drawmaha Poker", "drawmaha"),
        ("Drawmaha 2-7", "drawmaha"),
        ("Sviten Special", "drawmaha"),
        ("6-Card Omaha Hi/Lo Poker", "omaha"),
        ("6-Card Omaha Poker", "omaha"),
        ("Courchevel Hi/Lo Poker", "omaha"),
        ("Courchevel Poker", "omaha"),
        ("Big O Poker", "omaha"),
        ("5-Card Omaha Poker", "omaha"),
        ("Omaha Hi/Lo Poker", "omaha"),
        ("Omaha Poker", "omaha"),
        ("Pineapple Hold'em Poker", "holdem"),
        ("Short Deck Hold'em Poker", "holdem"),
        ("Texas Hold'em Poker", "holdem"),
        ("Razz Poker", "stud"),
        ("7-Card Stud Hi/Lo Poker", "stud"),
        ("7-Card Stud Poker", "stud"),
    ],
)
def test_native_table_family_covers_swc_rules_families(name: str, family: str) -> None:
    assert _native_table_family(name, name, b"") == family


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


def test_native_action_street_keeps_closing_stud_action_on_previous_street():
    assert (
        native_action_street(
            "stud",
            2,
            (9, 6, 3, 1),
            "studhi",
            event_index=0,
            transition_indexes=(2, 3),
        )
        == "THIRD"
    )
    assert native_action_street("stud", 6, (9,), "razz", event_index=0) == "SEVENTH"


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


def test_extract_game_state_reads_each_seat_state_from_the_block_before_its_record():
    table_id = 28248
    hand_id = 298328340
    payload = native_state_payload(
        table_id,
        hand_id,
        [
            None,
            (native_seat_block(funds=580, active=True), native_player_record(255385813, "alice")),
            None,
            (native_seat_block(funds=1500), native_player_record(7, "bob")),
        ],
    )

    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert snapshot is not None
    alice, bob = snapshot.players
    assert (alice.name, alice.seat_idx, alice.stack_units, alice.is_active) == ("alice", 1, 580, True)
    # The block after alice's record is bob's: reading it as hers handed every
    # player their neighbour's funds and active bit (#829).
    assert (bob.name, bob.seat_idx, bob.stack_units, bob.is_active) == ("bob", 3, 1500, False)


def test_decode_native_amount_reads_the_room_amount_encoding():
    assert decode_native_amount(b"\x05", 0) == (5, 1)
    assert decode_native_amount(bytes.fromhex("5c2e00"), 0) == (1500, 3)
    assert decode_native_amount(bytes.fromhex("480100"), 0) == (40, 3)
    assert decode_native_amount(bytes.fromhex("44ff00"), 0) == (4 + (0xFF << 5), 3)
    assert decode_native_amount(bytes.fromhex("4801"), 0) is None  # three bytes promised, two present
    assert decode_native_amount(bytes.fromhex("a0"), 0) is None  # an unobserved form is refused
    for value in (0, 31, 32, 580, 3152, 123_456):
        encoded = encode_native_amount(value)
        assert decode_native_amount(encoded, 0) == (value, len(encoded))


def test_extract_game_state_leaves_seat_state_unread_when_the_seat_array_does_not_fit():
    table_id = 28248
    hand_id = 298328340
    payload = bytearray(
        native_state_payload(
            table_id, hand_id, [(native_seat_block(funds=580, active=True), native_player_record(9, "alice"))]
        )
    )
    payload[14] = 0x07  # neither an empty nor an occupied seat

    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), bytes(payload)), {table_id})

    assert snapshot is not None
    assert snapshot.players == (NativePlayerIdentity(9, "alice"),)


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
    assert extract_native_boards(snapshot, "omaha") == (expected,)


def test_extract_native_boards_ignores_preflop_state():
    table_id = 24812
    hand_id = 298328325
    payload = (
        b"\x16\0state\xf0\xbf\0\0\0"
        + bytes([3, 30, 24, 14])
        + (b"\0" * 14)
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + b"\x01"
    )
    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert snapshot is not None
    assert extract_native_boards(snapshot, "holdem") == ()


def test_extract_native_boards_reads_double_board_bomb_pot():
    table_id = 299657213
    hand_id = 301461736
    b1_cards = [34, 37, 1, 47, 33]  # 10h, Jd, 2d, Ks, 10d
    b2_cards = [42, 14, 43, 18, 38]  # Qh, 5h, Qs, 6h, Jh
    prefix = b"\x16\0state\xf0\xbf\0"
    board_bytes = bytes([len(b1_cards), *b1_cards, len(b2_cards), *b2_cards])
    footer = b"\0" * 10
    payload = (
        prefix
        + board_bytes
        + footer
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + bytes([2])
    )
    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert snapshot is not None
    boards = extract_native_boards(snapshot, "holdem")
    assert len(boards) == 2
    assert boards[0] == ("10h", "Jd", "2d", "Ks", "10d")
    assert boards[1] == ("Qh", "5h", "Qs", "6h", "Jh")
    assert extract_native_board(snapshot, "holdem") == boards[0]


def test_extract_native_boards_reads_run_it_twice_at_showdown_with_hand_eval_strings():
    table_id = 299672838
    hand_id = 301461752
    b1_cards = [31, 38, 10, 46, 12]  # 9s, Jh, 4h, Kh, 5c
    b2_cards = [31, 38, 10, 8, 24]  # 9s, Jh, 4h, 4c, 8c (shared flop: 9s, Jh, 4h)
    eval_text1 = b"Flush high Kh"
    eval_text2 = b"Two Pairs 9 4 and K"
    strings_block = (
        len(eval_text1).to_bytes(2, "little")
        + eval_text1
        + len(eval_text2).to_bytes(2, "little")
        + eval_text2
        + b"\0\0"
    )
    prefix = b"\x16\0state\xf0\xbf" + strings_block
    board_bytes = bytes([len(b1_cards), *b1_cards, len(b2_cards), *b2_cards])
    footer = b"\0" * 10
    payload = (
        prefix
        + board_bytes
        + footer
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + bytes([5])
    )
    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert snapshot is not None
    boards = extract_native_boards(snapshot, "omaha")
    assert len(boards) == 2
    assert boards[0] == ("9s", "Jh", "4h", "Kh", "5c")
    assert boards[1] == ("9s", "Jh", "4h", "4c", "8c")


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
    action = native_action_event(8, 80, 2)
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


def test_extract_native_animation_events_reads_a_long_amount_and_the_seat_after_it():
    table_id = 28248
    hand_id = 298328340
    payload = native_state_payload(
        table_id,
        hand_id,
        [(native_seat_block(funds=900), native_player_record(9, "alice"))],
        events=native_event_list(native_action_event(9, 40, 0), native_action_event(3, 5, 0)),
    )

    events = extract_native_animation_events(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    # ``09 09 48 01 00 00``: 40 chips from seat 0, which a one-byte read took for 72 from seat 1.
    assert [(event.action_code, event.funds, event.seat_idx) for event in events] == [(9, 40, 0), (3, 5, 0)]


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
    assert native_action_street("omaha", 5, (9, 6, 3)) == "RIVER"


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
        "Game changes to NL Hold'em 25/50": ("hold", "holdem", "nl"),
        "Game changes to PL Omaha 15/30": ("hold", "omahahi", "pl"),
        "Game changes to PL Courchevel 15/30": ("hold", "cour_hi", "pl"),
        "Game changes to PL Big O 15/30": ("hold", "5_omaha8", "pl"),
        "Game changes to FL Razz 25/50": ("stud", "razz", "fl"),
        "Game changes to FL Badugi 75/150": ("draw", "badugi", "fl"),
        "Game changes to PL Drawmaha 25/50": ("draw", "drawmaha_high", "pl"),
        "Game changes to PL Drawmaha 2-7 25/50": ("draw", "drawmaha", "pl"),
        "Game changes to PL Drawmadugi 25/50": ("draw", "drawmadugi", "pl"),
    }
    for text, (base, category, limit) in cases.items():
        parsed = parse_native_game_change(_game_change_msg(1, text).payload)
        assert (parsed["base"], parsed["category"], parsed["limit_type"]) == (base, category, limit)
        if category in {"cour_hi", "5_omaha8"}:
            assert parsed["family"] == "omaha"
        if category.startswith("drawmaha") or category in {"drawmadugi", "sviten"}:
            assert parsed["family"] == "drawmaha"


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


def _stud_seat(player_id, name, cards, seat_idx, funds=1500):
    """A seated stud player whose state block carries ``cards`` (0xFF hidden)."""
    block = native_seat_block(funds=funds, cards=bytes([len(cards), *cards]))
    return NativePlayerIdentity(player_id, name, funds, False, 0, seat_idx=seat_idx, state_block=block)


def _stud_snapshot(*players):
    return NativeGameStateSnapshot(datetime.now(UTC), 1, 1, 5, tuple(players), b"")


HIDDEN = 0xFF


def test_extract_native_stud_upcards_maps_streets_and_hidden_slots():
    snap = _stud_snapshot(_stud_seat(1, "alice", [HIDDEN, HIDDEN, 37, 40, 43, HIDDEN], seat_idx=2))

    rows = extract_native_stud_upcards([snap])

    assert rows == [
        {
            "player": "alice",
            "seat_idx": 2,
            "up_cards": {
                "THIRD": card_id_to_str(37),
                "FOURTH": card_id_to_str(40),
                "FIFTH": card_id_to_str(43),
                "SIXTH": None,
            },
        }
    ]


def test_extract_native_stud_upcards_reads_each_seat_its_own_block():
    # Each player's cards come from their own seat block, so the bring-in's low
    # card stays with the bring-in (#829: it used to land on the next player).
    rows = extract_native_stud_upcards(
        [
            _stud_snapshot(
                _stud_seat(1, "alice", [HIDDEN, HIDDEN, 0], seat_idx=0),
                _stud_seat(2, "bob", [HIDDEN, HIDDEN, 50], seat_idx=3),
            )
        ]
    )

    assert {row["player"]: row["up_cards"]["THIRD"] for row in rows} == {
        "alice": card_id_to_str(0),
        "bob": card_id_to_str(50),
    }


def test_extract_native_stud_upcards_merges_snapshots_slot_by_slot():
    early = _stud_snapshot(_stud_seat(1, "alice", [HIDDEN, HIDDEN, 37], seat_idx=0))
    late = _stud_snapshot(_stud_seat(1, "alice", [HIDDEN, HIDDEN, 37, 40, 43], seat_idx=0))

    rows = extract_native_stud_upcards([early, late])

    assert list(rows[0]["up_cards"]) == ["THIRD", "FOURTH", "FIFTH"]


def test_extract_native_stud_upcards_drops_a_seat_whose_readings_disagree():
    first = _stud_snapshot(_stud_seat(1, "alice", [HIDDEN, HIDDEN, 37], seat_idx=0))
    second = _stud_snapshot(_stud_seat(1, "alice", [HIDDEN, HIDDEN, 38], seat_idx=0))

    assert extract_native_stud_upcards([first, second]) == []


def test_extract_native_stud_upcards_rejects_duplicate_cards():
    # The same card id in two players means a false match, so nothing decodes.
    snap = _stud_snapshot(
        _stud_seat(1, "alice", [HIDDEN, HIDDEN, 37, 40], seat_idx=0),
        _stud_seat(2, "bob", [HIDDEN, HIDDEN, 37, 44], seat_idx=1),
    )
    assert extract_native_stud_upcards([snap]) == []


def test_extract_native_stud_upcards_reads_visible_down_cards():
    # The local player always sees their own down cards; anyone else only at showdown.
    hidden = _stud_snapshot(_stud_seat(1, "alice", [HIDDEN, HIDDEN, 37, 40, 43, 44, HIDDEN], seat_idx=0))
    revealed = _stud_snapshot(_stud_seat(1, "alice", [1, 12, 37, 40, 43, 44, 31], seat_idx=0))

    rows = extract_native_stud_upcards([hidden, revealed])

    assert rows[0]["down_cards"] == {"THIRD": [card_id_to_str(1), card_id_to_str(12)], "SEVENTH": card_id_to_str(31)}
    assert "SEVENTH" not in rows[0]["up_cards"]


def test_native_seat_cards_find_the_cards_after_variable_length_amounts():
    for funds in (0, 31, 1500):
        block = native_seat_block(funds=funds, cards=bytes([3, HIDDEN, HIDDEN, 30]))
        assert native_seat_cards(block) == bytes([HIDDEN, HIDDEN, 30])
    assert native_seat_cards(b"\x01\x02\x80") is None


def test_native_stud_hole_cards_follow_the_text_importers_street_shape():
    rows = [
        {
            "player": "alice",
            "seat_idx": 0,
            "up_cards": {"THIRD": "Td", "FOURTH": "9s"},
            "down_cards": {"THIRD": ["5h", "3c"], "SEVENTH": "2d"},
        },
        {"player": "bob", "seat_idx": 1, "up_cards": {"THIRD": "Kc"}},
        {"player": "watcher", "seat_idx": 2, "up_cards": {"THIRD": "Ah"}},
    ]

    assert native_stud_hole_cards(rows, {"alice", "bob"}) == [
        {"player": "alice", "street": "THIRD", "open": ["Td"], "closed": ["5h", "3c"], "dealt": True},
        {"player": "alice", "street": "FOURTH", "open": ["9s"], "closed": []},
        {"player": "alice", "street": "SEVENTH", "open": [], "closed": ["2d"]},
        {"player": "bob", "street": "THIRD", "open": ["Kc"], "closed": [], "dealt": True},
    ]


def test_extract_native_stud_forced_bets_preserves_indexes_and_exact_amounts():
    steps = [
        {
            "native_events": [
                {
                    "type_code": 9,
                    "action_code": 4,
                    "funds_byte": 24,
                    "native_index": index,
                    "action_street_evidence": "BLINDSANTES",
                }
                for index in (0, 1, 3, 4)
            ]
        },
        {
            "native_events": [
                {
                    "type_code": 9,
                    "action_code": 5,
                    "funds_byte": 80,
                    "native_index": 3,
                    "action_street_evidence": "THIRD",
                }
            ]
        },
    ]

    forced = extract_native_stud_forced_bets(steps)

    assert [ante["amount_native"] for ante in forced["antes"]] == [24, 24, 24, 24]
    assert [ante["native_index"] for ante in forced["antes"]] == [0, 1, 3, 4]
    assert forced["bring_in"]["native_index"] == 3
    assert forced["bring_in"]["amount_native"] == 60


def test_extract_native_stud_forced_bets_rejects_inconsistent_antes():
    steps = [
        {
            "native_events": [
                {
                    "type_code": 9,
                    "action_code": 4,
                    "funds_byte": amount,
                    "native_index": index,
                    "action_street_evidence": "BLINDSANTES",
                }
                for index, amount in enumerate((12, 16))
            ]
        }
    ]

    assert extract_native_stud_forced_bets(steps) == {"antes": [], "bring_in": None}


def test_derive_native_stud_betting_structure_and_deterministic_action_amounts():
    forced = {
        "antes": [{"amount_native": 16}, {"amount_native": 16}],
        "bring_in": None,
    }
    structure = derive_native_stud_betting_structure(forced)
    steps = [
        {
            "step_num": 1,
            "native_events": [
                {
                    "event_index": event_index,
                    "action_name_evidence": action,
                    "player_name_evidence": "BingoBob",
                    "action_street_evidence": street,
                    "native_index": 4,
                    "funds_byte": 99,
                    "player_evidence_source": "previous_unique_active_player",
                    "raw_hex": "raw",
                }
                for event_index, (action, street) in enumerate(
                    (("bet", "FIFTH"), ("raise", "FOURTH"), ("call", "FOURTH"))
                )
            ],
        }
    ]

    actions = _build_native_action_evidence(steps, structure)

    assert structure == {
        "ante": 16,
        "bring_in": 40,
        "small_bet": 80,
        "big_bet": 160,
        "source": "swc_observed_fixed_limit_stud_ante_ratios",
    }
    assert actions[0]["amount_native"] == 160
    assert actions[1]["raise_increment_native"] == 80
    assert actions[1]["amount_native_minimum"] == 80
    assert "amount_native" not in actions[2]
    assert actions[2]["amount_native_minimum"] == 80


def test_native_stud_stateful_amounts_resolve_complete_bring_in_call_prefix():
    structure = {
        "ante": 12,
        "bring_in": 30,
        "small_bet": 60,
        "big_bet": 120,
        "source": "test",
    }

    def step(step_num, player, action):
        return {
            "step_num": step_num,
            "native_events": [
                {
                    "event_index": 0,
                    "action_name_evidence": action,
                    "player_name_evidence": player,
                    "action_street_evidence": "THIRD",
                    "native_index": step_num,
                    "funds_byte": 0,
                    "player_evidence_source": "previous_unique_active_player",
                    "raw_hex": "raw",
                }
            ],
        }

    actions = _build_native_action_evidence(
        [step(1, "Allinred", "bring_in"), step(2, "BingoBob", "call"), step(3, "Tw4rriorz", "call")],
        structure,
    )

    assert [action["amount_native"] for action in actions] == [30, 30, 30]
    assert actions[1]["amount_evidence_source"] == "complete_named_native_betting_prefix"


def test_native_stud_stateful_amounts_advance_through_anonymous_fixed_raise():
    structure = {
        "ante": 12,
        "bring_in": 30,
        "small_bet": 60,
        "big_bet": 120,
        "source": "test",
    }

    def event(step_num, action, player=None):
        item = {
            "event_index": 0,
            "action_name_evidence": action,
            "action_street_evidence": "THIRD",
            "native_index": step_num,
            "funds_byte": 0,
            "raw_hex": "raw",
        }
        if player:
            item.update(
                player_name_evidence=player,
                player_evidence_source="previous_unique_active_player",
            )
        return {"step_num": step_num, "native_events": [item]}

    steps = [
        event(1, "bring_in", "Allinred"),
        event(2, "call", "BingoBob"),
        event(3, "raise"),
        event(4, "call", "BingoBob"),
    ]
    actions = _build_native_action_evidence(steps, structure)

    assert [action["amount_native"] for action in actions if action["action"] == "call"] == [30, 30]


def test_native_hand_seat_map_keeps_only_seats_every_snapshot_agrees_on():
    alice = NativePlayerIdentity(7, "alice", seat_idx=0)
    bob = NativePlayerIdentity(8, "bob", seat_idx=2)
    carol_in_bobs_seat = NativePlayerIdentity(9, "carol", seat_idx=2)
    unseated = NativePlayerIdentity(10, "dave")

    def snapshot(*players):
        return NativeGameStateSnapshot(datetime.now(UTC), 1, 2, 1, players, b"")

    assert _native_hand_seat_map([snapshot(alice, bob, unseated), snapshot(alice, bob)]) == {0: alice, 2: bob}
    assert _native_hand_seat_map([snapshot(alice, bob), snapshot(alice, carol_in_bobs_seat)]) == {0: alice}
    alice_elsewhere = replace(alice, seat_idx=3)
    assert _native_hand_seat_map([snapshot(alice, bob), snapshot(alice_elsewhere, bob)]) == {2: bob}


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
    return NativeGameStateSnapshot(datetime.now(UTC), 297862828, 298330169, round_number, (), payload)


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
        return native_state_payload(
            table_id,
            hand_id,
            [(native_seat_block(funds=stack), native_player_record(7, name.decode())), None],
            game_code=b"OP",
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
    assert hand["players"][0]["starting_stack"] is None
    assert hand["players"][0]["native_opaque_funds_value"] == 584
    assert hand["players"][0]["seat_idx"] is None
    assert hand["players"][0]["roster_index"] == 0
    assert hand["players"][0]["native_status_values"] == [0]
    assert hand["steps"][1]["stacks"] == {"Player": 580}
    assert hand["steps"][1]["diff"]["candidates"][0]["amount_delta"] == "-4"
    assert hand["steps"][1]["native_events"] == []
    assert hand["metadata"]["player_funds_field"] == "native_seat_funds_amount"
    assert hand["metadata"]["importability"]["status"] == "capture_only"
    assert hand["actions"] == []
    assert hand["action_evidence"] == []
    assert hand["metadata"]["importability"]["poker_event_count"] == 0
    assert "hand start is not fully observed" in hand["metadata"]["importability"]["reasons"][0]


def test_normalize_native_hands_decodes_double_board_bomb_pot_and_streets():
    captured_at = datetime.now(UTC)
    table_id = 299657213
    hand_id = 301461736
    name = b"Player"
    table_name = b"No-Rake Micro Stakes Double Board Bomb Pots #1"
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
    b1_cards = [34, 37, 1, 47, 33]  # 10h, Jd, 2d, Ks, 10d
    b2_cards = [42, 14, 43, 18, 38]  # Qh, 5h, Qs, 6h, Jh
    player = (
        (7).to_bytes(4, "little")
        + len(name).to_bytes(2, "little")
        + name
        + b"\0\0prefix\xf0\xbf\0\x16\x80"
        + (b"\0" * 6)
        + (580).to_bytes(3, "little")
        + b"suffix"
    )
    prefix = b"\x16\0" + player + b"\xf0\xbf\0"
    board_bytes = bytes([len(b1_cards), *b1_cards, len(b2_cards), *b2_cards])
    footer = b"\0" * 10
    state_payload = (
        prefix
        + board_bytes
        + footer
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + (b"\0" * 5)
        + bytes([2])
    )
    hands = normalize_native_hands(
        [
            NativeProtocolMessage(captured_at, table_payload),
            NativeProtocolMessage(captured_at, state_payload, peer_port=20013),
        ],
        raw_ref="capture.raw",
    )

    assert len(hands) == 1
    hand = hands[0]
    assert hand["board"] == ["10h", "Jd", "2d", "Ks", "10d"]
    assert hand["run_it_times"] == 2
    assert hand["double_board"] is True
    # The boards prove a double board; the bomb-pot amount does not follow from
    # them. This snapshot carries no ante action, so none is claimed -- the table
    # being named "Bomb Pots" is not evidence about this hand.
    assert hand["bomb_pot"] == 0
    assert hand["community"] == {
        "FLOP": ["10h", "Jd", "2d"],
        "TURN": ["Ks"],
        "RIVER": ["10d"],
        "FLOP2": ["Qh", "5h", "Qs"],
        "TURN2": ["6h"],
        "RIVER2": ["Jh"],
    }
    assert len(hand["boards"]) == 2
    assert hand["boards"][0] == {"FLOP": ["10h", "Jd", "2d"], "TURN": ["Ks"], "RIVER": ["10d"]}
    assert hand["boards"][1] == {"FLOP": ["Qh", "5h", "Qs"], "TURN": ["6h"], "RIVER": ["Jh"]}
    assert hand["steps"][0]["boards"] == [
        ["10h", "Jd", "2d", "Ks", "10d"],
        ["Qh", "5h", "Qs", "6h", "Jh"],
    ]


def test_native_board_output_distinguishes_shared_flop_run_it_twice():
    output = _native_board_output(
        (
            ("9s", "Jh", "4h", "Kh", "5c"),
            ("9s", "Jh", "4h", "4c", "8c"),
        ),
    )

    assert output["double_board"] is False
    # No ante in this hand's evidence, so no bomb pot -- whatever the table is called.
    assert output["bomb_pot"] == 0
    assert output["run_it_times"] == 2


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

    audit = audit_native_hand(
        steps,
        [],
        action_evidence=[
            {"action": "small_blind", "amount_native": 5},
            {"action": "big_blind", "amount_native": 10},
        ],
    )

    assert audit["resolved_poker_event_count"] == 2
    assert audit["unresolved_poker_event_count"] == 1
    assert audit["unresolved_by_action"] == {"fold": 1}
    assert audit["unresolved_forced_bet_event_count"] == 0
    assert audit["unresolved_betting_event_count"] == 1
    assert audit["unresolved_betting_by_street"] == {"UNKNOWN": 1}
    assert audit["captured_action_players_complete"] is False
    assert audit["settlement_conservation_complete"] is False
    assert audit["resolved_action_amount_count"] == 2
    assert audit["resolved_action_amount_total"] == 2
    assert audit["bounded_action_amount_count"] == 0
    assert audit["has_small_blind"] is True
    assert audit["has_big_blind"] is True
    assert audit["has_collection"] is False
    assert audit["dealer_hand_started"] is False
    assert audit["dealer_hand_complete"] is False
    assert audit["importable"] is False
    assert audit["resolved_native_type_9_player_count"] == 1
    assert audit["native_type_9_event_count"] == 2


def test_audit_native_stud_accounting_exposes_unobserved_contributions():
    accounting = audit_native_stud_accounting(
        [
            {"action": "bring_in", "amount_native": 30},
            {"action": "call", "amount_native_minimum": 60},
        ],
        {"antes": [{"amount_native": 12}, {"amount_native": 12}]},
        [{"amount_native": 300}],
        [{"amount_native": 30}],
    )

    assert accounting["required_contribution_total_native"] == 330
    assert accounting["decoded_contribution_minimum_native"] == 114
    assert accounting["unexplained_contribution_minimum_native"] == 216
    assert accounting["complete"] is False


def test_add_native_funds_byte_amounts_requires_exact_settlement_conservation():
    actions = [
        {"action": "small_blind", "funds_byte": 2},
        {"action": "big_blind", "funds_byte": 4},
        {"action": "call", "funds_byte": 2},
        {"action": "check", "funds_byte": 0, "amount_native": 0},
    ]

    assert add_native_funds_byte_amounts_if_conserved(actions, [{"amount_native": 8}], []) is True
    assert [action.get("amount_native") for action in actions] == [2, 4, 2, 0]
    assert (
        add_native_funds_byte_amounts_if_conserved(
            [{"action": "bet", "funds_byte": 8}],
            [{"amount_native": 9}],
            [],
        )
        is False
    )


def test_extract_native_blind_structure_requires_both_exact_blinds():
    assert extract_native_blind_structure(
        [
            {"action": "small_blind", "amount_native": 2},
            {"action": "big_blind", "amount_native": 4},
        ]
    ) == {"sb": 2, "bb": 4}
    assert extract_native_blind_structure([{"action": "small_blind", "amount_native": 2}]) == {
        "sb": 0,
        "bb": 0,
    }


def test_build_native_canonical_actions_converts_incremental_raise_to_total():
    evidence = [
        {"action": "small_blind", "player": "Villain", "street": "BLINDSANTES", "amount_native": 2},
        {"action": "big_blind", "player": "Hero", "street": "PREFLOP", "amount_native": 4},
        {"action": "call", "player": "Villain", "street": "PREFLOP", "amount_native": 2},
        {"action": "raise", "player": "Hero", "street": "PREFLOP", "amount_native": 8},
        {"action": "call", "player": "Villain", "street": "PREFLOP", "amount_native": 8},
        {"action": "bet", "player": "Hero", "street": "FLOP", "amount_native": 24},
        {"action": "fold", "player": "Villain", "street": "FLOP", "amount_native": 0},
    ]

    actions = build_native_canonical_actions(evidence, [{"player": "Hero", "amount_native": 24}])

    assert actions[3] == {"type": "raises", "player": "Hero", "street": "PREFLOP", "amount": 8, "to": 12}
    assert actions[-1] == {"type": "uncalled", "player": "Hero", "street": "FLOP", "amount": 24}


def test_build_native_canonical_actions_rejects_unproven_amounts():
    assert (
        build_native_canonical_actions(
            [{"action": "call", "player": "Hero", "street": "PREFLOP"}],
            [],
        )
        == []
    )


def test_parse_native_outbound_seat_request_decodes_exact_requested_stack():
    payload = (
        b"\x0b\x00"
        + b"\x33\x00\x00\x00"
        + (24812).to_bytes(4, "little")
        + (4).to_bytes(4, "little")
        + (856).to_bytes(4, "little")
        + (b"\0" * 25)
    )
    message = NativeProtocolMessage(datetime.now(UTC), payload, direction="sent")

    assert parse_native_outbound_seat_request(message) == {
        "timestamp": message.captured_at.isoformat(),
        "table_id": 24812,
        "seat_idx": 4,
        "requested_stack_native": 856,
        "source": "swc_native_outbound_type_11_seat_request",
    }


def test_extract_native_table_player_stacks_decodes_type_23_roster():
    def player_record(player_id, name, stack, suffix=b""):
        encoded = name.encode()
        return (
            player_id.to_bytes(4, "little")
            + len(encoded).to_bytes(2, "little")
            + encoded
            + b"\0\0"
            + encode_native_amount(stack).ljust(3, b"\0")
            + suffix
        )

    payload = (
        b"\x17\x00"
        + b"\0" * 8
        + (24812).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + player_record(1, "Villain", 1608, b"flags")
        + player_record(2, "Hero", 856)
    )
    message = NativeProtocolMessage(datetime.now(UTC), payload, direction="received")

    assert extract_native_table_player_stacks(message) == {
        "timestamp": message.captured_at.isoformat(),
        "table_id": 24812,
        "players": [
            {"player_id": 1, "name": "Villain", "starting_stack": 1608},
            {"player_id": 2, "name": "Hero", "starting_stack": 856},
        ],
        "source": "swc_native_received_type_23_table_roster",
    }


def test_extract_native_hero_hole_cards_uses_block_before_local_record():
    payload = b"prefix" + b"Villain" + b"\0\0flags\x04\x2f\x03\x08\x0dtrail" + b"\x01\0\0\0\x04\0" + b"Hero" + b"suffix"
    snapshot = NativeGameStateSnapshot(
        datetime.now(UTC),
        1,
        2,
        1,
        (NativePlayerIdentity(1, "Villain"), NativePlayerIdentity(4, "Hero")),
        payload,
    )

    assert extract_native_hero_hole_cards([snapshot], "Hero", 4) == {
        "player": "Hero",
        "cards": ["Ks", "2s", "4c", "5d"],
        "street": "PREFLOP",
        "source": "native_private_deal_before_local_player_record",
    }


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


def test_build_tap_cross_platform(tmp_path, monkeypatch):
    """The compile itself, on whichever platform this is running.

    Skipped where no compiler is installed rather than failed: this asserts that
    the C builds, and a developer machine without a toolchain -- which is most
    Windows machines -- cannot answer that question either way. What such a
    machine *should* get is covered by
    test_swc_tap_build_reports_a_missing_compiler.
    """
    from fpdb_3_legacy.capture import swc_client, swc_tap_build
    from fpdb_3_legacy.capture.swc_tap_build import COMPILERS

    system_name = platform.system()
    if not any(shutil.which(name) for name in COMPILERS.get(system_name, ())):
        pytest.skip(f"no C compiler on this {system_name} machine")

    # Build into a scratch dir, not the user's ~/.fpdb tap: get_tap_library_path
    # / get_injector_path read swc_tap_build.BUILD_DIR at call time, so this is
    # the global that actually redirects the output (and avoids colliding with a
    # tap DLL that may be loaded -- and therefore locked -- in a live client).
    monkeypatch.setattr(swc_tap_build, "BUILD_DIR", tmp_path)
    tap_path = swc_client.build_tap(force=True)
    assert tap_path.exists()
    assert tap_path.name in ("libswc_native_tap.dylib", "libswc_native_tap.so", "swc_native_tap.dll")
    if system_name == "Windows":
        # Windows also builds the same-bitness injector alongside the tap.
        assert (tmp_path / "swc_inject.exe").exists()


def _tailing_thread(tmp_path, monkeypatch, hands):
    """A tailing thread whose decode stage yields `hands`, wired to a real archive."""
    from fpdb_3_legacy import swc_native_capture
    from fpdb_3_legacy.GuiAutoImport import SwCNativeTailingThread

    monkeypatch.setattr(swc_native_capture.NativeProtocolStream, "feed", lambda _self, records: list(records))
    monkeypatch.setattr(swc_native_capture, "normalize_native_hands", lambda messages, raw_ref=None: hands)

    raw = tmp_path / "swc-native.raw"
    raw.write_bytes(_record())
    return SwCNativeTailingThread(raw_path=raw), raw


def test_swc_native_tailing_yields_decoded_hands(tmp_path, monkeypatch):
    """The original test only asserted a clean stop, so the decode path was free to break."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailing_thread(tmp_path, monkeypatch, [hand])

    assert thread.poll_once() == [hand]


def test_swc_native_tailing_does_not_reimport_a_known_hand(tmp_path, monkeypatch):
    hand = {"table_id": 7, "hand_id": 1234}
    thread, raw = _tailing_thread(tmp_path, monkeypatch, [hand])
    assert thread.poll_once() == [hand]

    with raw.open("ab") as handle:
        handle.write(_record(b"more"))

    assert thread.poll_once() == []


def _tailing_thread_snapshots(tmp_path, monkeypatch, snapshots):
    """A tailing thread whose decode stage yields one list of hands per poll."""
    from fpdb_3_legacy import swc_native_capture
    from fpdb_3_legacy.GuiAutoImport import SwCNativeTailingThread

    stages = [list(stage) for stage in snapshots]
    monkeypatch.setattr(swc_native_capture.NativeProtocolStream, "feed", lambda _self, records: list(records))
    monkeypatch.setattr(
        swc_native_capture,
        "normalize_native_hands",
        lambda messages, raw_ref=None: stages.pop(0) if stages else [],
    )

    raw = tmp_path / "swc-native.raw"
    raw.write_bytes(_record())
    return SwCNativeTailingThread(raw_path=raw), raw


def _append(raw, payload=b"more"):
    """Another record, so the next poll has something new to read."""
    with raw.open("ab") as handle:
        handle.write(_record(payload))


def test_swc_native_tailing_reoffers_a_hand_that_later_becomes_importable(tmp_path, monkeypatch):
    """The tailer polls every 2.5s, so a hand is normally first seen mid-play.

    Retiring the hand on that first emission discarded it for good: the later
    records that complete its actions and settlement were decoded, and then
    suppressed. Only a terminal import result may retire a key.
    """
    partial = {"table_id": 7, "hand_id": 1234, "actions": []}
    complete = {"table_id": 7, "hand_id": 1234, "actions": [{"type": "big blind"}]}
    thread, raw = _tailing_thread_snapshots(tmp_path, monkeypatch, [[partial], [complete], [complete]])

    assert thread.poll_once() == [partial]

    _append(raw)
    assert thread.poll_once() == [complete]

    _append(raw)
    assert thread.poll_once() == []  # an unchanged snapshot is not offered again


def test_swc_native_tailing_stops_after_a_terminal_import_result(tmp_path, monkeypatch):
    hand = {"table_id": 7, "hand_id": 1234}
    thread, raw = _tailing_thread_snapshots(tmp_path, monkeypatch, [[hand], [{**hand, "actions": [1]}]])
    assert thread.poll_once() == [hand]

    thread.mark_hand_complete(hand)
    _append(raw)

    assert thread.poll_once() == []


def test_swc_native_tailing_reports_a_capture_only_hand_once(tmp_path, monkeypatch):
    """A skipped hand is re-offered as it grows, so the log line must not repeat."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, _raw = _tailing_thread(tmp_path, monkeypatch, [hand])

    assert thread.note_capture_only(hand) is True
    assert thread.note_capture_only(hand) is False

    thread.mark_hand_complete(hand)

    assert thread.note_capture_only(hand) is True


def test_swc_native_tailing_reoffers_a_hand_once_its_retry_delay_elapsed(tmp_path, monkeypatch):
    """A hand that produced no more records still has to be offered again.

    The reasons an import is refused clear on their own -- an import cycle
    finishes, the database comes back, the text history of the hand lands -- and
    none of them appends anything to the capture.
    """
    hand = {"table_id": 7, "hand_id": 1234}
    thread, raw = _tailing_thread(tmp_path, monkeypatch, [hand])
    assert thread.poll_once() == [hand]

    thread.retry_hand(hand)
    _append(raw)
    assert thread.poll_once() == []  # still inside the delay

    # The deadline is moved rather than slept through. A short backoff plus a
    # slightly longer sleep is a race against the clock's own resolution: on
    # Windows time.monotonic() advances in ~16ms steps, so a 10ms margin read
    # as no time passing at all and the hand stayed deferred.
    with thread._state_lock:
        thread._retry_after[(7, 1234)] = time.monotonic() - 1
    _append(raw)
    assert thread.poll_once() == [hand]


def test_swc_native_tailing_stops_retrying_a_hand_that_never_imports(tmp_path, monkeypatch):
    """A hand that will never be importable must not reach the database forever."""
    hand = {"table_id": 7, "hand_id": 1234}
    thread, raw = _tailing_thread(tmp_path, monkeypatch, [hand])
    thread.MAX_RETRY_OFFERS = 2
    thread.RETRY_BACKOFF_SECONDS = 0.0
    thread.RETRY_BACKOFF_CAP_SECONDS = 0.0
    assert thread.poll_once() == [hand]

    for _ in range(4):
        thread.retry_hand(hand)
        _append(raw)
        thread.poll_once()

    assert thread._retry_offers[(7, 1234)] == 2
    _append(raw)
    assert thread.poll_once() == []


def test_swc_native_tailing_renews_the_retry_budget_when_a_snapshot_changes(tmp_path, monkeypatch):
    """The budget bounds how often a refused snapshot is repeated, not a hand still being played."""
    first = {"table_id": 7, "hand_id": 1234, "actions": []}
    second = {"table_id": 7, "hand_id": 1234, "actions": [1]}
    stages = [[first], [first], [first], [second], [second]]
    thread, raw = _tailing_thread_snapshots(tmp_path, monkeypatch, stages)
    thread.MAX_RETRY_OFFERS = 1
    thread.RETRY_BACKOFF_SECONDS = 0.0
    thread.RETRY_BACKOFF_CAP_SECONDS = 0.0
    assert thread.poll_once() == [first]

    thread.retry_hand(first)
    _append(raw)
    assert thread.poll_once() == [first]  # the one offer it is allowed

    thread.retry_hand(first)
    _append(raw)
    assert thread.poll_once() == []  # budget spent for this snapshot

    _append(raw)
    assert thread.poll_once() == [second]  # changed content is offered anyway

    thread.retry_hand(second)
    _append(raw)
    assert thread.poll_once() == [second]  # and that change renewed the budget


def test_a_terminal_result_cancels_a_pending_retry(tmp_path, monkeypatch):
    hand = {"table_id": 7, "hand_id": 1234}
    thread, raw = _tailing_thread(tmp_path, monkeypatch, [hand])
    thread.RETRY_BACKOFF_SECONDS = 0.0
    thread.RETRY_BACKOFF_CAP_SECONDS = 0.0
    assert thread.poll_once() == [hand]

    thread.retry_hand(hand)
    thread.mark_hand_complete(hand)
    _append(raw)

    assert thread.poll_once() == []
    assert thread._retry_after == {}


def test_swc_native_tailing_consumes_the_archive_once(tmp_path, monkeypatch):
    """A poll must advance past what it read instead of re-parsing from zero."""
    thread, raw = _tailing_thread(tmp_path, monkeypatch, [])
    thread.poll_once()

    assert thread._offset == raw.stat().st_size


def test_swc_native_tailing_thread_stops_cleanly(tmp_path, monkeypatch):
    thread, _raw = _tailing_thread(tmp_path, monkeypatch, [])
    thread.start()
    thread.stop()
    thread.wait(2000)

    assert not thread.isRunning()


def test_a_chip_animation_with_a_long_amount_keeps_the_rest_of_its_event_list():
    table_id = 28248
    hand_id = 298328340
    chips = b"\x04\x00" + encode_native_amount(40) + b"\x02"  # an ante of 40, seat 2: six bytes, not four
    payload = native_state_payload(
        table_id,
        hand_id,
        [(native_seat_block(funds=900), native_player_record(9, "alice")), None, None],
        events=native_event_list(chips, native_action_event(4, 40, 2)),
    )

    events = extract_native_animation_events(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert [(event.type_code, event.funds, event.seat_idx) for event in events] == [(4, 40, 2), (9, 40, 2)]


def test_the_seat_walk_steps_over_a_showdown_label():
    table_id = 28248
    hand_id = 298328340
    payload = native_state_payload(
        table_id,
        hand_id,
        [
            (native_seat_block(funds=100), native_player_record(9, "alice", label="Pair of 3s and K Q 7")),
            None,
            (native_seat_block(funds=200), native_player_record(10, "bob")),
        ],
    )

    snapshot = extract_game_state(NativeProtocolMessage(datetime.now(UTC), payload), {table_id})

    assert [(player.name, player.seat_idx, player.stack_units) for player in snapshot.players] == [
        ("alice", 0, 100),
        ("bob", 2, 200),
    ]
