from __future__ import annotations

import copy

import pytest

from fpdb_3_legacy.ChipZenToFpdb import ChipZen
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError
from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig, build_fpdb_hand


def _record() -> dict:
    return {
        "schema": "fpdb-chipzen-hand/v1",
        "match": {
            "match_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "started_at": "2026-09-02T07:30:00.000Z",
            "game_config": {
                "variant": "nlhe",
                "starting_stack": 1000,
                "small_blind": 5,
                "big_blind": 10,
                "ante": 0,
                "num_players": 2,
            },
            "seats": [
                {"seat": 0, "participant_id": "p0", "display_name": "AlphaBot", "is_self": True},
                {"seat": 1, "participant_id": "p1", "display_name": "BetaBot", "is_self": False},
            ],
        },
        "round_start": {
            "round_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "server_ts": "2026-09-02T07:30:01.000Z",
            "state": {
                "hand_number": 12,
                "dealer_seat": 0,
                "your_hole_cards": ["As", "Kh"],
                "stacks": [1000, 1000],
            },
        },
        "phase_changes": [
            {"state": {"phase": "flop", "board": ["Qs", "7h", "3d"]}},
        ],
        "round_result": {
            "round_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "server_ts": "2026-09-02T07:30:06.100Z",
            "result": {
                "hand_number": 12,
                "winner_seats": [0],
                "pot": 100,
                "payouts": [{"seat": 0, "amount": 100}],
                "showdown": [],
                "action_history": [
                    {"seat": 0, "action": "post_small_blind", "amount": 5, "phase": "preflop", "is_timeout": False},
                    {"seat": 1, "action": "post_big_blind", "amount": 10, "phase": "preflop", "is_timeout": False},
                    {"seat": 0, "action": "raise", "amount": 30, "phase": "preflop", "is_timeout": False},
                    {"seat": 1, "action": "call", "amount": 20, "phase": "preflop", "is_timeout": False},
                    {"seat": 1, "action": "check", "amount": 0, "phase": "flop", "is_timeout": False},
                    {"seat": 0, "action": "raise", "amount": 40, "phase": "flop", "is_timeout": False},
                    {"seat": 1, "action": "fold", "amount": 0, "phase": "flop", "is_timeout": False},
                ],
                "stacks": [1030, 970],
                "deck_commitment": "",
                "deck_reveal": None,
            },
        },
    }


def test_stable_hand_id_is_deterministic_and_signed_bigint_safe() -> None:
    a = ChipZen.stable_hand_id("match-a", "round-a", 1)
    b = ChipZen.stable_hand_id("match-a", "round-a", 1)
    c = ChipZen.stable_hand_id("match-b", "round-a", 1)
    assert a == b
    assert a != c
    assert 0 <= a <= (2**63 - 1)


def test_normalize_maps_chipzen_to_fpdb_capture_model() -> None:
    data = ChipZen.normalize_record(_record())
    assert data["site"] == "ChipZen"
    assert data["gametype"]["category"] == "holdem"
    assert data["gametype"]["limitType"] == "nl"
    assert data["gametype"]["currency"] == "play"
    assert data["buttonpos"] == 1
    assert data["players"][0]["seat_idx"] == 0
    assert data["players"][1]["seat_idx"] == 1
    assert data["community"] == {"FLOP": ["Qs", "7h", "3d"]}
    assert data["actions"][0]["type"] == "small blind"
    assert data["actions"][2] == {"type": "raises", "street": "PREFLOP", "player": "AlphaBot", "to": 30}
    assert data["actions"][3] == {"type": "calls", "street": "PREFLOP", "player": "BetaBot", "amount": 20}
    assert data["collections"] == [{"player": "AlphaBot", "pot": 100}]


def test_build_real_fpdb_hand_from_chipzen_record() -> None:
    normalized = ChipZen.normalize_record(_record())
    config = HttpCaptureHandConfig(site_ids={"ChipZen": 141, "default": 141})
    hand = build_fpdb_hand(normalized, config=config)
    assert hand.sitename == "ChipZen"
    assert hand.tablename.startswith("ChipZen ")
    assert hand.buttonpos == 1
    assert hand.maxseats == 2
    assert [player[1] for player in hand.players] == ["AlphaBot", "BetaBot"]
    assert hand.board["FLOP"] == ["Qs", "7h", "3d"]
    assert hand.collected == [["AlphaBot", 100]] or hand.collected == [("AlphaBot", 100)]


def test_missing_phase_change_is_rejected_when_street_was_reached() -> None:
    record = _record()
    record["phase_changes"] = []
    with pytest.raises(FpdbParseError, match="required phase_change"):
        ChipZen.normalize_record(record)


def test_same_local_hand_number_in_different_matches_gets_different_id() -> None:
    first = ChipZen.normalize_record(_record())["hand_id"]
    second_record = copy.deepcopy(_record())
    second_record["match"]["match_id"] = "bbbbbbbb-e5f6-7890-abcd-ef1234567890"
    second = ChipZen.normalize_record(second_record)["hand_id"]
    assert first != second


def test_unknown_seat_action_is_rejected() -> None:
    record = _record()
    record["round_result"]["result"]["action_history"].append(
        {"seat": 4, "action": "fold", "amount": 0, "phase": "flop", "is_timeout": False}
    )
    with pytest.raises(FpdbParseError, match="unknown seat"):
        ChipZen.normalize_record(record)
