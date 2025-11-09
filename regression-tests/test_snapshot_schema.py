#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the canonical snapshot serializer."""

from datetime import datetime
from types import SimpleNamespace

from tools.serialize_hand_for_snapshot import (
    serialize_hand_for_snapshot,
    serialize_hands_batch,
    verify_hand_invariants,
    validate_snapshot_for_db,
    build_db_payload,
    simulate_db_insert,
)


class DummyStats:
    """Minimal stats object emulating DerivedStats output."""

    def __init__(self, hands, players, actions):
        self._hands = hands
        self._players = players
        self._actions = actions

    def getHands(self):
        return self._hands

    def getHandsPlayers(self):
        return self._players

    def getHandsActions(self):
        return self._actions


def build_dummy_hand():
    """Create a synthetic Hand instance for serializer tests."""
    hand_stats = {
        "siteHandNo": 987654321,
        "tableName": "Test Table",
        "siteId": 1,
        "siteName": "PokerStars",
        "startTime": datetime(2025, 1, 1, 12, 0, 0),
        "importTime": datetime(2025, 1, 1, 12, 1, 0),
        "seats": 2,
        "heroSeat": 1,
        "maxPosition": 2,
        "playersVpi": 1,
        "playersAtStreet1": 2,
        "playersAtStreet2": 2,
        "playersAtStreet3": 2,
        "playersAtStreet4": 1,
        "playersAtShowdown": 1,
        "street0Raises": 1,
        "street1Raises": 1,
        "street2Raises": 1,
        "street3Raises": 0,
        "street4Raises": 0,
        "street0Pot": 150,
        "street1Pot": 450,
        "street2Pot": 750,
        "street3Pot": 1050,
        "street4Pot": 1350,
        "finalPot": 1350,
        "gametype": {
            "base": "hold",
            "category": "holdem",
            "currency": "USD",
            "limitType": "nl",
            "sb": 50,
            "bb": 100,
        },
    }

    player_stats = {
        "Hero": {
            "seatNo": 1,
            "startCash": 10000,
            "effStack": 9500,
            "winnings": 1250,
            "rake": 50,
            "totalProfit": 1250,
            "position": "BTN",
        },
        "Villain": {
            "seatNo": 2,
            "startCash": 10000,
            "effStack": 10000,
            "winnings": 0,
            "rake": 0,
            "totalProfit": -1250,
            "position": "BB",
        },
    }

    action_stats = {
        1: {
            "actionNo": 1,
            "streetActionNo": 1,
            "street": -1,
            "actionId": 2,
            "actionName": "small blind",
            "player": "Hero",
            "amount": 50,
            "amountCalled": 0,
            "raiseTo": 0,
            "numDiscarded": 0,
            "cardsDiscarded": None,
            "allIn": False,
        },
        2: {
            "actionNo": 2,
            "streetActionNo": 1,
            "street": -1,
            "actionId": 4,
            "actionName": "big blind",
            "player": "Villain",
            "amount": 100,
            "amountCalled": 0,
            "raiseTo": 0,
            "numDiscarded": 0,
            "cardsDiscarded": None,
            "allIn": False,
        },
        3: {
            "actionNo": 3,
            "streetActionNo": 1,
            "street": 0,
            "actionId": 7,
            "actionName": "raises",
            "player": "Hero",
            "amount": 250,
            "amountCalled": 100,
            "raiseTo": 350,
            "numDiscarded": 0,
            "cardsDiscarded": None,
            "allIn": False,
        },
    }

    stats = DummyStats(hand_stats, player_stats, action_stats)
    return SimpleNamespace(
        stats=stats,
        handid=hand_stats["siteHandNo"],
        tablename=hand_stats["tableName"],
        siteId=hand_stats["siteId"],
        sitename=hand_stats["siteName"],
        gametype=hand_stats["gametype"],
        startTime=hand_stats["startTime"],
        importTime=hand_stats["importTime"],
        collectees={"Hero": 1250},
        cashouts={},
        cashOutFees={},
        uncalledbets={},
    )


def test_serialize_hand_for_snapshot_produces_canonical_sections():
    dummy_hand = build_dummy_hand()
    serialized = serialize_hand_for_snapshot(dummy_hand)

    assert set(serialized.keys()) >= {"hand_details", "players", "actions"}
    hand_details = serialized["hand_details"]
    assert hand_details["siteHandNo"] == 987654321
    assert isinstance(hand_details["finalPot"], int)

    players = serialized["players"]
    assert players[0]["playerName"] == "Hero"
    assert isinstance(players[0]["startCash"], int)

    violations = verify_hand_invariants(serialized)
    assert violations == []


def test_serialize_hands_batch_deterministic():
    dummy_hand = build_dummy_hand()
    batch = serialize_hands_batch([dummy_hand, dummy_hand])

    assert len(batch) == 2
    assert batch[0]["hand_details"]["siteHandNo"] == batch[1]["hand_details"]["siteHandNo"]


def test_verify_hand_invariants_detects_bad_money():
    dummy_hand = build_dummy_hand()
    serialized = serialize_hand_for_snapshot(dummy_hand)
    serialized["players"][0]["winnings"] = 12.5

    violations = verify_hand_invariants(serialized)
    assert any("players[].winnings" in msg for msg in violations)


def test_validate_snapshot_for_db_enforces_required_fields():
    dummy_hand = build_dummy_hand()
    serialized = serialize_hand_for_snapshot(dummy_hand)

    assert validate_snapshot_for_db(serialized) == []

    serialized["hand_details"].pop("heroSeat", None)
    violations = validate_snapshot_for_db(serialized)
    assert any("hand_details.heroSeat" in msg for msg in violations)


def test_build_db_payload_returns_table_rows():
    dummy_hand = build_dummy_hand()
    serialized = serialize_hand_for_snapshot(dummy_hand)

    payload = build_db_payload(serialized)

    assert payload["Hands"]["siteHandNo"] == 987654321
    assert payload["HandsPlayers"][0]["playerName"] == "Hero"
    assert payload["HandsActions"][0]["actionId"] == 2


def test_simulate_db_insert_success():
    dummy_hand = build_dummy_hand()
    serialized = serialize_hand_for_snapshot(dummy_hand)
    issues = simulate_db_insert(serialized)
    assert issues == []


def test_simulate_db_insert_detects_missing_columns():
    dummy_hand = build_dummy_hand()
    serialized = serialize_hand_for_snapshot(dummy_hand)
    serialized["hand_details"].pop("siteName", None)
    issues = simulate_db_insert(serialized)
    assert any("Hands.siteName" in issue for issue in issues)
