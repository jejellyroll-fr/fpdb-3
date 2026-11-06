"""The spot of each hero decision, and decisions grouped by spot (#448)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fpdb_3_legacy.hand_review_payload import build_full_review, build_hand_review
from fpdb_3_legacy.hand_review_spots import SPOT_FIELDS, decision_spots, spot_groups
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

REVIEW = Path(__file__).resolve().parent / "fixtures" / "hands" / "pokerstars" / "review"


def review(config: Any, name: str) -> Any:
    hand = PokerStars(config=config, in_path=str(REVIEW / name), autostart=True).getProcessedHands()[0]
    return build_full_review(hand)


def test_a_flop_decision_in_a_3bet_pot_names_its_spot(legacy_config) -> None:
    decisions = decision_spots(review(legacy_config, "nl_3bet_6max.txt"))

    flop = [decision for decision in decisions if decision["street"] == "FLOP"]
    assert [decision["index"] for decision in flop] == [0, 2]
    # Hero (CO, 112 behind) against the button's 3-bet (72 behind): 72 over a pot of 17.50 is 4.1.
    assert flop[0]["spot"] == {
        "game": "NL",
        "table_size": 6,
        "street": "FLOP",
        "pot_type": "three_bet",
        "hero": "CO",
        "aggressor": "BU",
        "players": 2,
        "spr": "4_to_7",
        "board_rank": "king-high",
        "board_suits": "rainbow",
        "board_pairing": "unpaired",
    }


def test_a_preflop_decision_is_read_from_the_actions_before_it(legacy_config) -> None:
    preflop = [d for d in decision_spots(review(legacy_config, "nl_3bet_6max.txt")) if d["street"] == "PREFLOP"]

    # The open: nobody in before Hero. Facing the 3-bet: the button raised last.
    assert [(d["spot"]["pot_type"], d["spot"]["aggressor"]) for d in preflop] == [
        ("unopened", None),
        ("three_bet", "BU"),
    ]
    assert all(d["spot"]["spr"] is None and d["spot"]["board_rank"] is None for d in preflop)


def test_a_preflop_only_review_has_no_spots(legacy_config) -> None:
    hand = PokerStars(config=legacy_config, in_path=str(REVIEW / "nl_hu.txt"), autostart=True).getProcessedHands()[0]

    assert decision_spots(build_hand_review(hand)) == []


def test_decisions_are_grouped_by_spot_most_frequent_first(legacy_config) -> None:
    three_bet = review(legacy_config, "nl_3bet_6max.txt")
    heads_up = review(legacy_config, "nl_hu.txt")

    groups = spot_groups([three_bet, heads_up, three_bet])

    assert set(groups[0]["spot"]) == set(SPOT_FIELDS)
    counts = [group["count"] for group in groups]
    assert counts == sorted(counts, reverse=True)
    # The two flop decisions of the 3-bet pot, twice over, share one spot.
    (flop,) = (group for group in groups if group["spot"]["street"] == "FLOP" and group["spot"]["hero"] == "CO")
    assert flop["count"] == 4
    assert {decision["index"] for decision in flop["decisions"]} == {0, 2}
    assert sum(counts) == 2 * len(decision_spots(three_bet)) + len(decision_spots(heads_up))


def test_the_same_seats_in_another_game_are_another_spot(legacy_config) -> None:
    # Codex (#639): six-handed NL and PLO, the same seats, the same line: two spots, not one.
    nl = review(legacy_config, "nl_3bet_6max.txt")
    plo = review(legacy_config, "plo_3bet_6max.txt")

    groups = spot_groups([nl, plo])

    assert {group["spot"]["game"] for group in groups} == {"NL", "PLO"}
    assert all(len({decision["hand_id"] for decision in group["decisions"]}) == 1 for group in groups)
