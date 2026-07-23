"""Seated-but-not-dealt players must not be recorded as having played the hand.

The capture reads the table's seat snapshot, so every occupied seat was turned
into an addPlayer operation whether or not that seat was dealt in. On CoinPoker
this made the hero a participant in every hand played while they were sitting
out: on 2026-07-23 the database held 19 hands for jeje1976, of which 10 had no
hole cards, no action and no winnings for them -- real hands at the table, but
not hands they played. The hand count (and every per-hand stat) was inflated.
"""

from __future__ import annotations

from fpdb_3_legacy.http_capture_hand_builder import build_hand_operations


def _seated(*names: str) -> list[dict]:
    return [
        {"name": name, "seat_idx": idx, "starting_stack": 100.0}
        for idx, name in enumerate(names)
    ]


def _added_players(hand_data: dict) -> list[str]:
    return [
        op["args"][1]
        for op in build_hand_operations(hand_data)
        if op.get("method") == "addPlayer"
    ]


def test_player_who_never_acted_is_not_seated() -> None:
    hand = {
        "players": _seated("hero", "villain", "sitting_out"),
        "actions": [
            {"type": "small blind", "player": "hero", "amount": "0.01"},
            {"type": "folds", "player": "villain"},
        ],
    }

    assert _added_players(hand) == ["hero", "villain"]


def test_a_fold_is_enough_to_count_as_dealt() -> None:
    players = _seated("hero", "folder")
    players[0]["cards"] = ["Ah", "Kd"]
    hand = {
        "players": players,
        "actions": [{"type": "folds", "player": "folder"}],
    }

    assert set(_added_players(hand)) == {"hero", "folder"}


def test_dealt_cards_alone_count_as_taking_part() -> None:
    # The hero is dealt but the capture recorded no action for them yet.
    players = _seated("hero", "bystander")
    players[0]["cards"] = ["Ah", "Kd"]
    hand = {"players": players}

    assert _added_players(hand) == ["hero"]


def test_collecting_a_pot_counts_as_taking_part() -> None:
    hand = {
        "players": _seated("hero", "winner"),
        "collections": [{"player": "winner", "pot": "1.20"}],
    }

    assert _added_players(hand) == ["winner"]


def test_hand_with_nothing_attributable_keeps_every_seat() -> None:
    # Nothing could be attributed: emitting a hand with no players at all would
    # be worse than the previous behaviour, so every seat is kept.
    hand = {"players": _seated("a", "b", "c")}

    assert _added_players(hand) == ["a", "b", "c"]
