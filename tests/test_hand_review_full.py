"""The whole-hand review document, version 2: every street for postflop study tools (#448).

Version 1 (PreflopAdvisor's) stops at the flop. Version 2 adds the board, each
street's starting pot and stacks, every action with its size in big blinds and
as a share of the pot, and the hero's decisions on every street, with the same
rule: a hand it cannot describe exactly is refused, never approximated.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy.Hand import hand_factory
from fpdb_3_legacy.hand_review_payload import (
    AMBIGUOUS_POSITION,
    FULL_SCHEMA,
    FULL_VERSION,
    SCHEMA,
    UNSUPPORTED_BOARD,
    HandReviewError,
    build_full_review,
    build_hand_review,
    export_hands,
    full_review_document,
    refusal_counts,
    review_document,
    review_hands,
)
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from tests.helpers.icm_hands import SNG_ALLIN
from tests.helpers.icm_hands import parse as parse_text

REVIEW = Path(__file__).resolve().parent / "fixtures" / "hands" / "pokerstars" / "review"


def parse(config: Any, name: str) -> Any:
    return PokerStars(config=config, in_path=str(REVIEW / name), autostart=True).getProcessedHands()[0]


def full(config: Any, name: str) -> dict[str, Any]:
    return build_full_review(parse(config, name)).to_full_payload()


def street(entry: dict[str, Any], name: str) -> dict[str, Any]:
    (found,) = (item for item in entry["streets"] if item["street"] == name)
    return found


def line(street_entry: dict[str, Any]) -> list[tuple]:
    return [(action["seat"], action["action"], action["amount"]) for action in street_entry["actions"]]


# -- what a postflop hand says ------------------------------------------------------------


def test_a_3bet_pot_is_described_to_the_flop_fold(legacy_config) -> None:
    entry = full(legacy_config, "nl_3bet_6max.txt")

    assert entry["board"] == "Kc7h2s"
    assert [item["street"] for item in entry["streets"]] == ["PREFLOP", "FLOP"]
    flop = street(entry, "FLOP")
    assert flop["cards"] == "Kc7h2s" and flop["board"] == "Kc7h2s"
    assert flop["pot_start"] == 17.5 and flop["pot_start_bb"] == 17.5
    # The two players still in, with what they had behind: 120 - 8 and 80 - 8.
    assert flop["stacks"] == [
        {"seat": "CO", "stack": 112, "stack_bb": 112.0},
        {"seat": "BU", "stack": 72, "stack_bb": 72.0},
    ]
    assert line(flop) == [("CO", "Check", 0), ("BU", "Bet", 6), ("CO", "Fold", 0)]
    assert entry["hero_decisions"] == [
        {"street": "PREFLOP", "index": 2},
        {"street": "PREFLOP", "index": 6},
        {"street": "FLOP", "index": 0},
        {"street": "FLOP", "index": 2},
    ]


def test_sizes_are_shares_of_the_pot(legacy_config) -> None:
    entry = full(legacy_config, "nl_3bet_6max.txt")

    preflop, flop = street(entry, "PREFLOP")["actions"], street(entry, "FLOP")["actions"]
    # The open to 2.47: an increment of 1.47 over a pot of 2.50 once the 1 is called.
    assert preflop[2]["size_pct_pot"] == pytest.approx(58.8)
    # The bet of 6 into 17.50.
    assert flop[1]["size_pct_pot"] == pytest.approx(6 / 17.5 * 100)
    assert flop[0]["size_pct_pot"] is None and flop[2]["size_pct_pot"] is None


def test_pot_limit_raises_are_pot_sized(legacy_config) -> None:
    entry = full(legacy_config, "plo_3bet_6max.txt")

    raises = [action for item in entry["streets"] for action in item["actions"] if action["action"] in ("Bet", "Raise")]
    assert [action["size_pct_pot"] for action in raises] == pytest.approx([100.0, 100.0, 100.0])


def test_an_unmatched_all_in_is_returned_before_the_flop(tmp_path) -> None:
    # Hero shoves 4000 into Villain's 3000: 1000 comes back, so the flop pot is 6200.
    hand, _path = parse_text(tmp_path, SNG_ALLIN)

    entry = build_full_review(hand).to_full_payload()

    assert entry["board"] == "2c7d9hJc3s"
    assert [item["street"] for item in entry["streets"]] == ["PREFLOP", "FLOP", "TURN", "RIVER"]
    flop = street(entry, "FLOP")
    assert flop["pot_start"] == 6200 and flop["actions"] == []
    assert flop["stacks"] == [
        {"seat": "BU", "stack": 1000, "stack_bb": 5.0},
        {"seat": "SB", "stack": 0, "stack_bb": 0.0},
    ]
    assert street(entry, "RIVER")["pot_start"] == 6200


# -- what it refuses -------------------------------------------------------------------


def test_a_board_run_twice_is_refused(legacy_config) -> None:
    hand = parse(legacy_config, "nl_3bet_6max.txt")
    hand.runItTimes = 2

    with pytest.raises(HandReviewError) as refused:
        build_full_review(hand)
    assert refused.value.code == UNSUPPORTED_BOARD


def test_flop_actions_without_flop_cards_are_refused(legacy_config) -> None:
    hand = parse(legacy_config, "nl_3bet_6max.txt")
    hand.board["FLOP"] = []

    with pytest.raises(HandReviewError) as refused:
        build_full_review(hand)
    assert refused.value.code == UNSUPPORTED_BOARD


def test_an_action_after_a_fold_is_refused(legacy_config) -> None:
    hand = parse(legacy_config, "nl_3bet_6max.txt")
    hand.actions["FLOP"].append(("Hero", "checks"))  # Hero folded the flop already

    with pytest.raises(HandReviewError) as refused:
        build_full_review(hand)
    assert refused.value.code == AMBIGUOUS_POSITION


# -- the document -----------------------------------------------------------------------


def test_version_2_is_its_own_document_and_version_1_is_unchanged(legacy_config) -> None:
    hand = parse(legacy_config, "nl_3bet_6max.txt")

    whole = full_review_document([build_full_review(hand)])
    preflop = review_document([build_hand_review(hand)])

    assert (whole["schema"], whole["version"]) == (FULL_SCHEMA, FULL_VERSION)
    assert preflop["schema"] == SCHEMA and preflop["version"] == 1
    assert "streets" not in preflop["hands"][0] and "actions" not in whole["hands"][0]
    # PreflopAdvisor's spelling stays in version 1: the 3-bet is a "Raise" there too.
    assert [action["action"] for action in preflop["hands"][0]["actions"]][3] == "Raise"


def test_a_batch_describes_every_street_and_lists_its_refusals(legacy_config) -> None:
    good = parse(legacy_config, "nl_hu.txt")
    twice = parse(legacy_config, "plo_3bet_6max.txt")
    twice.runItTimes = 2

    reviews, skipped = review_hands([good, twice], full=True)

    assert [len(review.streets) for review in reviews] == [2]
    assert [entry["code"] for entry in skipped] == [UNSUPPORTED_BOARD]


def test_a_hand_read_back_from_the_database_says_the_same(importer, fresh_db, legacy_config, tmp_path) -> None:
    copy = tmp_path / "nl_3bet_6max.txt"
    shutil.copy(REVIEW / "nl_3bet_6max.txt", copy)
    importer.addImportFile(str(copy), "PokerStars")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()

    stored = build_full_review(hand_factory(hand_id, legacy_config, fresh_db)).to_full_payload()
    parsed = full(legacy_config, "nl_3bet_6max.txt")

    for key in ("board", "hero_decisions"):
        assert stored[key] == parsed[key], key
    assert [line(item) for item in stored["streets"]] == [line(item) for item in parsed["streets"]]
    assert [item["pot_start"] for item in stored["streets"]] == [item["pot_start"] for item in parsed["streets"]]


# -- the batch export -------------------------------------------------------------------


def test_refusals_are_counted_by_reason_most_frequent_first() -> None:
    skipped = [{"code": "b"}, {"code": "a"}, {"code": "b"}, {"code": "c"}, {"code": "a"}, {"code": "b"}]

    assert list(refusal_counts(skipped).items()) == [("b", 3), ("a", 2), ("c", 1)]


def test_a_batch_of_500_hands_is_one_document_that_says_what_it_left_out(legacy_config, tmp_path) -> None:
    import copy
    import json

    good = parse(legacy_config, "nl_3bet_6max.txt")
    twice = copy.copy(good)
    twice.runItTimes = 2
    hands = [good] * 480 + [twice] * 20

    export = export_hands(hands, tmp_path / "batch.json", generated_at="2026-10-29T18:00:00+00:00")

    assert (export.exported, export.refused, export.refused_total) == (480, {UNSUPPORTED_BOARD: 20}, 20)
    document = json.loads((tmp_path / "batch.json").read_text(encoding="utf-8"))
    assert (document["schema"], document["version"]) == (FULL_SCHEMA, FULL_VERSION)
    assert len(document["hands"]) == 480 and len(document["skipped"]) == 20
    assert document["generated_at"] == "2026-10-29T18:00:00+00:00"
