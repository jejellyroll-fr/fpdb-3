"""Build SwC native game-state payloads in the room's real wire layout.

A class-22 game state is a header, then one entry per seat: ``00`` for an empty
seat, or ``01`` + the seat's state block + the player's identity record. The
state block (funds, active bit, cards) comes *before* the name it belongs to,
and every amount is one byte under 32, else three (``decode_native_amount``).
"""

from __future__ import annotations


def encode_native_amount(value: int) -> bytes:
    """The native encoding of ``value``: one byte under 32, else 0x40|low5 + 16 bits."""
    if not 0 <= value < 1 << 21:
        raise ValueError(value)
    if value < 0x20:
        return bytes([value])
    return bytes([0x40 | (value & 0x1F)]) + (value >> 5).to_bytes(2, "little")


def native_seat_block(
    *, funds: int = 0, bet: int = 0, active: bool = False, flags: int = 0x16, cards: bytes = b"\0"
) -> bytes:
    """One seat's state block: ``01 <flags> 80 00 <status> 00*4 <funds> <bet> 00*6 <count> <cards>``."""
    return (
        b"\x01"
        + bytes([flags, 0x80, 0x00, 0x40 if active else 0x00])
        + bytes(4)
        + encode_native_amount(funds)
        + encode_native_amount(bet)
        + bytes(6)
        + cards
        + bytes(5)
    )


def native_player_record(player_id: int, name: str, *, label: str | None = None) -> bytes:
    """A player's identity record, ended by ``f0 bf`` and an optional showdown label."""
    encoded = name.encode()
    record = (
        player_id.to_bytes(4, "little")
        + len(encoded).to_bytes(2, "little")
        + encoded
        + b"\0\0\0\x01"
        + bytes(6)
        + b"\x01"
        + bytes(6)
        + b"\xf0\xbf"
    )
    if label is not None:
        record += len(label).to_bytes(2, "little") + label.encode()
    return record


def native_state_payload(
    table_id: int,
    hand_id: int,
    seats: list[tuple[bytes, bytes] | None],
    *,
    round_number: int = 1,
    game_code: bytes = b"SF",
    events: bytes = b"",
    trailer: bytes = b"\0\0\0\0\0\0\xff\xff\x01\0",
) -> bytes:
    """A class-22 game state: ``seats`` holds ``(state_block, record)`` or None for an empty seat."""
    entries = b"".join(b"\0" if seat is None else seat[0] + seat[1] for seat in seats)
    return (
        b"\x16\0"
        + bytes(4)
        + bytes(4)
        + b"\x01"
        + game_code
        + bytes([len(seats)])
        + entries
        + trailer
        + hand_id.to_bytes(4, "little")
        + table_id.to_bytes(4, "little")
        + bytes(5)
        + bytes([round_number])
        + events
    )


def native_action_event(action_code: int, amount: int, seat_idx: int, *, label: str = "") -> bytes:
    """One type-9 action: ``09 <action> <amount> <seat> <label> 00*6``."""
    return (
        b"\x09"
        + bytes([action_code])
        + encode_native_amount(amount)
        + bytes([seat_idx])
        + len(label).to_bytes(2, "little")
        + label.encode()
        + bytes(6)
    )


def native_event_list(*events: bytes) -> bytes:
    """A counted animation-event list as it follows the table header."""
    return len(events).to_bytes(2, "little") + b"".join(events)


def native_tournament_table(table_id: int, tournament_id: int, name: str, *, seats: int = 6) -> bytes:
    """A class-31 tournament table descriptor: fixed-limit (``FT``), ``seats`` seats."""
    encoded = name.encode()
    return (
        b"\x1f\0"
        + (0x01180D01).to_bytes(4, "little")
        + tournament_id.to_bytes(4, "little")
        + bytes(4)
        + table_id.to_bytes(4, "little")
        + b"\x01"
        + tournament_id.to_bytes(4, "little")
        + b"S"
        + len(encoded).to_bytes(2, "little")
        + encoded
        + bytes([10, 20, 0])
        + b"FT"
        + bytes([3, seats, 0, 0, 4])
        + bytes(16)
    )


def native_dealer_message(table_id: int, text: str) -> bytes:
    """A class-0 chat record from the Dealer at ``table_id``."""
    return (
        b"\0\0"
        + bytes(4)
        + table_id.to_bytes(4, "little")
        + b"\0"
        + b"2026-11-20 10:00:00\0Dealer\0"
        + text.encode()
        + b"\0"
    )
