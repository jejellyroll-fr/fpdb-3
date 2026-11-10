from __future__ import annotations

import copy

import pytest

from fpdb_3_legacy.ChipZenToFpdb import ChipZen
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError
from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig, build_fpdb_hand


def _record() -> dict:
    """Protocol-faithful ChipZen fold-on-flop fixture.

    This mirrors the authoritative full-hand example in
    docs/protocol/POKER-GAME-STATE-PROTOCOL.md, including its legacy
    action_history convention where the BB preflop call is recorded as 30 while
    turn_result reports the actual incremental call of 20.
    """
    return {
        "schema": "fpdb-chipzen-hand/v1",
        "match": {
            "match_id": "m_abc123",
            "started_at": "2026-04-13T14:00:00.000Z",
            "game_config": {
                "variant": "nlhe",
                "starting_stack": 1000,
                "small_blind": 5,
                "big_blind": 10,
                "ante": 0,
                "num_players": 2,
            },
            "seats": [
                {"seat": 0, "participant_id": "p0", "display_name": "Bot A", "is_self": True},
                {"seat": 1, "participant_id": "p1", "display_name": "Bot B", "is_self": False},
            ],
        },
        "round_start": {
            "round_id": "r_550e8400-e29b-41d4-a716-446655440000",
            "server_ts": "2026-04-13T14:00:00.100Z",
            "state": {
                "hand_number": 1,
                "dealer_seat": 0,
                "your_hole_cards": ["As", "Kh"],
                "stacks": [1000, 1000],
                "deck_commitment": "",
            },
        },
        "phase_changes": [
            {"type": "phase_change", "state": {"phase": "flop", "board": ["Qs", "7h", "3d"]}},
        ],
        "turn_results": [
            {"details": {"seat": 0, "action": "raise", "amount": 30}},
            {"details": {"seat": 1, "action": "call", "amount": 20}},
            {"details": {"seat": 1, "action": "check", "amount": 0}},
            {"details": {"seat": 0, "action": "raise", "amount": 40}},
            {"details": {"seat": 1, "action": "fold", "amount": 0}},
        ],
        "round_result": {
            "round_id": "r_550e8400-e29b-41d4-a716-446655440000",
            "server_ts": "2026-04-13T14:00:06.100Z",
            "result": {
                "hand_number": 1,
                "winner_seats": [0],
                "pot": 100,
                "payouts": [{"seat": 0, "amount": 100}],
                "showdown": [],
                "action_history": [
                    {"seat": 0, "action": "post_small_blind", "amount": 5, "phase": "preflop", "is_timeout": False},
                    {"seat": 1, "action": "post_big_blind", "amount": 10, "phase": "preflop", "is_timeout": False},
                    {"seat": 0, "action": "raise", "amount": 30, "phase": "preflop", "is_timeout": False},
                    # Official worked example uses 30 here, while turn_result is 20.
                    {"seat": 1, "action": "call", "amount": 30, "phase": "preflop", "is_timeout": False},
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


def _showdown_record() -> dict:
    record = _record()
    record["match"]["match_id"] = "m_showdown"
    record["round_start"]["round_id"] = "r_showdown"
    record["round_result"]["round_id"] = "r_showdown"
    record["round_start"]["state"]["your_hole_cards"] = ["Ah", "Kd"]
    record["phase_changes"] = [
        {"state": {"phase": "flop", "board": ["Ts", "7h", "2d"]}},
        {"state": {"phase": "turn", "board": ["Ts", "7h", "2d", "Qc"]}},
        {"state": {"phase": "river", "board": ["Ts", "7h", "2d", "Qc", "3s"]}},
    ]
    record["turn_results"] = [
        {"details": {"seat": 0, "action": "raise", "amount": 30}},
        {"details": {"seat": 1, "action": "call", "amount": 20}},
        {"details": {"seat": 0, "action": "check", "amount": 0}},
        {"details": {"seat": 1, "action": "check", "amount": 0}},
        {"details": {"seat": 0, "action": "check", "amount": 0}},
        {"details": {"seat": 1, "action": "check", "amount": 0}},
        {"details": {"seat": 0, "action": "check", "amount": 0}},
        {"details": {"seat": 1, "action": "check", "amount": 0}},
    ]
    record["round_result"]["result"].update(
        {
            "pot": 60,
            "winner_seats": [0],
            "payouts": [{"seat": 0, "amount": 60}],
            "showdown": [
                {"seat": 0, "hole_cards": ["Ah", "Kd"], "hand_rank": "pair"},
                {"seat": 1, "hole_cards": ["Jc", "Tc"], "hand_rank": "high_card"},
            ],
            "action_history": [
                {"seat": 0, "action": "post_small_blind", "amount": 5, "phase": "preflop", "is_timeout": False},
                {"seat": 1, "action": "post_big_blind", "amount": 10, "phase": "preflop", "is_timeout": False},
                {"seat": 0, "action": "raise", "amount": 30, "phase": "preflop", "is_timeout": False},
                {"seat": 1, "action": "call", "amount": 30, "phase": "preflop", "is_timeout": False},
                {"seat": 0, "action": "check", "amount": 0, "phase": "flop", "is_timeout": False},
                {"seat": 1, "action": "check", "amount": 0, "phase": "flop", "is_timeout": False},
                {"seat": 0, "action": "check", "amount": 0, "phase": "turn", "is_timeout": False},
                {"seat": 1, "action": "check", "amount": 0, "phase": "turn", "is_timeout": False},
                {"seat": 0, "action": "check", "amount": 0, "phase": "river", "is_timeout": False},
                {"seat": 1, "action": "check", "amount": 0, "phase": "river", "is_timeout": False},
            ],
            "stacks": [1030, 970],
        }
    )
    return record


def test_stable_hand_id_is_deterministic_and_signed_bigint_safe() -> None:
    a = ChipZen.stable_hand_id("match-a", "round-a", 1)
    b = ChipZen.stable_hand_id("match-a", "round-a", 1)
    c = ChipZen.stable_hand_id("match-b", "round-a", 1)
    assert a == b
    assert a != c
    assert 0 <= a <= (2**63 - 1)


def test_normalize_maps_official_protocol_example_to_fpdb_capture_model() -> None:
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
    assert data["actions"][2] == {"type": "raises", "street": "PREFLOP", "player": "Bot A", "to": 30}
    # The action_history call-to 30 is normalized with authoritative turn_result=20.
    assert data["actions"][3] == {"type": "calls", "street": "PREFLOP", "player": "Bot B", "amount": 20}
    assert data["collections"] == [{"player": "Bot A", "pot": 100}]


def test_call_total_is_inferred_without_turn_result_when_unambiguous() -> None:
    record = _record()
    record["turn_results"] = []
    data = ChipZen.normalize_record(record)
    assert data["actions"][3]["amount"] == 20


def test_build_real_fpdb_hand_from_chipzen_record() -> None:
    normalized = ChipZen.normalize_record(_record())
    config = HttpCaptureHandConfig(site_ids={"ChipZen": 141, "default": 141})
    hand = build_fpdb_hand(normalized, config=config)
    assert hand.sitename == "ChipZen"
    assert hand.tablename.startswith("ChipZen ")
    assert hand.buttonpos == 1
    assert hand.maxseats == 2
    assert [player[1] for player in hand.players] == ["Bot A", "Bot B"]
    assert hand.board["FLOP"] == ["Qs", "7h", "3d"]
    assert hand.collected == [["Bot A", 100]] or hand.collected == [("Bot A", 100)]


def test_full_board_and_showdown_are_reconstructed() -> None:
    normalized = ChipZen.normalize_record(_showdown_record())
    assert normalized["community"] == {
        "FLOP": ["Ts", "7h", "2d"],
        "TURN": ["Qc"],
        "RIVER": ["3s"],
    }
    shown = {entry["player"]: entry for entry in normalized["holecards"]}
    assert shown["Bot A"]["cards"] == ["Ah", "Kd"]
    assert shown["Bot A"]["shown"] is True
    assert shown["Bot B"]["cards"] == ["Jc", "Tc"]
    assert shown["Bot B"]["shown"] is True


def test_missing_phase_change_is_rejected_when_street_was_reached() -> None:
    record = _record()
    record["phase_changes"] = []
    with pytest.raises(FpdbParseError, match="required phase_change"):
        ChipZen.normalize_record(record)


def test_turn_must_extend_flop() -> None:
    record = _showdown_record()
    record["phase_changes"][1]["state"]["board"] = ["As", "Ks", "Qh", "Qc"]
    with pytest.raises(FpdbParseError, match="does not extend the recorded flop"):
        ChipZen.normalize_record(record)


def test_same_local_hand_number_in_different_matches_gets_different_id() -> None:
    first = ChipZen.normalize_record(_record())["hand_id"]
    second_record = copy.deepcopy(_record())
    second_record["match"]["match_id"] = "m_other"
    second = ChipZen.normalize_record(second_record)["hand_id"]
    assert first != second


def test_unknown_seat_action_is_rejected() -> None:
    record = _record()
    record["round_result"]["result"]["action_history"].append(
        {"seat": 4, "action": "fold", "amount": 0, "phase": "flop", "is_timeout": False}
    )
    with pytest.raises(FpdbParseError, match="unknown seat"):
        ChipZen.normalize_record(record)


def test_ambiguous_call_amount_is_rejected() -> None:
    record = _record()
    record["turn_results"] = []
    record["round_result"]["result"]["action_history"][3]["amount"] = 25
    with pytest.raises(FpdbParseError, match="Ambiguous ChipZen call amount"):
        ChipZen.normalize_record(record)
