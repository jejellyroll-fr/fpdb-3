"""SwC native capture: tournament tables announced by a class-31 descriptor (#829).

A tournament table the room seats the player at can arrive with no class-34
descriptor, only a class-31 one. Without reading it the table had no entry in
the table map and every hand played there was dropped. The ids and names here
are made up; the byte layout is the captured one.
"""

from datetime import UTC, datetime

from fpdb_3_legacy.swc_native_capture import (
    NativeProtocolMessage,
    NativeTableInfo,
    _native_table_max_seats,
    _native_table_signature,
    _resolve_native_hand_game,
    extract_table_info,
    normalize_native_hands,
    summarize_native_hands,
)

TOURNAMENT_ID = 123456789
TABLE_ID = 123460001
HAND_ID = 123460002
TOURNAMENT_NAME = b"Sample Freeroll - 7-Card Stud"
#: The block after the name: ``FT`` (fixed limit, tournament), ``03``, 6 seats, ``00``.
TOURNAMENT_TRAILER = bytes([10, 20, 0]) + b"FT" + bytes([3, 6, 0, 0, 4])


def _class_31(
    *,
    tournament_id: int = TOURNAMENT_ID,
    repeated_tournament_id: int | None = None,
    table_id: int = TABLE_ID,
    name: bytes = TOURNAMENT_NAME,
    trailer: bytes = TOURNAMENT_TRAILER,
) -> bytes:
    repeated = tournament_id if repeated_tournament_id is None else repeated_tournament_id
    return (
        b"\x1f\0"
        + (0x01180D01).to_bytes(4, "little")
        + tournament_id.to_bytes(4, "little")
        + bytes(4)
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + repeated.to_bytes(4, "little")
        + b"S"
        + len(name).to_bytes(2, "little")
        + name
        + trailer
        + bytes(16)
    )


def _message(payload: bytes, **kwargs) -> NativeProtocolMessage:
    return NativeProtocolMessage(datetime(2026, 1, 1, tzinfo=UTC), payload, **kwargs)


def _state_payload(stack: int, name: bytes = b"Player") -> bytes:
    player = (
        (7).to_bytes(4, "little")
        + len(name).to_bytes(2, "little")
        + name
        + b"\0\0prefix\xf0\xbf\0\x16\x80"
        + bytes(6)
        + stack.to_bytes(3, "little")
        + b"suffix"
    )
    return b"\x16\0" + player + HAND_ID.to_bytes(4, "little") + TABLE_ID.to_bytes(4, "little") + bytes(5) + b"\x01"


def test_class_31_descriptor_names_the_tournament_table() -> None:
    info = extract_table_info(_message(_class_31()))

    assert info == NativeTableInfo(
        table_id=TABLE_ID,
        name=TOURNAMENT_NAME.decode(),
        tournament_id=TOURNAMENT_ID,
        family="stud",
        max_seats=6,
        limit_type="fl",
    )


def test_class_31_descriptor_whose_tournament_ids_disagree_is_not_read() -> None:
    assert extract_table_info(_message(_class_31(repeated_tournament_id=TOURNAMENT_ID + 1))) is None


def test_class_31_descriptor_needs_ids_and_a_whole_name() -> None:
    assert extract_table_info(_message(_class_31(tournament_id=0, repeated_tournament_id=0))) is None
    assert extract_table_info(_message(_class_31(table_id=0))) is None
    assert extract_table_info(_message(_class_31(name=b""))) is None
    truncated = _class_31()[: 26 + len(TOURNAMENT_NAME) - 1]
    assert extract_table_info(_message(truncated)) is None


def test_the_tournament_table_s_hands_are_no_longer_dropped() -> None:
    messages = [
        _message(_class_31()),
        _message(_state_payload(584), peer_port=20013),
        _message(_state_payload(580), peer_port=20013),
    ]

    [summary] = summarize_native_hands(messages)
    assert (summary.table_name, summary.family, summary.tournament_id) == (
        TOURNAMENT_NAME.decode(),
        "stud",
        TOURNAMENT_ID,
    )

    [hand] = normalize_native_hands(messages, raw_ref="capture.raw")
    assert hand["table_id"] == TABLE_ID
    assert hand["tournament_id"] == TOURNAMENT_ID
    assert hand["gametype"]["type"] == "tour"
    assert (hand["gametype"]["base"], hand["gametype"]["category"]) == ("stud", "studhi")
    assert hand["gametype"]["limitType"] == "fl"
    assert hand["gametype"]["maxSeats"] == 6


def test_a_tournament_signature_is_read_like_a_cash_one() -> None:
    """``R``ing tables close the block with ``12``, ``T``ournament ones with ``00``."""
    assert _native_table_signature(TOURNAMENT_TRAILER) == ("fl", "tour", 6)
    assert _native_table_signature(bytes([2, 4, 0]) + b"PR" + bytes([3, 9, 18, 0])) == ("pl", "ring", 9)
    assert _native_table_signature(bytes([10, 20, 0]) + b"UR" + bytes([3, 6, 18, 0])) == ("nl", "ring", 6)
    assert _native_table_max_seats(TOURNAMENT_TRAILER) == 6


def test_a_signature_whose_kind_marker_does_not_match_is_not_read() -> None:
    assert _native_table_signature(bytes([10, 20, 0]) + b"FT" + bytes([3, 6, 18, 0])) is None
    assert _native_table_signature(bytes([2, 4, 0]) + b"PR" + bytes([3, 9, 0, 0])) is None
    assert _native_table_signature(bytes([2, 4, 0]) + b"XR" + bytes([3, 9, 18, 0])) is None


def test_the_descriptor_s_limit_overrides_the_family_guess() -> None:
    """A fixed-limit Omaha table is not pot-limit just because it is Omaha."""
    table = NativeTableInfo(1, "FL Big O Table", None, "omaha", 8, "fl")
    assert _resolve_native_hand_game(None, table, 1, set())[3] == "fl"
    unsigned = NativeTableInfo(1, "No-Rake Micro Stakes PLO", None, "omaha", None, None)
    assert _resolve_native_hand_game(None, unsigned, 1, set())[3] == "pl"
