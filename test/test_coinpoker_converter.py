"""Tests for the CoinPoker protocol decoder and hand converter.

Fixture ``data/coinpoker_hand_events.json`` holds the decoded ``game.*`` events
of two real captured hands (player names anonymized). Hand 91426500343 is
complete; 91426500344 was still in progress when capture stopped and must be
rejected rather than imported truncated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy.coinpoker_hand_builder import build_hands
from fpdb_3_legacy.coinpoker_protocol import decode_frame, split_frames
from fpdb_3_legacy.http_capture_hand_builder import (
    CaptureNotImportableError,
    build_fpdb_hand,
    render_fpdb_hand,
)

FIXTURE = Path(__file__).parent / "data" / "coinpoker_hand_events.json"


def _load_events() -> list[tuple]:
    raw = json.loads(FIXTURE.read_text())
    return [tuple(e) for e in raw]


def _hand(hand_id: str) -> dict:
    hands = build_hands(_load_events(), "PLO4")
    return next(h for h in hands if h["hand_id"] == hand_id)


# --- protocol decoder ---------------------------------------------------------


def test_decode_frame_tlv_map_with_string() -> None:
    # type 0x12 map, 1 field, key "c", type 0x08 string "hi".
    payload = b"\x12\x00\x01\x00\x01c\x08\x00\x02hi"
    assert decode_frame(0x80, payload) == {"c": "hi"}


def test_split_frames_reads_length_prefixed_frames() -> None:
    payload = b"\x12\x00\x00"  # empty map
    stream = b"\x80\x00\x03" + payload + b"\x80\x00\x03" + payload
    frames = split_frames(stream)
    assert len(frames) == 2
    assert all(flags == 0x80 and body == payload for flags, body in frames)


# --- hand conversion ----------------------------------------------------------


def test_builds_two_hands_from_fixture() -> None:
    hands = build_hands(_load_events(), "PLO4")
    assert {h["hand_id"] for h in hands} == {"91426500343", "91426500344"}


def test_complete_hand_maps_to_fpdb_hand() -> None:
    hand = build_fpdb_hand(_hand("91426500343"))
    assert hand.handid == "91426500343"
    assert hand.gametype["base"] == "hold"
    assert hand.gametype["category"] == "omahahi"
    assert len(hand.players) == 5


def test_complete_hand_renders_expected_narrative() -> None:
    text = render_fpdb_hand(build_fpdb_hand(_hand("91426500343")))
    assert "Omaha Pot Limit ($0.01/$0.02)" in text
    assert "Dealt to Hero [Js 8s 7s 4d]" in text
    assert "Villain2: raises $0.05 to $0.07" in text
    assert "*** FLOP *** [Qc 9s 6c]" in text
    assert "*** TURN *** [Qc 9s 6c] [5s]" in text
    assert "Villain4 collected $0.2" in text
    assert "Rake $0.01" in text


def test_hole_cards_and_board_are_mapped() -> None:
    h = _hand("91426500343")
    hero = next(hc for hc in h["holecards"] if hc["player"] == "Hero")
    assert hero["closed"] == ["Js", "8s", "7s", "4d"]
    assert h["community"]["FLOP"] == ["Qc", "9s", "6c"]
    assert h["community"]["TURN"] == ["5s"]


def test_incomplete_hand_is_rejected() -> None:
    # Capture ended mid-hand: no winner -> no collections -> not importable.
    with pytest.raises(CaptureNotImportableError):
        build_fpdb_hand(_hand("91426500344"))
