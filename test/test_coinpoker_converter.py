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

from fpdb_3_legacy.coinpoker_hand_builder import _collect_players, _detect_category, build_hands
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
    assert all(h["collections"] for h in hands)  # both captured hands are complete


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


def _hole_cards_event(count: int) -> list[tuple]:
    values = ["ACE", "KING", "QUEEN", "JACK", "TEN", "NINE"]
    cards = [{"suit": "SPADES", "value": values[i]} for i in range(count)]
    return [("game.hole_cards", "H", {"holeCards": cards})]


def test_variant_detected_from_hero_hole_card_count() -> None:
    # The number of cards dealt to the hero identifies the Omaha variant; the
    # session-wide hint is ignored when the hero's cards are present.
    assert _detect_category(_hole_cards_event(2), "PLO4") == ("hold", "holdem")
    assert _detect_category(_hole_cards_event(4), "PLO5") == ("hold", "omahahi")
    assert _detect_category(_hole_cards_event(5), "PLO4") == ("hold", "5_omahahi")
    assert _detect_category(_hole_cards_event(6), "PLO4") == ("hold", "6_omahahi")


def test_variant_falls_back_to_hint_when_hero_cards_absent() -> None:
    # Observing a table (no hero hole cards captured): trust the GUI hint.
    assert _detect_category([("game.pre_hand_start_info", "H", {})], "PLO5") == ("hold", "5_omahahi")
    assert _detect_category([], "NLHE") == ("hold", "holdem")
    assert _detect_category([], "Shortdeck") == ("hold", "6_holdem")


def _two_card_hand(hole: list[tuple[str, str]], board: list[tuple[str, str]]) -> list[tuple]:
    def cards(pairs):
        return [{"value": v, "suit": s} for v, s in pairs]

    return [
        ("game.hole_cards", "H", {"holeCards": cards(hole)}),
        ("game.dealer_cards", "H", {"dealerCards": {"FLOP": cards(board)}}),
    ]


def test_shortdeck_detected_from_hint_when_no_low_cards() -> None:
    # Hold'em and short-deck both deal two cards, so the hint decides -- but only
    # when nothing in the hand contradicts a 36-card deck.
    hand = _two_card_hand([("ACE", "SPADES"), ("KING", "HEARTS")], [("TEN", "SPADES"), ("NINE", "CLUBS"), ("SEVEN", "HEARTS")])
    assert _detect_category(hand, "Shortdeck") == ("hold", "6_holdem")
    assert _detect_category(hand, "NLHE") == ("hold", "holdem")


def test_low_card_overrides_a_wrong_shortdeck_hint() -> None:
    # A 2-5 anywhere proves a full deck: it is regular Hold'em, hint notwithstanding.
    hand = _two_card_hand([("ACE", "SPADES"), ("KING", "HEARTS")], [("FOUR", "CLUBS"), ("TEN", "SPADES"), ("ACE", "DIAMONDS")])
    assert _detect_category(hand, "Shortdeck") == ("hold", "holdem")


def test_hand_start_time_uses_event_init_timestamp() -> None:
    # The protocol's own clock (epoch ms) must win over import wall-clock so
    # replayed captures keep their real dates.
    hand = _hand("91426500343")
    assert hand["timestamp"] is not None
    assert hand["timestamp"].year == 2026  # from the fixture's initTimeStamp, not 1970/now


def test_plo5_hand_keeps_its_fifth_card() -> None:
    # A 5-card hand imported under a stale "PLO4" hint must not be truncated.
    events = _load_events()
    patched = []
    for name, hid, data in events:
        if name == "game.hole_cards" and isinstance(data, dict) and data.get("holeCards"):
            cards = list(data["holeCards"])
            cards.append({"suit": "HEARTS", "value": "TWO"})  # 5th card
            data = {**data, "holeCards": cards}
        patched.append((name, hid, data))
    hand = next(h for h in build_hands(patched, "PLO4") if h["holecards"])
    assert hand["gametype"]["category"] == "5_omahahi"
    hero = next(hc for hc in hand["holecards"] if hc["player"] == "Hero")
    assert len(hero["closed"]) == 5


def test_seat_reuse_keeps_one_player_per_seat() -> None:
    # A seat's occupant changes within the captured window: fpdb must never get
    # two players in the same seat (previously raised FpdbHandPartial).
    evs = [
        ("game.seat", "H", {"seatId": 3, "userName": "Alice", "userChips": 2.0, "betAmout": 0}),
        ("game.seat", "H", {"seatId": 3, "userName": "Bob", "userChips": 1.0, "betAmout": 0}),
        ("game.seat", "H", {"seatId": 4, "userName": "Carol", "userChips": 3.0, "betAmout": 0}),
    ]
    players = _collect_players(evs)
    assert set(players) == {"Alice", "Carol"}
    seats = [p["seat"] for p in players.values()]
    assert len(seats) == len(set(seats))


def test_incomplete_hand_is_rejected() -> None:
    # Drop the winner events of a hand (as if capture stopped before showdown):
    # no collection -> the hand must be rejected, not imported truncated.
    events = [
        e
        for e in _load_events()
        if not (e[1] == "91426500343" and e[0] in ("game.winnerInfo", "game.cumulativeWinnerInfo"))
    ]
    hand_data = next(h for h in build_hands(events, "PLO4") if h["hand_id"] == "91426500343")
    assert not hand_data["collections"]
    with pytest.raises(CaptureNotImportableError):
        build_fpdb_hand(hand_data)
