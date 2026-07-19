#!/usr/bin/env python3
"""Build, launch, and inspect the passive TLS tap for the native SwC client."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import re
import struct
import subprocess
import sys
import threading
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from fpdb_3_legacy.http_capture_diff import diff_snapshot_steps
from fpdb_3_legacy.http_capture_models import SWC_GAME_DEFINITIONS
from fpdb_3_legacy.swc_http_adapter import card_id_to_str

SWC_APP = Path("/Applications/SwC Poker.app")
SWC_EXECUTABLE = SWC_APP / "Contents/MacOS/SwC Poker"
SOURCE_PATH = Path(__file__).with_name("swc_native_tap.c")
BUILD_DIR = Path.home() / ".fpdb" / "swc-native-capture"
TAP_LIBRARY = BUILD_DIR / "libswc_native_tap.dylib"
DEFAULT_ARCHIVE = BUILD_DIR / "swc-native.raw"
DEFAULT_STATUS = BUILD_DIR / "swc-native.status"

_HEADER = struct.Struct("=IHBBHHIQ")
_MAGIC = 0x53574354
_VERSION = 1
_MAX_PAYLOAD = 16 * 1024 * 1024


@dataclass(frozen=True)
class NativeCaptureRecord:
    captured_at: datetime
    direction: str
    peer_port: int
    payload: bytes
    connection_id: int = 0


@dataclass(frozen=True)
class NativeProtocolMessage:
    captured_at: datetime
    payload: bytes
    peer_port: int = 0
    connection_id: int = 0


@dataclass(frozen=True)
class NativeDealerMessage:
    timestamp: str
    text: str
    table_id: int | None = None
    peer_port: int = 0


@dataclass(frozen=True)
class NativeHandSummary:
    table_id: int
    hand_id: int
    table_name: str | None
    snapshot_count: int
    family: str = "unknown"
    tournament_id: int | None = None
    rounds: tuple[int, ...] = ()
    players: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeTableInfo:
    table_id: int
    name: str
    tournament_id: int | None
    family: str


@dataclass(frozen=True)
class NativePlayerIdentity:
    player_id: int
    name: str
    stack_units: int | None = None
    is_active: bool = False
    native_status: int | None = None


@dataclass(frozen=True)
class NativeStackTransition:
    table_id: int
    hand_id: int
    round_number: int
    player_id: int
    player_name: str
    previous_stack: int
    current_stack: int

    @property
    def delta(self) -> int:
        return self.current_stack - self.previous_stack


@dataclass(frozen=True)
class NativeSeatEvidence:
    table_id: int
    hand_id: int
    seat_idx: int
    player_id: int
    player_name: str
    source: str = "unique_raw_funds_decrease"


@dataclass(frozen=True)
class NativeCollectionEvent:
    table_id: int
    hand_id: int
    player_index: int
    player_name: str
    amount_native: int
    amount_displayed: str
    money_type: str
    native_units_per_display_unit: int | None
    text: str


@dataclass(frozen=True)
class NativeAnimationEvent:
    table_id: int
    hand_id: int
    round_number: int
    event_index: int
    type_code: int
    action_code: int
    funds: int
    seat_idx: int
    raw_payload: bytes
    table_message: str | None = None
    card_mnemonic: str | None = None


@dataclass(frozen=True)
class NativeGameStateSnapshot:
    """Confirmed identifiers from a native CClientGameState message.

    ``raw_payload`` deliberately remains available while the variable player
    records and animation-event suffix are still being decoded.
    """

    captured_at: datetime
    table_id: int
    hand_id: int
    round_number: int
    players: tuple[NativePlayerIdentity, ...]
    raw_payload: bytes
    peer_port: int = 0


_ROUND_STREETS = {
    "holdem": {0: "BLINDSANTES", 1: "PREFLOP", 2: "FLOP", 3: "TURN", 4: "RIVER", 5: "SHOWDOWN", 6: "SETTLEMENT"},
    "omaha": {0: "BLINDSANTES", 1: "PREFLOP", 2: "FLOP", 3: "TURN", 4: "RIVER", 5: "SHOWDOWN", 6: "SETTLEMENT"},
    "drawmaha": {
        0: "BLINDSANTES",
        1: "DEAL",
        2: "DRAWONE",
        3: "DRAWTWO",
        4: "DRAWTHREE",
        6: "SHOWDOWN",
        7: "SETTLEMENT",
    },
    "ofc": {0: "DEAL", 1: "ROUND1", 2: "ROUND2", 3: "ROUND3", 4: "ROUND4", 5: "SHOWDOWN", 6: "SETTLEMENT"},
}

_STREET_PROFILES = {
    "holdem": ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
    "omaha": ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
    "draw": ["BLINDSANTES", "DEAL", "DRAWONE"],
    "drawmaha": ["BLINDSANTES", "DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"],
    "ofc": ["DEAL", "ROUND1", "ROUND2", "ROUND3", "ROUND4"],
}

# Once the exact game is known (mixed-game tables), streets are resolved per FPDB
# category rather than per family. Round->street maps below are anchored on the
# observed native round span and, for draw games, on the dealer-announced draw
# rounds (2/4/6); settlement is the last round and showdown the one before it.
_STUD_ROUND_STREETS = {
    0: "BLINDSANTES",
    1: "THIRD",
    2: "FOURTH",
    3: "FIFTH",
    4: "SIXTH",
    5: "SEVENTH",
    6: "SHOWDOWN",
    7: "SETTLEMENT",
}
_SINGLE_DRAW_ROUND_STREETS = {
    0: "BLINDSANTES",
    1: "DEAL",
    2: "DRAWONE",
    3: "DRAWONE",
    4: "DRAWONE",
    5: "SHOWDOWN",
    6: "SETTLEMENT",
}
_TRIPLE_DRAW_ROUND_STREETS = {
    0: "BLINDSANTES",
    1: "DEAL",
    2: "DRAWONE",
    3: "DRAWONE",
    4: "DRAWTWO",
    5: "DRAWTWO",
    6: "DRAWTHREE",
    7: "DRAWTHREE",
    8: "SHOWDOWN",
    9: "SETTLEMENT",
}
_STUD_STREETS = ["BLINDSANTES", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
_SINGLE_DRAW_STREETS = ["BLINDSANTES", "DEAL", "DRAWONE"]
_TRIPLE_DRAW_STREETS = ["BLINDSANTES", "DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"]

_CATEGORY_ROUND_STREETS = {
    "studhi": _STUD_ROUND_STREETS,
    "studhilo": _STUD_ROUND_STREETS,
    "razz": _STUD_ROUND_STREETS,
    "27_1draw": _SINGLE_DRAW_ROUND_STREETS,
    "27_3draw": _TRIPLE_DRAW_ROUND_STREETS,
    "badugi": _TRIPLE_DRAW_ROUND_STREETS,
    "badeucey": _TRIPLE_DRAW_ROUND_STREETS,
    "badacey": _TRIPLE_DRAW_ROUND_STREETS,
}
_CATEGORY_STREET_PROFILES = {
    "studhi": _STUD_STREETS,
    "studhilo": _STUD_STREETS,
    "razz": _STUD_STREETS,
    "27_1draw": _SINGLE_DRAW_STREETS,
    "27_3draw": _TRIPLE_DRAW_STREETS,
    "badugi": _TRIPLE_DRAW_STREETS,
    "badeucey": _TRIPLE_DRAW_STREETS,
    "badacey": _TRIPLE_DRAW_STREETS,
}


def _native_round_street_map(family: str, category: str) -> dict[int, str]:
    return _CATEGORY_ROUND_STREETS.get(category) or _ROUND_STREETS.get(family, {})


def _native_street_profile(family: str, category: str) -> list[str]:
    return _CATEGORY_STREET_PROFILES.get(category) or _STREET_PROFILES.get(family, [])


def _native_family_gametype(family: str) -> tuple[str, str, str]:
    return {
        "holdem": ("hold", "holdem", "nl"),
        "omaha": ("hold", "omahahi", "pl"),
        "draw": ("draw", "27_1draw", "nl"),
        "drawmaha": ("draw", "drawmaha", "unknown"),
        "ofc": ("ofc", "ofc", "unknown"),
    }.get(family, ("unknown", "unknown", "unknown"))


def native_action_street(
    family: str, round_number: int, event_types: tuple[int, ...], category: str = ""
) -> str:
    """Place an action on its street, resolving per category when known.

    The round-before-board-reveal shift only applies to community-card games
    (Hold'em/Omaha/Drawmaha), where a type-2 board animation rides on the
    pre-transition snapshot; stud and draw games never trigger it.
    """
    board_game = family in {"holdem", "omaha", "drawmaha"}
    action_round = (
        round_number - 1 if board_game and round_number in {2, 3, 4} and 2 in event_types else round_number
    )
    return _native_round_street_map(family, category).get(action_round, "UNKNOWN")


class NativeProtocolDecoder:
    """Reassemble SwC's uint32-le length-prefixed messages across SSL reads."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.message_timestamp: datetime | None = None

    def feed(self, record: NativeCaptureRecord) -> list[NativeProtocolMessage]:
        if record.direction != "received":
            return []
        if not self.buffer:
            self.message_timestamp = record.captured_at
        self.buffer.extend(record.payload)
        messages = []
        while len(self.buffer) >= 4:
            size = int.from_bytes(self.buffer[:4], "little")
            if size > _MAX_PAYLOAD:
                raise ValueError("SwC native protocol message is too large")
            if len(self.buffer) < 4 + size:
                break
            payload = bytes(self.buffer[4 : 4 + size])
            del self.buffer[: 4 + size]
            messages.append(
                NativeProtocolMessage(
                    captured_at=self.message_timestamp or record.captured_at,
                    payload=payload,
                    peer_port=record.peer_port,
                    connection_id=record.connection_id,
                )
            )
            self.message_timestamp = record.captured_at if self.buffer else None
        return messages

    def finish(self) -> None:
        if self.buffer:
            raise ValueError("truncated SwC native protocol message")


def iter_protocol_messages(records: Iterator[NativeCaptureRecord]) -> Iterator[NativeProtocolMessage]:
    decoders: dict[tuple[int, int], NativeProtocolDecoder] = {}
    for record in records:
        key = (record.peer_port, record.connection_id)
        decoder = decoders.setdefault(key, NativeProtocolDecoder())
        yield from decoder.feed(record)
    for decoder in decoders.values():
        decoder.finish()


_PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_TAG = re.compile(r"<[^>]+>")
_DEALER_WIN_TEXT = re.compile(r"^(?P<name>.+?) wins \((?P<amount>[\d,.]+)\)(?:\s|:|$)")
_DEALER_RETURN_TEXT = re.compile(r"^Uncalled bet \((?P<amount>[\d,.]+)\) returned to (?P<name>.+)$")
_DEALER_DRAW_TEXT = re.compile(
    r"^(?P<ordinal>First|Second|Final) draw: (?P<name>.+?) (?:draws (?P<count>\d+)|stands pat)$"
)
_OFC_HAND_RESULT = re.compile(r"^Hand #(?P<number>\d+) finished - (?P<scores>.+)$")
_OFC_TOTAL_RESULT = re.compile(r"^TOTAL - (?P<scores>.+)$")
_OFC_PAYOUT = re.compile(r"^(?P<name>.+?) wins (?P<amount>\d+\.\d{2})$")
_OFC_FANTASY_LAND = re.compile(r"^(?P<name>.+?) is in fantasy land\. The button will not be moved$")
_OFC_GAME_COMPLETE = re.compile(r"^Game complete, (?P<hands>\d+) hands played$")
_OFC_GAME_START = re.compile(r"^New game started \((?P<hands>\d+) hands\)$")
_NATIVE_WIN_TEXT = re.compile(
    r'<nick s="(?P<seat>\d+)">(?P<name>[^<]+)</nick> wins.*?'
    r'<money a="(?P<amount>\d+)" mt="(?P<money_type>[^"]+)">(?P<displayed>[0-9.]+)</money>',
    re.DOTALL,
)
_FIXED_ANIMATION_EVENT_LENGTHS = {
    # Observed native CAnimationEvent encodings. The first four bytes are
    # type/action/funds/seat. Remaining bytes hold optional card mnemonics.
    1: 4,
    2: 4,
    3: 4,
    4: 4,
    6: 4,
    7: 14,
    9: 12,
    12: 14,
    25: 4,
}
_NATIVE_ACTION_LABELS = {
    1: "fold",
    2: "check",
    3: "call",
    4: "ante",
    6: "small_blind",
    7: "big_blind",
    8: "bet",
    9: "raise",
}
_NATIVE_CARD_MNEMONIC = re.compile(r"^D\.(?P<cards>\d+(?:;\d+)*)\.O\.[A-Z]+$")


def parse_native_card_mnemonic(value: str) -> tuple[str, ...]:
    """Decode an observed SwC evaluated-card mnemonic."""
    match = _NATIVE_CARD_MNEMONIC.fullmatch(value)
    if match is None:
        return ()
    card_ids = [int(card_id) for card_id in match.group("cards").split(";")]
    if any(card_id < 0 or card_id > 51 for card_id in card_ids):
        return ()
    return tuple(card_id_to_str(card_id) for card_id in card_ids)


# OFC settlement snapshots reveal each shown board as evaluated rows shaped
# ``<X>.<card;ids>.<Y>.<Z>``, e.g. ``H.42;19;16;14;13.M.H``. The prefix/suffix
# letters vary across hands and are not interpreted; only the card ids and the
# row size (3 = top row, 5 = middle/bottom) are decoded. Grouping rows into
# per-player top/middle/bottom boards is deliberately not attempted: the token
# order does not reliably match player identity (a captured example produces
# fouled boards and mismatched dealer descriptions when grouped sequentially).
_NATIVE_OFC_SHOWDOWN_ROW = re.compile(rb"[A-Z]\.((?:\d{1,2};){2,4}\d{1,2})\.[A-Z]\.[A-Z]")
_OFC_ROW_SIZES = (3, 5)


def parse_native_ofc_showdown_row(card_ids: str) -> tuple[str, ...]:
    """Decode one OFC settlement row's ``;``-separated card ids into cards.

    Returns ``()`` unless the row has a valid OFC size (3 or 5), every id is a
    distinct card in ``0..51``.
    """
    ids = [int(card_id) for card_id in card_ids.split(";")]
    if len(ids) not in _OFC_ROW_SIZES:
        return ()
    if any(card_id < 0 or card_id > 51 for card_id in ids):
        return ()
    if len(set(ids)) != len(ids):
        return ()
    return tuple(card_id_to_str(card_id) for card_id in ids)


def extract_native_ofc_showdown_rows(snapshots: list[NativeGameStateSnapshot]) -> list[dict]:
    """Return the evaluated OFC rows revealed at settlement, as capture evidence.

    Reads the snapshot that exposes the most rows (the completed settlement view)
    and decodes each row's cards in payload order. A three-card row is labelled
    ``top`` (an OFC top row is always three cards); five-card rows are left
    ``row: null`` because middle and bottom cannot be told apart without proven
    player attribution. Returns ``[]`` when nothing decodes cleanly or the same
    card appears twice (a sign of a false-positive match).
    """
    best: list[tuple[str, ...]] = []
    for snapshot in snapshots:
        rows: list[tuple[str, ...]] = []
        for match in _NATIVE_OFC_SHOWDOWN_ROW.finditer(snapshot.raw_payload):
            cards = parse_native_ofc_showdown_row(match.group(1).decode())
            if cards:
                rows.append(cards)
        if len(rows) > len(best):
            best = rows

    all_cards = [card for row in best for card in row]
    if len(set(all_cards)) != len(all_cards):
        return []
    return [
        {"cards": list(row), "card_count": len(row), "row": "top" if len(row) == 3 else None}
        for row in best
    ]


def derive_native_used_hole_cards(evaluated_cards: tuple[str, ...], board: tuple[str, ...]) -> tuple[str, ...]:
    """Subtract community cards from a five-card evaluated combination."""
    remaining_board = Counter(board)
    used_hole_cards = []
    for card in evaluated_cards:
        if remaining_board[card]:
            remaining_board[card] -= 1
        else:
            used_hole_cards.append(card)
    return tuple(used_hole_cards)


def _build_native_showdown(
    collections: list[dict], evaluated_hands: set[tuple[str, ...]], final_board: tuple[str, ...]
) -> dict | None:
    if len(collections) != 1 or len(evaluated_hands) != 1 or not final_board:
        return None
    evaluated_cards = next(iter(evaluated_hands))
    used_hole_cards = derive_native_used_hole_cards(evaluated_cards, final_board)
    if not 1 <= len(used_hole_cards) <= 2:
        return None
    return {
        "player": collections[0]["player"],
        "evaluated_cards": list(evaluated_cards),
        "used_hole_cards": list(used_hole_cards),
        "source": "unique_native_type_10_minus_board",
        "complete_private_hand": False,
    }


def _build_native_action_evidence(steps: list[dict]) -> list[dict]:
    actions = []
    for step in steps:
        for event in step["native_events"]:
            if "action_name_evidence" not in event or "player_name_evidence" not in event:
                continue
            actions.append(
                {
                    "sequence": len(actions) + 1,
                    "step_num": step["step_num"],
                    "street": event["action_street_evidence"],
                    "player": event["player_name_evidence"],
                    "action": event["action_name_evidence"],
                    "seat_idx": None,
                    "native_index": event["native_index"],
                    "funds_byte": event["funds_byte"],
                    "source": event["player_evidence_source"],
                    "raw_hex": event["raw_hex"],
                }
            )
    return actions


def audit_native_hand(
    steps: list[dict],
    collections: list[dict],
    *,
    dealer_hand_started: bool = False,
    dealer_hand_complete: bool = False,
) -> dict:
    """Report whether captured native evidence is sufficient for FPDB import."""
    type_9_events = [event for step in steps for event in step["native_events"] if event.get("type_code") == 9]
    poker_events = [event for step in steps for event in step["native_events"] if "action_name_evidence" in event]
    unresolved = [event for event in poker_events if "player_name_evidence" not in event]
    unresolved_by_action = dict(sorted(Counter(event["action_name_evidence"] for event in unresolved).items()))
    observed_actions = {event["action_name_evidence"] for event in poker_events}
    reasons = []
    if unresolved:
        reasons.append(f"{len(unresolved)} native action event(s) have no proven player")
    if not {"small_blind", "big_blind"}.issubset(observed_actions):
        reasons.append("hand start is not fully observed (small and big blinds required)")
    if not collections:
        reasons.append("settlement/collection is not observed")
    reasons.append("complete private cards and full-width action-amount encoding are not decoded")
    return {
        "importable": False,
        "status": "capture_only",
        "native_type_9_event_count": len(type_9_events),
        "resolved_native_type_9_player_count": sum("player_name_evidence" in event for event in type_9_events),
        "poker_event_count": len(poker_events),
        "resolved_poker_event_count": len(poker_events) - len(unresolved),
        "unresolved_poker_event_count": len(unresolved),
        "unresolved_by_action": unresolved_by_action,
        "complete_action_players": not unresolved,
        "has_small_blind": "small_blind" in observed_actions,
        "has_big_blind": "big_blind" in observed_actions,
        "has_collection": bool(collections),
        "dealer_hand_started": dealer_hand_started,
        "dealer_hand_complete": dealer_hand_complete,
        "reasons": reasons,
    }


def extract_dealer_message(message: NativeProtocolMessage) -> NativeDealerMessage | None:
    """Extract native chat records (message class 0) without guessing snapshots."""
    if len(message.payload) < 2 or int.from_bytes(message.payload[:2], "little") != 0:
        return None
    strings = [value.decode("utf-8", "replace") for value in _PRINTABLE.findall(message.payload)]
    timestamp = next((value for value in strings if _TIMESTAMP.fullmatch(value)), None)
    dealer_index = next((index for index, value in enumerate(strings) if value.startswith("Dealer")), None)
    if timestamp is None or dealer_index is None or dealer_index + 1 >= len(strings):
        return None
    rich_text = strings[dealer_index + 1]
    plain_text = html.unescape(_TAG.sub("", rich_text)).strip()
    table_id = int.from_bytes(message.payload[6:10], "little") if len(message.payload) >= 10 else None
    return NativeDealerMessage(
        timestamp=timestamp,
        text=plain_text,
        table_id=table_id,
        peer_port=message.peer_port,
    )


def parse_native_dealer_win(text: str, *, tournament: bool) -> dict | None:
    """Parse an exact Dealer-chat collection amount without assigning a seat."""
    match = _DEALER_WIN_TEXT.match(text)
    if match is None:
        return None
    amount_displayed = match.group("amount")
    displayed_decimal = Decimal(amount_displayed.replace(",", ""))
    money_type = "T" if tournament else "R"
    scale = 1 if tournament else 100
    native_decimal = displayed_decimal * scale
    if native_decimal != int(native_decimal):
        return None
    return {
        "player": match.group("name"),
        "seat_idx": None,
        "amount_native": int(native_decimal),
        "amount_displayed": amount_displayed,
        "money_type": money_type,
        "native_units_per_display_unit": scale,
        "source": "swc_native_dealer_chat",
        "text": text,
    }


def parse_native_dealer_draw(text: str) -> dict | None:
    """Parse a draw-game Dealer line into an exact per-player draw count.

    Handles ``First/Second/Final draw: <player> draws N`` and ``... stands pat``.
    The draw round is kept as the dealer's own ordinal (``first``/``second``/
    ``final``); ``stands_pat`` means zero cards drawn. No seat is claimed.
    """
    match = _DEALER_DRAW_TEXT.match(text)
    if match is None:
        return None
    count = match.group("count")
    return {
        "draw": match.group("ordinal").lower(),
        "player": match.group("name"),
        "seat_idx": None,
        "cards_drawn": int(count) if count is not None else 0,
        "stands_pat": count is None,
        "source": "swc_native_dealer_chat",
        "text": text,
    }


# A mixed-game table announces each rotation with a class-26 message shaped
# "Game changes to <NL|PL|FL> <game label> <small>/<big>". The game label matches
# a SWC_GAME_DEFINITIONS label exactly, so the shared HTTP-adapter table resolves
# the FPDB base/category without decoding the opaque native game-type code.
_GAME_CHANGE_TEXT = re.compile(
    r"^Game changes to (?P<limit>NL|PL|FL) (?P<game>.+?) (?P<sb>\d+)/(?P<bb>\d+)$"
)
_NATIVE_LIMIT_TYPES = {"NL": "nl", "PL": "pl", "FL": "fl"}
_SWC_LABEL_TO_DEFINITION = {}
for _swc_code, _swc_definition in SWC_GAME_DEFINITIONS.items():
    _SWC_LABEL_TO_DEFINITION.setdefault(_swc_definition.label, _swc_definition)


def _native_family_from_definition(base: str, category: str) -> str:
    """Map an FPDB base/category to the native decoder's family label."""
    if base == "hold":
        return "omaha" if "omaha" in category else "holdem"
    if base in {"stud", "draw", "ofc"}:
        return base
    return "unknown"


def _resolve_native_hand_game(
    native_game: dict | None, table: NativeTableInfo, table_id: int, ofc_table_ids: set[int]
) -> tuple[str, str, str, str]:
    """Return ``(family, base, category, limit_type)`` for a hand.

    A per-hand game-change announcement (mixed-game tables) is authoritative over
    the static table-name heuristic and the OFC deal-pattern detector.
    """
    if native_game is not None:
        return native_game["family"], native_game["base"], native_game["category"], native_game["limit_type"]
    family = "ofc" if table_id in ofc_table_ids else table.family
    base, category, limit_type = _native_family_gametype(family)
    return family, base, category, limit_type


def parse_native_game_change(payload: bytes) -> dict | None:
    """Parse a class-26 'Game changes to ...' mixed-game rotation announcement.

    Resolves the announced game label through the shared SWC_GAME_DEFINITIONS
    table. Returns ``None`` for any other message or an unrecognised label.
    """
    if len(payload) < 14 or int.from_bytes(payload[:2], "little") != 26:
        return None
    text = payload[14:].split(b"\x00", 1)[0].decode("utf-8", "replace")
    match = _GAME_CHANGE_TEXT.match(text)
    if match is None:
        return None
    definition = _SWC_LABEL_TO_DEFINITION.get(match.group("game"))
    if definition is None:
        return None
    return {
        "table_id": int.from_bytes(payload[6:10], "little"),
        "game_label": match.group("game"),
        "base": definition.base,
        "category": definition.category,
        "family": _native_family_from_definition(definition.base, definition.category),
        "limit_type": _NATIVE_LIMIT_TYPES.get(match.group("limit"), "unknown"),
        "small_bet": match.group("sb"),
        "big_bet": match.group("bb"),
        "fpdb_supported": definition.fpdb_supported,
        "text": text,
    }


def _collect_native_game_changes(
    messages: list[NativeProtocolMessage], table_infos: dict[int, NativeTableInfo]
) -> dict[tuple[int, int], dict]:
    """Map (table_id, hand_id) to the game the latest class-26 change announced.

    Walks the stream in order, remembering the current game per table, and binds
    it to each hand at that hand's first snapshot. Hands captured before any game
    change (or on tables that never announce one) are left unmapped.
    """
    result: dict[tuple[int, int], dict] = {}
    current: dict[int, dict] = {}
    table_ids = set(table_infos)
    for message in messages:
        change = parse_native_game_change(message.payload)
        if change is not None:
            current[change["table_id"]] = change
            continue
        snapshot = extract_game_state(message, table_ids)
        if snapshot is None:
            continue
        key = (snapshot.table_id, snapshot.hand_id)
        if key not in result and snapshot.table_id in current:
            result[key] = current[snapshot.table_id]
    return result


def parse_native_dealer_return(text: str, *, tournament: bool) -> dict | None:
    """Parse an exact Dealer-chat uncalled-bet return."""
    match = _DEALER_RETURN_TEXT.match(text)
    if match is None:
        return None
    amount_displayed = match.group("amount")
    displayed_decimal = Decimal(amount_displayed.replace(",", ""))
    money_type = "T" if tournament else "R"
    scale = 1 if tournament else 100
    native_decimal = displayed_decimal * scale
    if native_decimal != int(native_decimal):
        return None
    return {
        "player": match.group("name"),
        "amount_native": int(native_decimal),
        "amount_displayed": amount_displayed,
        "money_type": money_type,
        "native_units_per_display_unit": scale,
        "source": "swc_native_dealer_chat",
        "text": text,
    }


def parse_native_ofc_scores(text: str) -> dict | None:
    """Parse exact per-hand or cumulative OFC point scores from Dealer chat."""
    hand_match = _OFC_HAND_RESULT.match(text)
    total_match = _OFC_TOTAL_RESULT.match(text)
    match = hand_match or total_match
    if match is None:
        return None
    scores = {}
    for item in match.group("scores").split(", "):
        name, separator, raw_score = item.rpartition(": ")
        if not separator or not re.fullmatch(r"[+-]?\d+", raw_score):
            return None
        scores[name] = int(raw_score)
    return {
        "kind": "hand" if hand_match else "total",
        **({"hand_number": int(hand_match.group("number"))} if hand_match else {}),
        "scores": scores,
        "source": "swc_native_dealer_chat",
        "text": text,
    }


def parse_native_ofc_payout(text: str) -> dict | None:
    """Parse an exact two-decimal OFC cash payout."""
    match = _OFC_PAYOUT.match(text)
    if match is None:
        return None
    amount_displayed = match.group("amount")
    return {
        "player": match.group("name"),
        "amount_displayed": amount_displayed,
        "amount_native": int(Decimal(amount_displayed) * 100),
        "money_type": "R",
        "native_units_per_display_unit": 100,
        "source": "swc_native_dealer_chat",
        "text": text,
    }


def parse_native_ofc_fantasy_land(text: str) -> dict | None:
    """Parse an explicit OFC fantasy-land transition."""
    match = _OFC_FANTASY_LAND.match(text)
    if match is None:
        return None
    return {
        "player": match.group("name"),
        "button_moved": False,
        "source": "swc_native_dealer_chat",
        "text": text,
    }


def parse_native_ofc_game_complete(text: str) -> dict | None:
    """Parse the explicit OFC session-completion marker."""
    match = _OFC_GAME_COMPLETE.match(text)
    if match is None:
        return None
    return {
        "complete": True,
        "hands_played": int(match.group("hands")),
        "source": "swc_native_dealer_chat",
        "text": text,
    }


def parse_native_ofc_game_start(text: str) -> dict | None:
    """Parse the initial planned OFC session length."""
    match = _OFC_GAME_START.match(text)
    if match is None:
        return None
    return {
        "planned_hands": int(match.group("hands")),
        "source": "swc_native_dealer_chat",
        "text": text,
    }


def _collect_native_dealer_wins(
    messages: list[NativeProtocolMessage], table_infos: dict[int, NativeTableInfo]
) -> dict[tuple[int, int], list[dict]]:
    collections: dict[tuple[int, int], list[dict]] = {}
    current_hand_by_table: dict[int, int] = {}
    table_ids = set(table_infos)
    for message in messages:
        if snapshot := extract_game_state(message, table_ids):
            current_hand_by_table[snapshot.table_id] = snapshot.hand_id
        dealer = extract_dealer_message(message)
        if dealer is None or dealer.table_id not in current_hand_by_table or dealer.table_id not in table_infos:
            continue
        table = table_infos[dealer.table_id]
        collection = parse_native_dealer_win(dealer.text, tournament=table.tournament_id is not None)
        if collection:
            key = (dealer.table_id, current_hand_by_table[dealer.table_id])
            collections.setdefault(key, []).append(collection)
    return collections


def _collect_native_dealer_returns(
    messages: list[NativeProtocolMessage], table_infos: dict[int, NativeTableInfo]
) -> dict[tuple[int, int], list[dict]]:
    returns: dict[tuple[int, int], list[dict]] = {}
    current_hand_by_table: dict[int, int] = {}
    table_ids = set(table_infos)
    for message in messages:
        if snapshot := extract_game_state(message, table_ids):
            current_hand_by_table[snapshot.table_id] = snapshot.hand_id
        dealer = extract_dealer_message(message)
        if dealer is None or dealer.table_id not in current_hand_by_table or dealer.table_id not in table_infos:
            continue
        table = table_infos[dealer.table_id]
        returned = parse_native_dealer_return(dealer.text, tournament=table.tournament_id is not None)
        if returned:
            key = (dealer.table_id, current_hand_by_table[dealer.table_id])
            returns.setdefault(key, []).append(returned)
    return returns


def _collect_native_dealer_events(
    messages: list[NativeProtocolMessage], table_infos: dict[int, NativeTableInfo]
) -> dict[tuple[int, int], list[dict]]:
    events: dict[tuple[int, int], list[dict]] = {}
    current_hand_by_table: dict[int, int] = {}
    table_ids = set(table_infos)
    for message in messages:
        if snapshot := extract_game_state(message, table_ids):
            current_hand_by_table[snapshot.table_id] = snapshot.hand_id
        dealer = extract_dealer_message(message)
        if (
            dealer is None
            or dealer.table_id not in current_hand_by_table
            or dealer.text.startswith("New game started")
            or (dealer.text.startswith("New hand started") and dealer.text != "New hand started")
        ):
            continue
        key = (dealer.table_id, current_hand_by_table[dealer.table_id])
        events.setdefault(key, []).append({"timestamp": dealer.timestamp, "text": dealer.text})
    return events


def _collect_native_ofc_game_starts(
    messages: list[NativeProtocolMessage], table_infos: dict[int, NativeTableInfo]
) -> dict[tuple[int, int], dict]:
    starts = {}
    pending_by_table: dict[int, dict] = {}
    table_ids = set(table_infos)
    for message in messages:
        dealer = extract_dealer_message(message)
        if dealer and dealer.table_id and (start := parse_native_ofc_game_start(dealer.text)):
            pending_by_table[dealer.table_id] = start
        snapshot = extract_game_state(message, table_ids)
        if snapshot and snapshot.table_id in pending_by_table:
            starts[(snapshot.table_id, snapshot.hand_id)] = pending_by_table.pop(snapshot.table_id)
    return starts


def _merge_native_collections(type_15_events: list[NativeCollectionEvent], dealer_events: list[dict]) -> list[dict]:
    """Prefer type-15 settlements and supplement them with deduplicated Dealer chat."""
    collections = []
    keys = set()
    for event in type_15_events:
        key = (event.player_name, event.amount_native)
        if key in keys:
            continue
        keys.add(key)
        collections.append(
            {
                "player": event.player_name,
                "seat_idx": None,
                "player_index": event.player_index,
                "amount_native": event.amount_native,
                "amount_displayed": event.amount_displayed,
                "money_type": event.money_type,
                "native_units_per_display_unit": event.native_units_per_display_unit,
                "source": "swc_native_type_15",
                "text": event.text,
            }
        )
    for collection in dealer_events:
        key = (collection["player"], collection["amount_native"])
        if key not in keys:
            keys.add(key)
            collections.append(collection)
    return collections


def extract_table_info(message: NativeProtocolMessage) -> NativeTableInfo | None:
    payload = message.payload
    if len(payload) < 18 or int.from_bytes(payload[:2], "little") != 34:
        return None
    name_size = int.from_bytes(payload[16:18], "little")
    if name_size == 0 or 18 + name_size > len(payload):
        return None
    name = payload[18 : 18 + name_size].decode("utf-8", "replace")
    tournament_value = int.from_bytes(payload[11:15], "little")
    searchable = f"{name} " + " ".join(value.decode("utf-8", "replace") for value in _PRINTABLE.findall(payload))
    trailer = payload[18 + name_size : 18 + name_size + 16]
    family = _native_table_family(name, searchable, trailer)
    return NativeTableInfo(
        table_id=int.from_bytes(payload[6:10], "little"),
        name=name,
        tournament_id=tournament_value or None,
        family=family,
    )


def _native_table_family(name: str, searchable: str, trailer: bytes) -> str:
    """Classify a native table name before applying generic trailer signatures."""
    lowered = searchable.lower()
    if "drawmaha" in lowered:
        return "drawmaha"
    if "ofc" in lowered or "chinese" in lowered:
        return "ofc"
    if "plo" in lowered or "omaha" in lowered:
        return "omaha"
    if "single draw" in lowered or "2-7" in lowered or "deuce to seven" in lowered:
        return "draw"
    if "hold'em" in lowered or "holdem" in lowered:
        return "holdem"
    if b"UR" in trailer and "plo" not in name.lower():
        # Observed native cash-table signature for NL Hold'em. PLO tables use
        # PR here; keep unobserved signatures unknown rather than generalizing.
        return "holdem"
    if "stud" in lowered:
        return "stud"
    if "draw" in lowered:
        return "draw"
    return "unknown"


def _extract_player_identities(payload: bytes, end: int) -> tuple[NativePlayerIdentity, ...]:
    """Read length-prefixed player names from the player section.

    This intentionally does not decode the bytes following each name yet.
    Those records contain optional card/action blocks whose lengths change
    during a hand.
    """
    candidates: list[tuple[int, int, int, str]] = []
    seen_ids = set()
    for name_offset in range(6, end):
        name_size = int.from_bytes(payload[name_offset - 2 : name_offset], "little")
        # SwC screen names are at least two characters. Requiring that lower
        # bound also prevents a one-byte card/action value from looking like a
        # length-prefixed name inside the variable record suffix.
        if not 2 <= name_size <= 32 or name_offset + name_size > end:
            continue
        encoded_name = payload[name_offset : name_offset + name_size]
        try:
            name = encoded_name.decode("utf-8")
        except UnicodeDecodeError:
            continue
        name_end = name_offset + name_size
        if (
            not name.isprintable()
            or any(character.isspace() for character in name)
            or name == "RESERVED"
            or payload[name_end : name_end + 2] != b"\0\0"
        ):
            continue
        player_id = int.from_bytes(payload[name_offset - 6 : name_offset - 2], "little")
        if player_id == 0 or player_id in seen_ids:
            continue
        candidates.append((name_offset - 6, name_end, player_id, name))
        seen_ids.add(player_id)
    players = []
    for index, (record_start, name_end, player_id, name) in enumerate(candidates):
        record_end = candidates[index + 1][0] if index + 1 < len(candidates) else end
        marker = payload.find(b"\xf0\xbf", name_end, record_end)
        stack_units = None
        is_active = False
        native_status = None
        if marker >= 0:
            # One optional byte precedes the two-byte player flags. Locate the
            # flags by their high bit, then read the three-byte funds value at
            # a stable +8 offset. This handles both observed record shapes.
            flag_offset = next(
                (offset for offset in range(marker + 2, min(marker + 6, record_end - 1)) if payload[offset + 1] & 0x80),
                None,
            )
            stack_offset = flag_offset + 8 if flag_offset is not None else record_end
            if flag_offset is not None and flag_offset + 3 < record_end:
                native_status = payload[flag_offset + 3]
                is_active = bool(native_status & 0x40)
            if stack_offset + 3 <= record_end:
                stack_units = int.from_bytes(payload[stack_offset : stack_offset + 3], "little")
        players.append(NativePlayerIdentity(player_id, name, stack_units, is_active, native_status))
    return tuple(players)


def extract_game_state(message: NativeProtocolMessage, table_ids: set[int]) -> NativeGameStateSnapshot | None:
    """Extract only fields confirmed across captured SwC state messages."""
    payload = message.payload
    if len(payload) < 16 or int.from_bytes(payload[:2], "little") != 22:
        return None
    for table_id in table_ids:
        table_offset = payload.find(table_id.to_bytes(4, "little"), 4)
        if table_offset < 4 or len(payload) <= table_offset + 9:
            continue
        return NativeGameStateSnapshot(
            captured_at=message.captured_at,
            table_id=table_id,
            hand_id=int.from_bytes(payload[table_offset - 4 : table_offset], "little"),
            round_number=payload[table_offset + 9],
            players=_extract_player_identities(payload, table_offset - 4),
            raw_payload=payload,
            peer_port=message.peer_port,
        )
    return None


def extract_native_board(snapshot: NativeGameStateSnapshot, family: str) -> tuple[str, ...]:
    """Extract the confirmed Hold'em/Omaha board stored before the table footer."""
    if family not in {"holdem", "omaha"} or snapshot.round_number < 2:
        return ()
    expected_count = min(snapshot.round_number + 1, 5)
    table_offset = snapshot.raw_payload.find(snapshot.table_id.to_bytes(4, "little"), 4)
    if table_offset < 0:
        return ()
    marker = snapshot.raw_payload.rfind(b"\xf0\xbf", 0, table_offset)
    if marker < 0:
        return ()
    for count_offset in range(marker + 2, min(marker + 8, table_offset)):
        if snapshot.raw_payload[count_offset] != expected_count:
            continue
        card_ids = snapshot.raw_payload[count_offset + 1 : count_offset + 1 + expected_count]
        footer_size = table_offset - (count_offset + 1 + expected_count)
        if len(card_ids) == expected_count and all(card_id <= 51 for card_id in card_ids) and 14 <= footer_size <= 18:
            return tuple(card_id_to_str(card_id) for card_id in card_ids)
    return ()


def _parse_type_10_event(payload: bytes, cursor: int) -> tuple[int, str | None]:
    """Return the end and optional mnemonic for an observed type-10 event."""
    if cursor + 8 > len(payload) or payload[cursor + 4 : cursor + 6] != b"\0" * 2:
        return cursor + 14, None
    mnemonic_size = int.from_bytes(payload[cursor + 6 : cursor + 8], "little")
    candidate_end = cursor + 18 + mnemonic_size
    if (
        mnemonic_size == 0
        or candidate_end > len(payload)
        or payload[cursor + 8 + mnemonic_size : candidate_end] != b"\0" * 10
    ):
        return cursor + 14, None
    mnemonic = payload[cursor + 8 : cursor + 8 + mnemonic_size].decode("ascii", "replace")
    return candidate_end, mnemonic


def _parse_type_15_event(payload: bytes, cursor: int) -> tuple[int, str] | None:
    if cursor + 6 > len(payload):
        return None
    message_size = int.from_bytes(payload[cursor + 4 : cursor + 6], "little")
    event_end = cursor + 6 + message_size
    if event_end > len(payload):
        return None
    return event_end, payload[cursor + 6 : event_end].decode("utf-8", "replace")


def _parse_animation_event_list(
    payload: bytes, offset: int
) -> tuple[tuple[int, int, int, int, bytes, str | None, str | None], ...] | None:
    if offset + 2 > len(payload):
        return None
    event_count = int.from_bytes(payload[offset : offset + 2], "little")
    if event_count > 64:
        return None

    cursor = offset + 2
    events = []
    for _ in range(event_count):
        if cursor + 4 > len(payload):
            return None
        type_code = payload[cursor]
        action_code = payload[cursor + 1]
        funds = payload[cursor + 2]
        seat_idx = payload[cursor + 3]
        event_start = cursor
        table_message = None
        card_mnemonic = None
        if type_code == 15:
            parsed = _parse_type_15_event(payload, cursor)
            if parsed is None:
                return None
            cursor, table_message = parsed
        elif type_code == 10:
            # Observed showdown-card event: two empty 16-bit strings, one
            # length-prefixed card mnemonic, then four empty 16-bit strings.
            # Empty type-10 animations also occur in the legacy 12-byte form.
            cursor, card_mnemonic = _parse_type_10_event(payload, cursor)
        elif type_code in _FIXED_ANIMATION_EVENT_LENGTHS:
            cursor += _FIXED_ANIMATION_EVENT_LENGTHS[type_code]
        else:
            return None
        events.append(
            (type_code, action_code, funds, seat_idx, payload[event_start:cursor], table_message, card_mnemonic)
        )

    trailing = payload[cursor:]
    if trailing and (len(trailing) > 8 or len(trailing) % 2 or any(trailing)):
        return None
    return tuple(events)


def extract_native_animation_events(
    message: NativeProtocolMessage, table_ids: set[int]
) -> tuple[NativeAnimationEvent, ...]:
    """Extract observed native CAnimationEvent records from a game-state message.

    These are intentionally exposed as native evidence. Type 9 appears to carry
    action-like data, but player/amount semantics are not promoted to FPDB
    actions until they are fully correlated.
    """
    snapshot = extract_game_state(message, table_ids)
    if snapshot is None:
        return ()
    table_offset = snapshot.raw_payload.find(snapshot.table_id.to_bytes(4, "little"), 4)
    if table_offset < 0:
        return ()

    for offset in range(table_offset + 10, len(snapshot.raw_payload)):
        raw_events = _parse_animation_event_list(snapshot.raw_payload, offset)
        if not raw_events:
            continue
        return tuple(
            NativeAnimationEvent(
                table_id=snapshot.table_id,
                hand_id=snapshot.hand_id,
                round_number=snapshot.round_number,
                event_index=index,
                type_code=type_code,
                action_code=action_code,
                funds=funds,
                seat_idx=seat_idx,
                raw_payload=raw_payload,
                table_message=table_message,
                card_mnemonic=card_mnemonic,
            )
            for index, (
                type_code,
                action_code,
                funds,
                seat_idx,
                raw_payload,
                table_message,
                card_mnemonic,
            ) in enumerate(raw_events)
        )
    # A still-unknown animation can make the enclosing list undecodable.
    # Preserve one standalone type-9 action only when its observed shape is
    # exact and unique after the table header.
    isolated = []
    for offset in range(table_offset + 10, len(snapshot.raw_payload) - 11):
        raw = snapshot.raw_payload[offset : offset + 12]
        if raw[0] == 9 and 1 <= raw[1] <= 26 and raw[3] <= 10 and raw[4:] == b"\0" * 8:
            isolated.append(raw)
    if len(isolated) != 1:
        return ()
    raw = isolated[0]
    return (
        NativeAnimationEvent(
            table_id=snapshot.table_id,
            hand_id=snapshot.hand_id,
            round_number=snapshot.round_number,
            event_index=0,
            type_code=9,
            action_code=raw[1],
            funds=raw[2],
            seat_idx=raw[3],
            raw_payload=raw,
        ),
    )


def _extract_evaluated_cards(message: NativeProtocolMessage, table_ids: set[int]) -> set[tuple[str, ...]]:
    evaluated = set()
    for event in extract_native_animation_events(message, table_ids):
        if event.card_mnemonic and (cards := parse_native_card_mnemonic(event.card_mnemonic)):
            evaluated.add(cards)
    return evaluated


def _observed_ofc_table_ids(messages: list[NativeProtocolMessage]) -> set[int]:
    table_ids = set()
    for message in messages:
        dealer = extract_dealer_message(message)
        if (
            dealer
            and dealer.table_id
            and any(marker in dealer.text.lower() for marker in ("fantasy land", "hand #", "total -"))
        ):
            table_ids.add(dealer.table_id)
    return table_ids


def classify_native_ofc_deal_pattern(*, has_initial_five: bool, has_later_three: bool) -> str:
    """Name only the observed five-then-three Pineapple deal pattern."""
    return "pineapple" if has_initial_five and has_later_three else "unresolved"


def _observed_ofc_variants(
    messages: list[NativeProtocolMessage], table_ids: set[int], ofc_table_ids: set[int]
) -> dict[int, str]:
    patterns = {table_id: {"initial": False, "later": False} for table_id in ofc_table_ids}
    for message in messages:
        snapshot = extract_game_state(message, table_ids)
        if snapshot is None or snapshot.table_id not in patterns:
            continue
        deal_counts = Counter(
            event.seat_idx for event in extract_native_animation_events(message, table_ids) if event.type_code == 1
        )
        patterns[snapshot.table_id]["initial"] |= snapshot.round_number == 0 and 5 in deal_counts.values()
        patterns[snapshot.table_id]["later"] |= snapshot.round_number in {1, 2, 3, 4} and 3 in deal_counts.values()
    return {
        table_id: classify_native_ofc_deal_pattern(
            has_initial_five=pattern["initial"], has_later_three=pattern["later"]
        )
        for table_id, pattern in patterns.items()
    }


def extract_native_collections(
    message: NativeProtocolMessage, table_ids: set[int]
) -> tuple[NativeCollectionEvent, ...]:
    """Extract explicit type-15 winner events and their unscaled amount."""
    events = []
    for animation in extract_native_animation_events(message, table_ids):
        if animation.type_code != 15 or animation.table_message is None:
            continue
        match = _NATIVE_WIN_TEXT.search(animation.table_message)
        if match is None or int(match.group("seat")) != animation.seat_idx:
            continue
        amount_native = int(match.group("amount"))
        amount_displayed = match.group("displayed")
        displayed_decimal = Decimal(amount_displayed)
        scale = Decimal(amount_native) / displayed_decimal if displayed_decimal else None
        events.append(
            NativeCollectionEvent(
                table_id=animation.table_id,
                hand_id=animation.hand_id,
                player_index=animation.seat_idx,
                player_name=html.unescape(match.group("name")),
                amount_native=amount_native,
                amount_displayed=amount_displayed,
                money_type=match.group("money_type"),
                native_units_per_display_unit=int(scale) if scale is not None and scale == int(scale) else None,
                text=html.unescape(_TAG.sub("", animation.table_message)).strip(),
            )
        )
    return tuple(events)


def diff_game_states(
    previous: NativeGameStateSnapshot, current: NativeGameStateSnapshot
) -> tuple[NativeStackTransition, ...]:
    """Return exact observed stack changes; do not infer poker actions."""
    if (previous.table_id, previous.hand_id) != (current.table_id, current.hand_id):
        return ()
    old_players = {player.player_id: player for player in previous.players}
    transitions = []
    for player in current.players:
        old_player = old_players.get(player.player_id)
        if (
            old_player is None
            or old_player.stack_units is None
            or player.stack_units is None
            or old_player.stack_units == player.stack_units
        ):
            continue
        transitions.append(
            NativeStackTransition(
                table_id=current.table_id,
                hand_id=current.hand_id,
                round_number=current.round_number,
                player_id=player.player_id,
                player_name=player.name,
                previous_stack=old_player.stack_units,
                current_stack=player.stack_units,
            )
        )
    return tuple(transitions)


def infer_native_seat_evidence(
    _messages: list[NativeProtocolMessage], _table_ids: set[int]
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    """Return no player/action mapping until a native player index is decoded."""
    return {}


def match_native_return_seat_evidence(
    table_id: int,
    hand_id: int,
    events: list[NativeAnimationEvent],
    players: tuple[NativePlayerIdentity, ...],
    returned: list[dict],
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    """Anchor a cash player to one uniquely matching returned bet."""
    identities = {player.name: player.player_id for player in players}
    evidence = {}
    for item in returned:
        if item["money_type"] != "R" or item["player"] not in identities:
            continue
        bets = [event for event in events if event.type_code == 9 and event.action_code == 8]
        if not bets or bets[-1].funds != item["amount_native"]:
            continue
        native_index = bets[-1].seat_idx
        key = (table_id, hand_id, native_index)
        evidence[key] = NativeSeatEvidence(
            table_id,
            hand_id,
            native_index,
            identities[item["player"]],
            item["player"],
            "unique_returned_cash_bet",
        )
    return evidence


def match_native_foldout_winner_seat_evidence(
    table_id: int,
    hand_id: int,
    family: str,
    events: list[NativeAnimationEvent],
    players: tuple[NativePlayerIdentity, ...],
    collections: list[dict],
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    """Anchor a sole non-folded dealt index to an explicit no-show winner."""
    expected_by_family = {"holdem": 2, "omaha": 4, "drawmaha": 5}
    if family not in expected_by_family or len(collections) != 1:
        return {}
    collection = collections[0]
    if "doesn't show cards" not in collection["text"]:
        return {}
    expected_cards = expected_by_family[family]
    dealt_counts = Counter(event.seat_idx for event in events if event.type_code == 1)
    if not dealt_counts or any(count != expected_cards for count in dealt_counts.values()):
        return {}
    folded = {event.seat_idx for event in events if event.type_code == 9 and event.action_code == 1}
    remaining = dealt_counts.keys() - folded
    identities = {player.name: player.player_id for player in players}
    if len(remaining) != 1 or collection["player"] not in identities:
        return {}
    native_index = next(iter(remaining))
    key = (table_id, hand_id, native_index)
    return {
        key: NativeSeatEvidence(
            table_id,
            hand_id,
            native_index,
            identities[collection["player"]],
            collection["player"],
            "unique_non_folded_no_show_winner",
        )
    }


def _build_normalized_native_seat_evidence(
    grouped: dict[tuple[int, int], list[NativeGameStateSnapshot]],
    table_infos: dict[int, NativeTableInfo],
    type_15_by_hand: dict[tuple[int, int], list[NativeCollectionEvent]],
    dealer_collections_by_hand: dict[tuple[int, int], list[dict]],
    dealer_returns_by_hand: dict[tuple[int, int], list[dict]],
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    evidence = {}
    table_ids = set(table_infos)
    for (table_id, hand_id), snapshots in grouped.items():
        events = [
            event
            for snapshot in snapshots
            for event in extract_native_animation_events(
                NativeProtocolMessage(snapshot.captured_at, snapshot.raw_payload, snapshot.peer_port), table_ids
            )
        ]
        players = tuple({player.player_id: player for snapshot in snapshots for player in snapshot.players}.values())
        collections = _merge_native_collections(
            type_15_by_hand.get((table_id, hand_id), []),
            dealer_collections_by_hand.get((table_id, hand_id), []),
        )
        candidate_groups = (
            match_native_return_seat_evidence(
                table_id, hand_id, events, players, dealer_returns_by_hand.get((table_id, hand_id), [])
            ),
            match_native_foldout_winner_seat_evidence(
                table_id, hand_id, table_infos[table_id].family, events, players, collections
            ),
        )
        for candidates in candidate_groups:
            for key, candidate in candidates.items():
                existing = evidence.get(key)
                if existing is None or existing.player_id == candidate.player_id:
                    evidence[key] = candidate
                else:
                    evidence.pop(key)
    return _retain_bijective_native_seat_evidence(evidence)


def _infer_native_seat_evidence_from_opaque_funds(
    messages: list[NativeProtocolMessage], table_ids: set[int]
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    """Retain the rejected opaque-funds experiment for capture analysis only.

    ``stack_units`` is currently an opaque native funds representation. Its
    direction contradicted a known winner/action sequence and must not become
    normalized player evidence.
    """
    previous_by_table: dict[int, NativeGameStateSnapshot] = {}
    candidates: dict[tuple[int, int, int], set[tuple[int, str]]] = {}
    rosters: dict[tuple[int, int], set[int]] = {}
    player_names: dict[tuple[int, int], dict[int, str]] = {}
    dealt_seats: dict[tuple[int, int], set[int]] = {}
    hand_order: dict[int, list[int]] = {}
    for message in messages:
        snapshot = extract_game_state(message, table_ids)
        if snapshot is None:
            continue
        hand_key = (snapshot.table_id, snapshot.hand_id)
        rosters.setdefault(hand_key, set()).update(player.player_id for player in snapshot.players)
        player_names.setdefault(hand_key, {}).update((player.player_id, player.name) for player in snapshot.players)
        ordered_hands = hand_order.setdefault(snapshot.table_id, [])
        if snapshot.hand_id not in ordered_hands:
            ordered_hands.append(snapshot.hand_id)
        previous = previous_by_table.get(snapshot.table_id)
        transitions = diff_game_states(previous, snapshot) if previous else ()
        native_events = extract_native_animation_events(message, table_ids)
        dealt_seats.setdefault(hand_key, set()).update(
            event.seat_idx for event in native_events if event.type_code == 1
        )
        action_events = [event for event in native_events if event.type_code == 9]
        decreases = [transition for transition in transitions if transition.delta < 0]
        if len(action_events) == 1 and len(decreases) == 1:
            event = action_events[0]
            transition = decreases[0]
            key = (snapshot.table_id, snapshot.hand_id, event.seat_idx)
            candidates.setdefault(key, set()).add((transition.player_id, transition.player_name))
        previous_by_table[snapshot.table_id] = snapshot

    evidence = {}
    for key, identities in candidates.items():
        if len(identities) != 1:
            continue
        player_id, player_name = next(iter(identities))
        evidence[key] = NativeSeatEvidence(key[0], key[1], key[2], player_id, player_name, "unique_raw_funds_decrease")
    evidence = _retain_bijective_native_seat_evidence(evidence)
    propagated = _propagate_native_seat_evidence(evidence, rosters, dealt_seats, hand_order)
    propagated = _retain_bijective_native_seat_evidence(propagated)
    eliminated = _eliminate_unique_native_dealt_seats(propagated, rosters, player_names, dealt_seats)
    return _retain_bijective_native_seat_evidence(eliminated)


def _retain_bijective_native_seat_evidence(
    evidence: dict[tuple[int, int, int], NativeSeatEvidence],
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    """Reject a hand's anchors when one player is assigned to multiple native seats."""
    seats_by_player: dict[tuple[int, int, int], set[int]] = {}
    for (table_id, hand_id, seat_idx), item in evidence.items():
        seats_by_player.setdefault((table_id, hand_id, item.player_id), set()).add(seat_idx)
    conflicted_players = {key for key, seats in seats_by_player.items() if len(seats) > 1}
    return {
        key: item
        for key, item in evidence.items()
        if (item.table_id, item.hand_id, item.player_id) not in conflicted_players
    }


def _eliminate_unique_native_dealt_seats(
    evidence: dict[tuple[int, int, int], NativeSeatEvidence],
    rosters: dict[tuple[int, int], set[int]],
    player_names: dict[tuple[int, int], dict[int, str]],
    dealt_seats: dict[tuple[int, int], set[int]],
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    result = dict(evidence)
    for (table_id, hand_id), player_ids in rosters.items():
        seats = dealt_seats.get((table_id, hand_id), set())
        known = {
            seat_idx: item.player_id
            for (event_table, event_hand, seat_idx), item in result.items()
            if (event_table, event_hand) == (table_id, hand_id)
        }
        remaining_seats = seats - known.keys()
        remaining_players = player_ids - set(known.values())
        if len(seats) != len(player_ids) or len(remaining_seats) != 1 or len(remaining_players) != 1:
            continue
        seat_idx = next(iter(remaining_seats))
        player_id = next(iter(remaining_players))
        result[(table_id, hand_id, seat_idx)] = NativeSeatEvidence(
            table_id,
            hand_id,
            seat_idx,
            player_id,
            player_names[(table_id, hand_id)][player_id],
            "unique_dealt_seat_elimination",
        )
    return result


def _propagate_native_seat_evidence(
    evidence: dict[tuple[int, int, int], NativeSeatEvidence],
    rosters: dict[tuple[int, int], set[int]],
    dealt_seats: dict[tuple[int, int], set[int]],
    hand_order: dict[int, list[int]],
) -> dict[tuple[int, int, int], NativeSeatEvidence]:
    propagated = dict(evidence)
    for table_id, hands in hand_order.items():
        segments: list[list[int]] = []
        for hand_id in hands:
            previous_hand = segments[-1][-1] if segments else None
            signature_changed = previous_hand is not None and (
                rosters[(table_id, previous_hand)] != rosters[(table_id, hand_id)]
                or dealt_seats.get((table_id, previous_hand), set()) != dealt_seats.get((table_id, hand_id), set())
            )
            if not segments or signature_changed:
                segments.append([])
            segments[-1].append(hand_id)
        for segment in segments:
            _propagate_native_roster_segment(propagated, evidence, rosters, table_id, segment)
    return propagated


def _propagate_native_roster_segment(
    propagated: dict[tuple[int, int, int], NativeSeatEvidence],
    evidence: dict[tuple[int, int, int], NativeSeatEvidence],
    rosters: dict[tuple[int, int], set[int]],
    table_id: int,
    segment: list[int],
) -> None:
    identities_by_seat: dict[int, set[tuple[int, str]]] = {}
    for hand_id in segment:
        for (event_table, event_hand, seat_idx), item in evidence.items():
            if (event_table, event_hand) == (table_id, hand_id):
                identities_by_seat.setdefault(seat_idx, set()).add((item.player_id, item.player_name))
    for hand_id in segment:
        for seat_idx, identities in identities_by_seat.items():
            if len(identities) != 1:
                continue
            player_id, player_name = next(iter(identities))
            if player_id not in rosters[(table_id, hand_id)]:
                continue
            key = (table_id, hand_id, seat_idx)
            propagated.setdefault(
                key,
                NativeSeatEvidence(
                    table_id,
                    hand_id,
                    seat_idx,
                    player_id,
                    player_name,
                    "stable_consecutive_roster",
                ),
            )


def summarize_native_hands(messages: list[NativeProtocolMessage]) -> list[NativeHandSummary]:
    """Identify stable table/hand ids without pretending native fields are decoded."""
    table_infos: dict[int, NativeTableInfo] = {}
    table_names = {}
    for message in messages:
        payload = message.payload
        message_type = int.from_bytes(payload[:2], "little") if len(payload) >= 2 else -1
        table_info = extract_table_info(message)
        if table_info:
            table_infos[table_info.table_id] = table_info
            table_names[table_info.table_id] = table_info.name
        elif message_type == 0 and len(payload) >= 10:
            table_names.setdefault(int.from_bytes(payload[6:10], "little"), None)

    ofc_table_ids = _observed_ofc_table_ids(messages)

    snapshots: dict[tuple[int, int], list[int]] = {}
    hand_players: dict[tuple[int, int], dict[int, str]] = {}
    for message in messages:
        snapshot = extract_game_state(message, set(table_names))
        if snapshot:
            key = (snapshot.table_id, snapshot.hand_id)
            snapshots.setdefault(key, []).append(snapshot.round_number)
            players = hand_players.setdefault(key, {})
            players.update((player.player_id, player.name) for player in snapshot.players)

    return [
        NativeHandSummary(
            table_id,
            hand_id,
            table_names.get(table_id),
            count,
            "ofc"
            if table_id in ofc_table_ids
            else table_infos.get(table_id, NativeTableInfo(0, "", None, "unknown")).family,
            table_infos.get(table_id).tournament_id if table_id in table_infos else None,
            tuple(dict.fromkeys(round_number for round_number in rounds if round_number >= 0)),
            tuple(hand_players.get((table_id, hand_id), {}).values()),
        )
        for (table_id, hand_id), rounds in snapshots.items()
        for count in (len(rounds),)
    ]


def normalize_native_hands(messages: list[NativeProtocolMessage], *, raw_ref: str) -> list[dict]:
    """Build capture-only FPDB-aligned envelopes from confirmed native fields."""
    table_infos = {info.table_id: info for message in messages if (info := extract_table_info(message)) is not None}
    ofc_table_ids = _observed_ofc_table_ids(messages)
    ofc_variants = _observed_ofc_variants(messages, set(table_infos), ofc_table_ids)
    grouped: dict[tuple[int, int], list[NativeGameStateSnapshot]] = {}
    collections_by_hand: dict[tuple[int, int], list[NativeCollectionEvent]] = {}
    dealer_collections_by_hand = _collect_native_dealer_wins(messages, table_infos)
    dealer_returns_by_hand = _collect_native_dealer_returns(messages, table_infos)
    dealer_events_by_hand = _collect_native_dealer_events(messages, table_infos)
    game_changes_by_hand = _collect_native_game_changes(messages, table_infos)
    ofc_game_starts_by_hand = _collect_native_ofc_game_starts(messages, table_infos)
    evaluated_cards_by_hand: dict[tuple[int, int], set[tuple[str, ...]]] = {}
    for message in messages:
        snapshot = extract_game_state(message, set(table_infos))
        if snapshot:
            key = (snapshot.table_id, snapshot.hand_id)
            grouped.setdefault(key, []).append(snapshot)
            collections_by_hand.setdefault(key, []).extend(extract_native_collections(message, set(table_infos)))
            evaluated_cards_by_hand.setdefault(key, set()).update(_extract_evaluated_cards(message, set(table_infos)))

    seat_evidence = _build_normalized_native_seat_evidence(
        grouped,
        table_infos,
        collections_by_hand,
        dealer_collections_by_hand,
        dealer_returns_by_hand,
    )

    hands = []
    for (table_id, hand_id), snapshots in grouped.items():
        table = table_infos[table_id]
        native_game = game_changes_by_hand.get((table_id, hand_id))
        family, base, category, limit_type = _resolve_native_hand_game(
            native_game, table, table_id, ofc_table_ids
        )
        player_order: dict[int, NativePlayerIdentity] = {}
        for snapshot in snapshots:
            for player in snapshot.players:
                existing = player_order.get(player.player_id)
                if existing is None or existing.stack_units is None:
                    player_order[player.player_id] = player

        steps = []
        previous_step = None
        for step_num, snapshot in enumerate(snapshots, 1):
            stacks = {player.name: player.stack_units for player in snapshot.players if player.stack_units is not None}
            board = extract_native_board(snapshot, family)
            native_events = extract_native_animation_events(
                NativeProtocolMessage(
                    snapshot.captured_at,
                    snapshot.raw_payload,
                    peer_port=snapshot.peer_port,
                ),
                {table_id},
            )
            event_types = tuple(event.type_code for event in native_events)
            step = {
                "step_num": step_num,
                "street": _native_round_street_map(family, category).get(snapshot.round_number, "UNKNOWN"),
                "native_round": snapshot.round_number,
                "stacks": stacks,
                "bets": {},
                "board": list(board),
                "placed": {},
                "folded": [],
                "pot": 0,
                "raw": {
                    "archive": raw_ref,
                    "peer_port": snapshot.peer_port,
                    "payload_sha256": hashlib.sha256(snapshot.raw_payload).hexdigest(),
                },
                "native_events": [
                    {
                        "event_index": event.event_index,
                        "type_code": event.type_code,
                        "action_code": event.action_code,
                        **(
                            {"action_name_evidence": _NATIVE_ACTION_LABELS[event.action_code]}
                            if event.type_code == 9 and event.action_code in _NATIVE_ACTION_LABELS
                            else {}
                        ),
                        **(
                            {
                                "action_street_evidence": native_action_street(
                                    family, snapshot.round_number, event_types, category
                                )
                            }
                            if event.type_code == 9
                            else {}
                        ),
                        **(
                            {"animation_name_evidence": "private_card_deal"}
                            if event.type_code == 1 and family in {"holdem", "omaha"} and snapshot.round_number == 1
                            else {}
                        ),
                        **(
                            {"animation_name_evidence": "ofc_card_deal"}
                            if event.type_code == 1 and family == "ofc"
                            else {}
                        ),
                        **(
                            {"ofc_event_evidence": "turn_commit"}
                            if event.type_code == 9 and event.action_code == 21 and family == "ofc"
                            else {}
                        ),
                        **(
                            {"animation_name_evidence": "community_card_reveal"}
                            if event.type_code == 2
                            and family in {"holdem", "omaha"}
                            and snapshot.round_number in {2, 3, 4}
                            else {}
                        ),
                        **(
                            {"animation_name_evidence": "community_deal_transition"}
                            if event.type_code == 3
                            and family in {"holdem", "omaha"}
                            and snapshot.round_number in {2, 3, 4}
                            else {}
                        ),
                        "funds": event.funds,
                        "funds_byte": event.funds,
                        "seat_idx": None,
                        "native_index": event.seat_idx,
                        "raw_hex": event.raw_payload.hex(),
                        **(
                            {
                                "player_id_evidence": resolved.player_id,
                                "player_name_evidence": resolved.player_name,
                                "player_evidence_source": resolved.source,
                            }
                            if (resolved := seat_evidence.get((event.table_id, event.hand_id, event.seat_idx)))
                            else {}
                        ),
                        **({"table_message": event.table_message} if event.table_message is not None else {}),
                        **({"card_mnemonic": event.card_mnemonic} if event.card_mnemonic is not None else {}),
                        **(
                            {"evaluated_cards": list(cards)}
                            if event.card_mnemonic and (cards := parse_native_card_mnemonic(event.card_mnemonic))
                            else {}
                        ),
                    }
                    for event in native_events
                ],
            }
            step["diff"] = diff_snapshot_steps(previous_step, step)
            steps.append(step)
            previous_step = step

        collections = _merge_native_collections(
            collections_by_hand.get((table_id, hand_id), []),
            dealer_collections_by_hand.get((table_id, hand_id), []),
        )
        evaluated_hands = evaluated_cards_by_hand.get((table_id, hand_id), set())
        final_board = max((extract_native_board(snapshot, family) for snapshot in snapshots), key=len, default=())
        showdown = _build_native_showdown(collections, evaluated_hands, final_board)
        dealer_events = dealer_events_by_hand.get((table_id, hand_id), [])
        ofc_scores = [parsed for event in dealer_events if (parsed := parse_native_ofc_scores(event["text"]))]
        # Draw-game discards are announced exactly by the dealer, so decode them
        # for every family (non-draw hands simply have none).
        native_draws = [parsed for event in dealer_events if (parsed := parse_native_dealer_draw(event["text"]))]
        ofc_payouts = (
            [parsed for event in dealer_events if (parsed := parse_native_ofc_payout(event["text"]))]
            if family == "ofc"
            else []
        )
        ofc_fantasy_land = (
            [parsed for event in dealer_events if (parsed := parse_native_ofc_fantasy_land(event["text"]))]
            if family == "ofc"
            else []
        )
        ofc_game_complete = (
            next(
                (parsed for event in dealer_events if (parsed := parse_native_ofc_game_complete(event["text"]))),
                None,
            )
            if family == "ofc"
            else None
        )
        importability = audit_native_hand(
            steps,
            collections,
            dealer_hand_started=any(event["text"] == "New hand started" for event in dealer_events),
            dealer_hand_complete=any(event["text"] == "Hand complete" for event in dealer_events),
        )
        hands.append(
            {
                "site": "SealsWithClubs",
                "hand_id": hand_id,
                "table_id": table_id,
                "table_name": table.name,
                "tournament_id": table.tournament_id,
                "timestamp": snapshots[0].captured_at.isoformat(),
                "game": {
                    "label": native_game["game_label"] if native_game else table.name,
                    "base": base,
                    "category": category,
                    "limit_type": limit_type,
                    "fpdb_supported": False,
                    **({"ofc_variant": ofc_variants.get(table_id, "unresolved")} if family == "ofc" else {}),
                },
                "gametype": {
                    "type": "tour" if table.tournament_id else "ring",
                    "base": base,
                    "category": category,
                    "limitType": limit_type,
                    "currency": "room_native",
                    "sb": 0,
                    "bb": 0,
                    "ante": 0,
                    "mix": "none",
                    "maxSeats": len(player_order),
                },
                "streets": {"allStreets": _native_street_profile(family, category)},
                "players": [
                    {
                        "player_id": player.player_id,
                        "name": player.name,
                        "seat_idx": None,
                        "roster_index": roster_index,
                        "starting_stack": player.stack_units,
                        "native_status_values": sorted(
                            {
                                observed.native_status
                                for snapshot in snapshots
                                for observed in snapshot.players
                                if observed.player_id == player.player_id and observed.native_status is not None
                            }
                        ),
                    }
                    for roster_index, player in enumerate(player_order.values())
                ],
                "steps": steps,
                "action_evidence": _build_native_action_evidence(steps),
                "actions": [],
                "collections": collections,
                "returned": dealer_returns_by_hand.get((table_id, hand_id), []),
                "dealer_events": dealer_events,
                "ofc_result": next((result for result in ofc_scores if result["kind"] == "hand"), None),
                "ofc_total": next((result for result in ofc_scores if result["kind"] == "total"), None),
                "ofc_payouts": ofc_payouts,
                "ofc_fantasy_land": ofc_fantasy_land,
                "ofc_game_complete": ofc_game_complete,
                "ofc_game_start": ofc_game_starts_by_hand.get((table_id, hand_id)) if family == "ofc" else None,
                "ofc_showdown_rows": extract_native_ofc_showdown_rows(snapshots) if family == "ofc" else [],
                "native_draws": native_draws,
                "native_game": native_game,
                "showdown": showdown,
                "raw_refs": [raw_ref],
                "metadata": {
                    "adapter": "swc_native",
                    "state_model": "snapshot",
                    "money_unit": "room_native_integer",
                    "player_funds_field": "opaque_native_value_not_money",
                    "importability": importability,
                },
            }
        )
    return hands


def iter_capture_records(stream: BinaryIO) -> Iterator[NativeCaptureRecord]:
    """Yield complete records and reject corrupt/truncated archives."""
    while True:
        header = stream.read(_HEADER.size)
        if not header:
            return
        if len(header) != _HEADER.size:
            raise ValueError("truncated SwC native capture header")
        magic, version, direction, _reserved, peer_port, connection_id, size, timestamp_us = _HEADER.unpack(header)
        if magic != _MAGIC or version != _VERSION:
            raise ValueError("invalid SwC native capture header")
        if direction not in (0, 1):
            raise ValueError("invalid SwC native capture direction")
        if size > _MAX_PAYLOAD:
            raise ValueError("SwC native capture payload is too large")
        payload = stream.read(size)
        if len(payload) != size:
            raise ValueError("truncated SwC native capture payload")
        yield NativeCaptureRecord(
            captured_at=datetime.fromtimestamp(timestamp_us / 1_000_000, tz=UTC),
            direction="received" if direction == 0 else "sent",
            peer_port=peer_port,
            payload=payload,
            connection_id=connection_id,
        )


def build_tap(*, force: bool = False) -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("the native SwC tap is only supported on macOS")
    if not SWC_EXECUTABLE.exists():
        raise FileNotFoundError(f"SwC client not found at {SWC_APP}")
    if TAP_LIBRARY.exists() and not force and TAP_LIBRARY.stat().st_mtime >= SOURCE_PATH.stat().st_mtime:
        return TAP_LIBRARY

    BUILD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    command = [
        "clang",
        "-arch",
        "x86_64",
        "-dynamiclib",
        "-O2",
        "-Wall",
        "-Wextra",
        "-undefined",
        "dynamic_lookup",
        "-o",
        str(TAP_LIBRARY),
        str(SOURCE_PATH),
    ]
    subprocess.run(command, check=True)
    TAP_LIBRARY.chmod(0o700)
    return TAP_LIBRARY


def running_client_pids() -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", f"^{SWC_EXECUTABLE}$"],
        check=False,
        capture_output=True,
        text=True,
    )
    return [int(value) for value in result.stdout.split() if value.isdigit()]


def native_client_environment(archive: Path, tap: Path, *, port: int, include_outbound: bool) -> dict[str, str]:
    """Return a Finder-like environment plus the variables required by the tap.

    The old Qt/C++ runtime bundled by SwC aborts while parsing decimal skin
    values such as ``0.45`` when it inherits terminal locale variables (notably
    ``LC_ALL=C.UTF-8`` from uv/Codex shells). Apps started by LaunchServices do
    not normally receive those variables.
    """
    env = os.environ.copy()
    for name in tuple(env):
        if name == "LANG" or name == "LANGUAGE" or name.startswith("LC_"):
            env.pop(name, None)
    env.update(
        {
            "DYLD_INSERT_LIBRARIES": str(tap),
            "SWC_CAPTURE_PATH": str(archive),
            "SWC_CAPTURE_STATUS_PATH": str(archive.with_suffix(".status")),
            "SWC_CAPTURE_PORT": str(port),
            "SWC_CAPTURE_OUTBOUND": "1" if include_outbound else "0",
        }
    )
    return env


def launch_client(archive: Path, *, port: int = 0, include_outbound: bool = False) -> subprocess.Popen[bytes]:
    if not 0 <= port <= 65535:
        raise ValueError("capture port must be 0 (auto) or between 1 and 65535")
    active_pids = running_client_pids()
    if active_pids:
        joined = ", ".join(str(pid) for pid in active_pids)
        raise RuntimeError(
            f"SwC is already running (pid {joined}). Close it normally, then launch it through this capture command."
        )
    tap = build_tap()
    archive = archive.expanduser().resolve()
    archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive.touch(mode=0o600, exist_ok=True)
    archive.chmod(0o600)
    status_path = archive.with_suffix(".status")
    status_path.unlink(missing_ok=True)

    env = native_client_environment(archive, tap, port=port, include_outbound=include_outbound)
    return subprocess.Popen([str(SWC_EXECUTABLE)], env=env, cwd=str(Path.home()))


def inspect_archive(path: Path) -> int:
    count = 0
    total = 0
    with path.open("rb") as stream:
        for record in iter_capture_records(stream):
            count += 1
            total += len(record.payload)
            print(
                f"{record.captured_at.isoformat()} {record.direction:<8} "
                f"port={record.peer_port} bytes={len(record.payload)}"
            )
    print(f"records={count} plaintext_bytes={total}")
    return count


def print_dealer_history(path: Path) -> int:
    messages = read_dealer_history(path)
    for dealer in messages:
        print(f"{dealer.timestamp} table={dealer.table_id} Dealer: {dealer.text}")
    print(f"dealer_messages={len(messages)}")
    return len(messages)


def print_session_summary(path: Path) -> int:
    with path.open("rb") as stream:
        messages = list(iter_protocol_messages(iter_capture_records(stream)))
    hands = summarize_native_hands(messages)
    for hand in hands:
        print(
            f"table={hand.table_id} name={hand.table_name or '<unknown>'!r} "
            f"family={hand.family} tournament={hand.tournament_id} "
            f"hand={hand.hand_id} snapshots={hand.snapshot_count} rounds={list(hand.rounds)} "
            f"players={list(hand.players)}"
        )
    print(f"native_messages={len(messages)} hands={len(hands)}")
    return len(hands)


def print_stack_history(path: Path) -> int:
    """Print opaque native player-funds changes for correlation only."""
    with path.open("rb") as stream:
        messages = list(iter_protocol_messages(iter_capture_records(stream)))
    table_infos = {
        table_info.table_id: table_info
        for message in messages
        if (table_info := extract_table_info(message)) is not None
    }
    table_ids = set(table_infos)
    previous_by_table: dict[int, NativeGameStateSnapshot] = {}
    count = 0
    for message in messages:
        snapshot = extract_game_state(message, table_ids)
        if snapshot is None or table_infos[snapshot.table_id].family not in {"holdem", "omaha"}:
            continue
        previous = previous_by_table.get(snapshot.table_id)
        if previous:
            for transition in diff_game_states(previous, snapshot):
                print(
                    f"table={transition.table_id} hand={transition.hand_id} "
                    f"round={transition.round_number} player={transition.player_name!r} "
                    f"raw_funds={transition.previous_stack}->{transition.current_stack} "
                    f"raw_delta={transition.delta:+d}"
                )
                count += 1
        previous_by_table[snapshot.table_id] = snapshot
    print(f"stack_transitions={count}")
    return count


def print_animation_events(path: Path) -> int:
    """Print animation events beside opaque player-funds changes."""
    with path.open("rb") as stream:
        messages = list(iter_protocol_messages(iter_capture_records(stream)))
    table_infos = {
        table_info.table_id: table_info
        for message in messages
        if (table_info := extract_table_info(message)) is not None
    }
    table_ids = set(table_infos)
    previous_by_table: dict[int, NativeGameStateSnapshot] = {}
    count = 0
    for message_index, message in enumerate(messages):
        snapshot = extract_game_state(message, table_ids)
        if snapshot is None:
            continue
        previous = previous_by_table.get(snapshot.table_id)
        transitions = diff_game_states(previous, snapshot) if previous else ()
        events = extract_native_animation_events(message, table_ids)
        if events:
            rendered_events = ", ".join(
                (
                    f"type={event.type_code} action={event.action_code} funds={event.funds} "
                    f"seat={event.seat_idx} raw={event.raw_payload.hex()}"
                )
                for event in events
            )
            rendered_transitions = ", ".join(
                f"{transition.player_name}:{transition.delta:+d}" for transition in transitions
            )
            print(
                f"message={message_index} table={snapshot.table_id} hand={snapshot.hand_id} "
                f"round={snapshot.round_number} events=[{rendered_events}] "
                f"raw_funds_deltas=[{rendered_transitions}]"
            )
            count += len(events)
        previous_by_table[snapshot.table_id] = snapshot
    print(f"animation_events={count}")
    return count


def print_normalized_hands(path: Path) -> int:
    with path.open("rb") as stream:
        messages = list(iter_protocol_messages(iter_capture_records(stream)))
    hands = normalize_native_hands(messages, raw_ref=str(path.expanduser().resolve()))
    print(json.dumps(hands, indent=2, sort_keys=True))
    return len(hands)


def print_importability_audit(path: Path) -> int:
    """Print one compact evidence-completeness record per captured hand."""
    with path.open("rb") as stream:
        messages = list(iter_protocol_messages(iter_capture_records(stream)))
    hands = normalize_native_hands(messages, raw_ref=str(path.expanduser().resolve()))
    for hand in hands:
        audit = hand["metadata"]["importability"]
        unresolved = ",".join(f"{name}:{count}" for name, count in audit["unresolved_by_action"].items()) or "none"
        print(
            f"table={hand['table_id']} hand={hand['hand_id']} game={hand['game']['category']} "
            f"native_players={audit['resolved_native_type_9_player_count']}/{audit['native_type_9_event_count']} "
            f"actions={audit['resolved_poker_event_count']}/{audit['poker_event_count']} "
            f"unresolved={unresolved} blinds={int(audit['has_small_blind'])}/{int(audit['has_big_blind'])} "
            f"collection={int(audit['has_collection'])} started={int(audit['dealer_hand_started'])} "
            f"complete={int(audit['dealer_hand_complete'])} "
            f"status={audit['status']}"
        )
    return len(hands)


def build_native_ofc_summary(hands: list[dict]) -> list[dict]:
    """Select compact OFC scoring/session fields from normalized hands."""
    return [
        {
            "table_id": hand["table_id"],
            "table_name": hand["table_name"],
            "hand_id": hand["hand_id"],
            "variant": hand["game"].get("ofc_variant", "unresolved"),
            "result": hand["ofc_result"],
            "total": hand["ofc_total"],
            "fantasy_land": hand["ofc_fantasy_land"],
            "payouts": hand["ofc_payouts"],
            "game_start": hand["ofc_game_start"],
            "game_complete": hand["ofc_game_complete"],
            "showdown_rows": hand["ofc_showdown_rows"],
        }
        for hand in hands
        if hand["game"]["category"] == "ofc"
    ]


def print_ofc_summary(path: Path) -> int:
    """Print one machine-readable OFC summary line per native hand."""
    with path.open("rb") as stream:
        messages = list(iter_protocol_messages(iter_capture_records(stream)))
    summary = build_native_ofc_summary(normalize_native_hands(messages, raw_ref=str(path.expanduser().resolve())))
    for item in summary:
        print(json.dumps(item, sort_keys=True))
    return len(summary)


def read_dealer_history(path: Path) -> list[NativeDealerMessage]:
    messages = []
    with path.open("rb") as stream:
        records = iter_capture_records(stream)
        for message in iter_protocol_messages(records):
            dealer = extract_dealer_message(message)
            if dealer:
                messages.append(dealer)
    return messages


def follow_dealer_history(path: Path, stop: threading.Event, *, poll_seconds: float = 0.25) -> None:
    """Print only dealer messages appended after this follower starts."""
    printed = 0
    try:
        printed = len(read_dealer_history(path))
    except (FileNotFoundError, ValueError):
        pass
    while not stop.wait(poll_seconds):
        try:
            messages = read_dealer_history(path)
        except (FileNotFoundError, ValueError):
            continue
        for dealer in messages[printed:]:
            print(f"[SWC] {dealer.timestamp} table={dealer.table_id} Dealer: {dealer.text}", flush=True)
        printed = len(messages)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="build the interposer without launching SwC")
    parser.add_argument("--force-build", action="store_true", help="rebuild the interposer")
    parser.add_argument("--inspect", type=Path, help="validate and summarize an existing raw archive")
    parser.add_argument("--dealer-history", type=Path, help="print dealer messages from a raw archive")
    parser.add_argument("--session-summary", type=Path, help="list native tables, hand ids, and snapshot counts")
    parser.add_argument(
        "--stack-history", type=Path, help="list opaque native player-funds changes without inferring amounts"
    )
    parser.add_argument(
        "--animation-events", type=Path, help="list native animation events with opaque player-funds changes"
    )
    parser.add_argument("--normalized-json", type=Path, help="print capture-only normalized native hands as JSON")
    parser.add_argument("--importability-audit", type=Path, help="audit evidence completeness for every native hand")
    parser.add_argument("--ofc-summary", type=Path, help="print compact OFC score/session JSON lines")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="peer port to capture (default: auto-detect SWC game ports and exclude lobby 20001)",
    )
    parser.add_argument(
        "--include-outbound",
        action="store_true",
        help="also capture client-to-server plaintext; may contain sensitive session data",
    )
    return parser.parse_args(argv)


def _run_native_report(args: argparse.Namespace) -> bool:
    reports = (
        ("inspect", inspect_archive),
        ("dealer_history", print_dealer_history),
        ("session_summary", print_session_summary),
        ("stack_history", print_stack_history),
        ("animation_events", print_animation_events),
        ("normalized_json", print_normalized_hands),
        ("importability_audit", print_importability_audit),
        ("ofc_summary", print_ofc_summary),
    )
    for argument, report in reports:
        if path := getattr(args, argument):
            report(path)
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if _run_native_report(args):
        return 0
    if args.build or args.force_build:
        print(build_tap(force=args.force_build))
        return 0
    try:
        process = launch_client(args.archive, port=args.port, include_outbound=args.include_outbound)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"SwC launched with passive capture: pid={process.pid} archive={args.archive.expanduser().resolve()}")
    print("Dealer messages will appear with the [SWC] prefix. Close SwC normally to stop capture.")
    stop_follower = threading.Event()
    follower = threading.Thread(
        target=follow_dealer_history,
        args=(args.archive.expanduser().resolve(), stop_follower),
        daemon=True,
    )
    follower.start()
    try:
        return process.wait()
    finally:
        stop_follower.set()
        follower.join(timeout=1)


if __name__ == "__main__":
    sys.exit(main())
