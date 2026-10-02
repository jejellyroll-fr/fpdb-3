"""Preflop hand-review payload for PreflopAdvisor (#328).

Real hand histories go in, the document PreflopAdvisor's hand review reads
comes out. The checks are on what that reader relies on (seat names, the
line of play, raise-to amounts in big blinds) and on what the payload must
never do: round a sizing away, guess a position, or invent a value for a
hand it cannot describe.
"""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fpdb_3_legacy.Hand import hand_factory
from fpdb_3_legacy.hand_review_payload import (
    AMBIGUOUS_POSITION,
    HERO_CARDS,
    HERO_NOT_DEALT,
    MISSING_PREFLOP,
    NO_HERO,
    NO_HERO_DECISION,
    PAYLOAD_VERSION,
    SEAT_NAMES,
    UNSUPPORTED_GAME,
    UNSUPPORTED_POSTS,
    HandReviewError,
    JsonFileTransport,
    build_hand_review,
    decision_at,
    review_document,
    review_hands,
    summary_lines,
)
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hands" / "pokerstars"


def parse(config: Any, relative: str) -> Any:
    return PokerStars(config=config, in_path=str(FIXTURES / relative), autostart=True).getProcessedHands()[0]


def payload(config: Any, relative: str, **kwargs: Any) -> dict[str, Any]:
    return build_hand_review(parse(config, relative), **kwargs).to_payload()


def line(entry: dict[str, Any]) -> list[tuple]:
    return [(action["seat"], action["action"], action.get("to_bb")) for action in entry["actions"]]


# -- real hands -----------------------------------------------------------------


def test_a_nlhe_3bet_pot_reads_as_preflop_advisor_expects(legacy_config) -> None:
    entry = payload(legacy_config, "review/nl_3bet_6max.txt")

    assert entry["game"] == "NL"
    assert entry["table_size"] == 6
    assert entry["seats"] == ["UTG", "MP", "CO", "BU", "SB", "BB"]
    assert entry["hero"] == "CO"
    assert entry["hero_name"] == "Hero"
    assert entry["hero_seat_no"] == 2
    assert entry["hero_cards"] == "AhQd"
    # Hero 120, deepest opponent 100: the depth a tree is chosen for.
    assert entry["effective_stack_bb"] == 100.0
    assert line(entry) == [
        ("UTG", "Fold", None),
        ("MP", "Fold", None),
        ("CO", "Raise", 2.47),
        ("BU", "Raise", 8.0),
        ("SB", "Fold", None),
        ("BB", "Fold", None),
        # A call carries its street total too, never just what it added.
        ("CO", "Call", 8.0),
    ]
    assert entry["hero_decisions"] == [2, 6]
    assert entry["selected_decision"] is None


def test_sizings_keep_the_source_amounts(legacy_config) -> None:
    entry = payload(legacy_config, "review/nl_3bet_6max.txt")
    open_raise, three_bet, *_rest, call = entry["actions"][2:]

    # 2.47 BB stays 2.47: PreflopAdvisor matches it to a 2.5 BB branch with
    # its own tolerance, so nothing here rounds it.
    assert open_raise["to"] == 2.47
    assert open_raise["amount"] == 2.47
    assert open_raise["pot_before_bb"] == 1.5
    assert open_raise["to_call_bb"] == 1.0
    assert three_bet["to"] == 8
    assert three_bet["amount"] == 8
    assert three_bet["pot_before"] == 3.97
    # The hero's second decision: 5.53 more to call into an 11.97 pot, 80 BB
    # effective against the button, who is the one still in.
    assert call["amount"] == 5.53
    assert call["to_call"] == 5.53
    assert call["pot_before"] == 11.97
    assert call["effective_stack_bb"] == pytest.approx(80.0 - 8.0)


def test_a_plo_3bet_pot(legacy_config) -> None:
    entry = payload(legacy_config, "review/plo_3bet_6max.txt")

    assert entry["game"] == "PLO"
    assert entry["hero"] == "SB"
    assert entry["hero_cards"] == "AsAdKhQh"
    assert line(entry) == [
        ("UTG", "Fold", None),
        ("MP", "Fold", None),
        ("CO", "Fold", None),
        ("BU", "Raise", 3.5),
        ("SB", "Raise", 11.5),
        ("BB", "Fold", None),
        ("BU", "Call", 11.5),
    ]
    assert entry["hero_decisions"] == [4]
    assert entry["blinds"] == {"sb": 0.25, "bb": 0.5, "sb_bb": 0.5}


def test_heads_up_names_the_button_the_small_blind(legacy_config) -> None:
    entry = payload(legacy_config, "review/nl_hu.txt")

    assert entry["seats"] == ["SB", "BB"]
    assert entry["hero"] == "BB"
    assert line(entry) == [("SB", "Raise", 3.0), ("BB", "Raise", 9.0), ("SB", "Call", 9.0)]
    assert entry["effective_stack_bb"] == 75.0


def test_a_short_table_counts_only_the_players_dealt_in(legacy_config) -> None:
    # A 9-max table with four players, empty seats in between and one more
    # sitting out: positions are those of a four-handed game, and the raw seat
    # numbers are kept so the mapping can be audited.
    entry = payload(legacy_config, "review/nl_9max_short_sitout.txt")

    assert entry["table_size"] == 4
    assert entry["max_seats"] == 9
    assert entry["seats"] == ["CO", "BU", "SB", "BB"]
    assert [player["seat_no"] for player in entry["players"]] == [7, 9, 2, 5]
    assert entry["hero"] == "CO"


def test_a_nine_handed_tournament_with_antes(legacy_config) -> None:
    entry = payload(legacy_config, "review/nl_9handed_antes_mtt.txt")

    assert entry["seats"] == ["UTG", "UTG1", "MP", "LJ", "HJ", "CO", "BU", "SB", "BB"]
    assert entry["hero"] == "UTG1"
    assert entry["ante_bb"] == pytest.approx(0.1)
    assert entry["actions"][0]["pot_before_bb"] == pytest.approx(2.4)
    # The ante is not part of the raise: a raise to 225 is 2.25 BB.
    assert entry["actions"][1]["to_bb"] == 2.25
    assert entry["effective_stack_bb"] == 40.0
    assert entry["game_type"] == "tour"
    assert entry["tournament"]["tourney_no"] == "3100000001"


def test_a_hand_read_back_from_the_database_correlates_to_its_id(importer, fresh_db, legacy_config, tmp_path) -> None:
    source = FIXTURES / "review" / "nl_3bet_6max.txt"
    copy = tmp_path / source.name
    shutil.copy(source, copy)
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()

    # The id comes from the hand itself; a caller does not have to pass it.
    stored = build_hand_review(hand_factory(hand_id, legacy_config, fresh_db)).to_payload()
    parsed = payload(legacy_config, "review/nl_3bet_6max.txt")

    assert stored["hand_id"] == str(hand_id)
    assert stored["fpdb_hand_id"] == hand_id
    # The database keeps a placeholder table size, so none is claimed.
    assert stored["max_seats"] is None
    assert parsed["max_seats"] == 6
    assert stored["site_hand_no"] == "2810000001"
    for key in ("seats", "hero", "hero_cards", "effective_stack_bb", "hero_decisions"):
        assert stored[key] == parsed[key], key
    assert line(stored) == line(parsed)


# -- positions ------------------------------------------------------------------


def stub_hand(players: int, *, hero_index: int = 0, button_offset: int = 0, **overrides: Any) -> Any:
    """A hold'em hand where everyone folds to the big blind but the hero, who raises."""
    seats = list(range(1, players + 1))
    names = [f"P{seat}" for seat in seats]
    # Preflop order: everyone after the big blind, the blinds last.
    order = names[2:] + names[:2] if players > 2 else names
    small, big = (names[0], names[1]) if players > 2 else (names[0], names[1])
    hero = order[hero_index]
    preflop = []
    for name in order:
        if name == hero:
            preflop.append((name, "raises", Decimal(2), Decimal(3), Decimal(1), False))
        elif name != big or hero == big:
            preflop.append((name, "folds"))
    if hero != big:
        preflop.append((big, "folds"))
    hand = SimpleNamespace(
        gametype={"category": "holdem", "limitType": "nl", "type": "ring", "currency": "USD"},
        hero=hero,
        sb="0.5",
        bb="1",
        sitout=set(),
        players=[[seat, name, "100", None, None] for seat, name in zip(seats, names, strict=True)],
        buttonpos=seats[-1] if players > 2 else seats[0],
        actions={
            "BLINDSANTES": [(small, "small blind", Decimal("0.5"), False), (big, "big blind", Decimal(1), False)],
            "PREFLOP": preflop,
        },
        handid="1",
        sitename="Test",
        tablename="T",
        maxseats=9,
        startTime=None,
        join_holecards=lambda player, asList=True: ["Ah", "Kd"] if player == hero else [],
    )
    for key, value in overrides.items():
        setattr(hand, key, value)
    return hand


@pytest.mark.parametrize("players", sorted(SEAT_NAMES))
def test_every_supported_table_size_names_every_seat(players: int) -> None:
    for hero_index in range(players):
        review = build_hand_review(stub_hand(players, hero_index=hero_index))
        assert [seat.position for seat in review.seats] == list(SEAT_NAMES[players])
        assert review.hero_position == SEAT_NAMES[players][hero_index]


def test_seat_names_are_preflop_advisors() -> None:
    # Its TreeReader lists (BB first), read backwards; up to six the six-max
    # list is cut from the button outwards.
    six = "BB,SB,BU,CO,MP,UTG".split(",")
    for players in range(2, 7):
        assert list(SEAT_NAMES[players]) == list(reversed(six[:players]))
    assert list(SEAT_NAMES[7]) == list(reversed("BB,SB,BU,CO,HJ,MP,UTG".split(",")))
    assert list(SEAT_NAMES[8]) == list(reversed("BB,SB,BU,CO,HJ,LJ,MP,UTG".split(",")))
    assert list(SEAT_NAMES[9]) == list(reversed("BB,SB,BU,CO,HJ,LJ,MP,UTG1,UTG".split(",")))


# -- refusals -------------------------------------------------------------------


def refusal(hand: Any, **kwargs: Any) -> str:
    with pytest.raises(HandReviewError) as caught:
        build_hand_review(hand, **kwargs)
    return caught.value.code


def test_a_straddle_is_refused_rather_than_misplaced(legacy_config) -> None:
    assert refusal(parse(legacy_config, "holdem/straddle.txt")) == UNSUPPORTED_POSTS


def test_games_preflop_advisor_has_no_trees_for_are_refused(legacy_config) -> None:
    assert refusal(parse(legacy_config, "stud/7stud.txt")) == UNSUPPORTED_GAME
    limit = stub_hand(6)
    limit.gametype = {**limit.gametype, "limitType": "fl"}
    assert refusal(limit) == UNSUPPORTED_GAME


def test_a_hand_without_a_hero_is_refused() -> None:
    hand = stub_hand(6)
    hand.hero = ""
    assert refusal(hand) == NO_HERO
    assert refusal(stub_hand(6), hero="Nobody") == HERO_NOT_DEALT


def test_a_hero_without_known_cards_is_refused() -> None:
    hand = stub_hand(6)
    hand.join_holecards = lambda player, asList=True: ["Ah"]
    assert refusal(hand) == HERO_CARDS


def test_a_hand_without_preflop_action_is_refused() -> None:
    hand = stub_hand(6)
    hand.actions = {**hand.actions, "PREFLOP": []}
    assert refusal(hand) == MISSING_PREFLOP


def test_a_walk_gives_the_big_blind_no_decision() -> None:
    hand = stub_hand(6, hero_index=5)
    hand.actions = {**hand.actions, "PREFLOP": [(f"P{seat}", "folds") for seat in (3, 4, 5, 6, 1)]}
    assert refusal(hand) == NO_HERO_DECISION


def test_a_button_that_contradicts_the_blinds_is_refused(legacy_config) -> None:
    # Three-handed with the button posting the small blind: no seating makes
    # both true, so no position is claimed.
    assert refusal(parse(legacy_config, "holdem/tournament_ko.txt")) == AMBIGUOUS_POSITION


def test_a_listed_player_who_never_acts_is_refused() -> None:
    hand = stub_hand(6, hero_index=1)
    hand.actions = {**hand.actions, "PREFLOP": hand.actions["PREFLOP"][1:]}
    assert refusal(hand) == AMBIGUOUS_POSITION


def test_two_big_blinds_are_refused() -> None:
    hand = stub_hand(6)
    extra = ("P4", "big blind", Decimal(1), False)
    hand.actions = {**hand.actions, "BLINDSANTES": [*hand.actions["BLINDSANTES"], extra]}
    assert refusal(hand) == AMBIGUOUS_POSITION


# -- decisions and the document -------------------------------------------------


def test_the_replayed_point_selects_a_hero_decision(legacy_config) -> None:
    review = build_hand_review(parse(legacy_config, "review/nl_3bet_6max.txt"))
    # Hero decisions are actions 2 (the open) and 6 (the call of the 3-bet).
    assert decision_at(review, 0) == 2  # before anything: the next one
    assert decision_at(review, 3) == 2  # paused right after the open
    assert decision_at(review, 4) == 6  # facing the 3-bet: the next one
    assert decision_at(review, 7) == 6  # past preflop: the last one
    with pytest.raises(ValueError):
        review.with_selected_decision(3)


def test_the_document_is_versioned_and_holds_many_hands(legacy_config, tmp_path) -> None:
    reviews = [
        build_hand_review(parse(legacy_config, "review/nl_3bet_6max.txt")).with_selected_decision(6),
        build_hand_review(parse(legacy_config, "review/plo_3bet_6max.txt")),
    ]
    document = review_document(reviews, generated_at="2026-10-02T12:00:00+00:00")

    assert document["version"] == PAYLOAD_VERSION == 1
    assert document["schema"] == "fpdb-3/preflop-hand-review"
    assert document["source"] == "fpdb-3"
    assert [hand["game"] for hand in document["hands"]] == ["NL", "PLO"]
    assert document["hands"][0]["selected_decision"] == 6

    target = tmp_path / "review.json"
    assert JsonFileTransport(target).send(document) == str(target)
    assert json.loads(target.read_text(encoding="utf-8")) == document


def test_the_summary_marks_the_hero_decisions(legacy_config) -> None:
    review = build_hand_review(parse(legacy_config, "review/nl_3bet_6max.txt")).with_selected_decision(6)
    lines = summary_lines(review)

    assert lines[0] == "NL - 6 players - PokerStars.COM"
    assert lines[1] == "Hero: CO [Ah Qd] - 120 BB (100 BB effective)"
    assert "* CO: Raise to 2.47 BB  (pot 1.5 BB, solver review available)" in lines
    assert "> CO: Call 5.53 BB  (pot 11.97 BB, solver review available)" in lines
    assert "  BU: Raise to 8 BB" in lines


def test_an_ev_cash_out_is_not_a_decision() -> None:
    hand = stub_hand(6)
    hand.actions = {**hand.actions, "PREFLOP": [*hand.actions["PREFLOP"], ("P3", "cashout")]}

    review = build_hand_review(hand)

    assert [action.kind for action in review.actions] == ["raises", "folds", "folds", "folds", "folds", "folds"]


def test_a_batch_lists_the_hands_it_refuses(legacy_config) -> None:
    hands = [
        parse(legacy_config, "review/nl_3bet_6max.txt"),
        parse(legacy_config, "holdem/straddle.txt"),
        parse(legacy_config, "review/plo_3bet_6max.txt"),
    ]

    reviews, skipped = review_hands(hands)
    document = review_document(reviews, skipped=skipped)

    assert [hand["game"] for hand in document["hands"]] == ["NL", "PLO"]
    [refused] = document["skipped"]
    assert (refused["hand"], refused["code"]) == ("PokerStars.COM#9999999999", UNSUPPORTED_POSTS)
    assert "straddle" in refused["message"]
    assert "skipped" not in review_document(reviews)
