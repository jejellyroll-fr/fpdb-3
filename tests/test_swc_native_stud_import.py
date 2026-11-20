"""SwC native capture: tournament stud hands become importable (#829, step 2).

Each test builds one 7-Card Stud tournament hand in the room's real wire layout
(tests/helpers/swc_native_payloads.py) -- seat blocks before the records,
one/three-byte amounts, labelled actions -- and checks that normalization reads
every action's player from its seat, every amount exactly, every starting
stack from the seat funds, and imports the hand only when all of it balances.
Names and ids are made up.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpdb_3_legacy.http_capture_db_import import _native_public_import_copy
from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig, build_fpdb_hand
from fpdb_3_legacy.swc_native_capture import (
    NativeProtocolMessage,
    build_native_canonical_actions,
    card_id_to_str,
    native_hand_is_publicly_importable,
    normalize_native_hands,
    parse_native_dealer_win,
)
from tests.helpers.swc_native_payloads import (
    native_action_event,
    native_dealer_message,
    native_event_list,
    native_player_record,
    native_seat_block,
    native_state_payload,
    native_tournament_table,
)

TABLE_ID = 123460001
TOURNAMENT_ID = 123456789
HAND_ID = 123460002
HIDDEN = 0xFF
# seat -> (player id, name, down cards, door card); seat 0 is empty.
SEATS = {
    1: (11, "alice", (21, 40), 2),
    2: (12, "bob", (HIDDEN, HIDDEN), 30),
    3: (13, "carol", (HIDDEN, HIDDEN), 22),
    4: (14, "dave", (HIDDEN, HIDDEN), 17),
    5: (15, "erin", (HIDDEN, HIDDEN), 0),
}
START = 1500
ANTE, BRING_IN, SMALL_BET = 2, 5, 10
FOLD, ANTE_ACTION, BRING_IN_ACTION, RAISE = 1, 4, 5, 9


def _snapshot(round_number: int, funds: dict[int, int], events: tuple[bytes, ...] = (), *, dealt: bool = True):
    seats = [None]
    for seat, (player_id, name, down, door) in SEATS.items():
        cards = bytes([3, *down, door]) if dealt else b"\0"
        seats.append((native_seat_block(funds=funds[seat], cards=cards), native_player_record(player_id, name)))
    return native_state_payload(
        TABLE_ID,
        HAND_ID,
        seats,
        round_number=round_number,
        events=native_event_list(*events) if events else b"",
    )


def _messages(*, drop_raise: bool = False, closing_funds_for_bob: int | None = None):
    """erin brings in (timed out), alice folds, bob completes, everyone else folds."""
    funds = dict.fromkeys(SEATS, START - ANTE)
    payloads = [
        native_tournament_table(TABLE_ID, TOURNAMENT_ID, "Sample Freeroll - 7-Card Stud"),
        _snapshot(0, funds, tuple(native_action_event(ANTE_ACTION, ANTE, seat) for seat in SEATS), dealt=False),
        native_dealer_message(TABLE_ID, "New hand started"),
    ]
    funds[5] -= BRING_IN
    payloads.append(_snapshot(1, funds, (native_action_event(BRING_IN_ACTION, BRING_IN, 5, label="TO"),)))
    payloads.append(_snapshot(1, funds, (native_action_event(FOLD, 0, 1),)))
    funds[2] -= SMALL_BET
    payloads.append(_snapshot(1, funds, () if drop_raise else (native_action_event(RAISE, SMALL_BET, 2),)))
    for seat in (3, 4, 5):
        payloads.append(_snapshot(1, funds, (native_action_event(FOLD, 0, seat),)))
    pot = len(SEATS) * ANTE + BRING_IN + BRING_IN
    funds[2] += SMALL_BET - BRING_IN + pot
    if closing_funds_for_bob is not None:
        funds[2] = closing_funds_for_bob
    payloads.append(_snapshot(7, funds))
    payloads += [
        native_dealer_message(TABLE_ID, f"Uncalled bet ({SMALL_BET - BRING_IN}) returned to bob"),
        native_dealer_message(TABLE_ID, "Hand complete"),
        native_dealer_message(TABLE_ID, f"bob wins ({pot}): doesn't show cards"),
    ]
    start = datetime(2026, 11, 20, 10, tzinfo=UTC)
    return [
        NativeProtocolMessage(start + timedelta(seconds=index), payload, peer_port=20013)
        for index, payload in enumerate(payloads)
    ]


def _hand(**kwargs) -> dict:
    [hand] = normalize_native_hands(_messages(**kwargs), raw_ref="capture.raw")
    return hand


def test_each_action_is_read_from_the_seat_that_made_it():
    hand = _hand()

    assert {player["name"]: player["seat_idx"] for player in hand["players"]} == {
        name: seat for seat, (_, name, _, _) in SEATS.items()
    }
    assert [(action["type"], action["player"], action["amount"], action.get("to")) for action in hand["actions"]] == [
        *[("ante", name, ANTE, None) for _, name, _, _ in SEATS.values()],
        ("bringin", "erin", BRING_IN, None),
        ("folds", "alice", 0, None),
        ("completes", "bob", SMALL_BET, SMALL_BET),
        ("folds", "carol", 0, None),
        ("folds", "dave", 0, None),
        ("folds", "erin", 0, None),
        ("uncalled", "bob", SMALL_BET - BRING_IN, None),
    ]


def test_starting_stacks_come_from_the_seat_funds_once_the_hand_balances():
    hand = _hand()

    assert {player["name"]: player["starting_stack"] for player in hand["players"]} == dict.fromkeys(
        (name for _, name, _, _ in SEATS.values()), START
    )
    assert {player["starting_stack_source"] for player in hand["players"]} == {"native_seat_funds_closed_ledger"}
    assert hand["native_seat_ledger"]["closed"] is True


def test_a_complete_stud_hand_is_importable_with_its_stakes_and_tournament():
    hand = _hand()

    assert native_hand_is_publicly_importable(hand)
    assert hand["metadata"]["importability"]["status"] == "importable"
    assert (hand["gametype"]["type"], hand["gametype"]["sb"], hand["gametype"]["bb"], hand["gametype"]["ante"]) == (
        "tour",
        5,
        10,
        2,
    )
    assert hand["tournament_id"] == TOURNAMENT_ID
    # Antes without blinds are every stud hand, not a bomb pot.
    assert hand["bomb_pot"] == 0


def test_the_local_player_and_every_door_card_reach_the_hand():
    hand = _hand()

    assert hand["hero"] == "alice"
    third = {entry["player"]: entry for entry in hand["holecards"] if entry["street"] == "THIRD"}
    assert third["alice"]["closed"] == [card_id_to_str(21), card_id_to_str(40)]
    assert third["erin"] == {
        "player": "erin",
        "street": "THIRD",
        "open": [card_id_to_str(0)],
        "closed": [],
        "dealt": True,
    }


def test_the_built_hand_counts_the_completion_as_voluntary_and_aggressive():
    hand = build_fpdb_hand(
        _native_public_import_copy(_hand()),
        config=HttpCaptureHandConfig(site_ids={"SealsWithClubs": 23, "default": 23}),
    )
    hand.totalPot()
    hand.assembleHand()

    stats = hand.stats.handsplayers
    assert stats["bob"]["street0VPI"] is True
    assert stats["bob"]["street0Aggr"] is True
    assert stats["alice"]["street0VPI"] is False
    assert hand.stats.hands["playersVpi"] == 1
    assert sum(player["totalProfit"] for player in stats.values()) == 0


def test_a_hand_missing_an_action_stays_capture_only():
    hand = _hand(drop_raise=True)

    assert not native_hand_is_publicly_importable(hand)
    assert hand["actions"] == []


def test_a_hand_whose_stacks_do_not_close_stays_capture_only():
    hand = _hand(closing_funds_for_bob=START)

    assert hand["native_seat_ledger"]["closed"] is False
    assert {"player": "bob", "expected_native": START + 13, "observed_native": START} in hand["native_seat_ledger"][
        "mismatches"
    ]
    assert not native_hand_is_publicly_importable(hand)


@pytest.mark.parametrize(
    ("text", "player", "amount"),
    [
        ("alice wins side pot 1(600) with Pair of J and A 10 8", "alice", 600),
        ("alice wins main pot(4,123) with Pair of J and A 10 8", "alice", 4123),
        ("alice wins (22): doesn't show cards", "alice", 22),
    ],
)
def test_dealer_wins_are_read_per_pot(text, player, amount):
    parsed = parse_native_dealer_win(text, tournament=True)

    assert (parsed["player"], parsed["amount_native"]) == (player, amount)


def test_only_the_first_third_street_raise_is_a_completion():
    evidence = [
        {"player": "erin", "street": "THIRD", "action": "bring_in", "amount_native": 5},
        {"player": "bob", "street": "THIRD", "action": "raise", "amount_native": 10},
        {"player": "erin", "street": "THIRD", "action": "raise", "amount_native": 15},
        {"player": "bob", "street": "FOURTH", "action": "bet", "amount_native": 10},
    ]

    actions = build_native_canonical_actions(evidence, [], stud=True)

    assert [(action["type"], action.get("to")) for action in actions] == [
        ("bringin", None),
        ("completes", 10),
        ("raises", 20),
        ("bets", None),
    ]
