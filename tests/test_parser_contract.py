"""The generic parser contract (#903): its rules, and every converter held to it.

The second half parses the whole regression corpus (the cases of
``test_live_parser_regression``) and checks each hand against
:func:`parser_contract.contract_errors`. A file that breaks the contract today
is listed in :data:`KNOWN_CONTRACT_DEBT` with what it breaks; the list may only
shrink: a file that starts to break the contract fails, and so does one that
stops breaking it while still listed.
"""

from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import parser_contract
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.parser_contract import check_gametype, check_hand, completeness_issues, hand_invariants
from tests.test_live_parser_regression import CASES

GAMETYPE = {
    "type": "ring",
    "base": "hold",
    "category": "holdem",
    "limitType": "nl",
    "currency": "USD",
    "sb": "0.01",
    "bb": "0.02",
}

# Each entry is a parser bug the contract found when it was written down
# (#903), left for its own fix: (step, field) of every violation of the file.
KNOWN_CONTRACT_DEBT: dict[str, set[tuple[str, str]]] = {
    # Bovada loses the flop and the turn of a board run out after an all-in:
    # with no action between the street markers, only the river is kept.
    "bovada/zone_poker.txt": {("readCommunityCards", "board.RIVER")},
    "regression/Bovada/Flop/LHE-2max-USD - $30-$60 - 201301.HU.all.in.big.txt": {("readCommunityCards", "board.RIVER")},
    "regression/Bovada/Flop/NLHE-6max-USD - $0.10-$0.25 - 202104.ZonePoker.txt": {
        ("readCommunityCards", "board.RIVER")
    },
    "regression/Bovada/Flop/NLHE-USD-0.10-0.25-201209.RING - $0.10-$0.25 - .post.both.txt": {
        ("readCommunityCards", "board.RIVER")
    },
    "regression/Bovada/Flop/PLO8-9max-USD-0.02-0.05-201408.corrupted.lines.txt": {
        ("readCommunityCards", "board.RIVER")
    },
    # Bovada's old format: a raise read as a negative "raise by".
    "regression/Bovada/Flop/LHE-USD-8-16-201204.old.format.txt": {("readAction", "actions.PREFLOP")},
    # A corrupted Merge export through PokerTracker: a negative raise as well.
    "regression/PokerTracker/Flop/NLHE-6max-USD-0.02-0.04-201412.Merge.weird.allin.sb.corrupted.txt": {
        ("readAction", "actions.PREFLOP")
    },
    # Courchevel deals the first flop card with the hole cards; the converter
    # keeps only the two dealt on the flop.
    "regression/FTP/Flop/PL-Courchevel-6max-play-25-50-201305.txt": {("readCommunityCards", "board.FLOP")},
    # The turn of an iPoker archive read through PokerTracker repeats the flop.
    "regression/PokerTracker/Flop/PLO-2max-USD-50.00-100.00-201308.iPoker.archive.txt": {
        ("readCommunityCards", "board.TURN")
    },
}


def _hand(**overrides):
    """A small, valid hold'em hand; ``overrides`` replace its attributes."""
    values = {
        "handid": "1",
        "tablename": "Table",
        "startTime": datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        "tourNo": None,
        "gametype": dict(GAMETYPE),
        "players": [[1, "alice", "2.00", None, None], [2, "bob", "2.00", None, None]],
        "maxseats": 6,
        "buttonpos": 1,
        "actions": {
            "BLINDSANTES": [
                ("alice", "small blind", Decimal("0.01"), False),
                ("bob", "big blind", Decimal("0.02"), False),
            ],
            "PREFLOP": [("alice", "calls", Decimal("0.01"), False), ("bob", "checks")],
            "FLOP": [("alice", "bets", Decimal("0.04"), False), ("bob", "folds")],
        },
        "actionStreets": ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
        "streets": {"PREFLOP": "x", "FLOP": "x", "TURN": "", "RIVER": ""},
        "allStreets": ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
        "board": {"FLOP": ["2c", "3d", "4h"], "TURN": [], "RIVER": []},
        "holecards": {"PREFLOP": {"alice": [[], ["As", "Ks"]]}},
        "collectees": {"alice": Decimal("0.04")},
        "totalpot": Decimal("0.08"),
        "totalcollected": Decimal("0.04"),
        "rake": Decimal("0.04"),
        "shown": set(),
        "folded": {"bob"},
        "stacks": {"alice": Decimal("1.94"), "bob": Decimal("1.98")},
        "hero": "alice",
        "handText": "",
        "cancelled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _errors(hand) -> set[tuple[str, str]]:
    return {(violation.step, violation.field) for violation in check_hand(hand) if violation.severity == "error"}


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def test_a_valid_hand_meets_the_contract() -> None:
    assert check_hand(_hand(), [["ring", "hold", "nl"]]) == []


def test_every_contract_step_is_a_converter_step() -> None:
    """Each step is declared by the generic converter or called on it by Hand."""
    from pathlib import Path

    from fpdb_3_legacy import Hand
    from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter

    hand_source = Path(Hand.__file__).read_text(encoding="utf-8")
    for step in parser_contract.STEP_NAMES:
        declared = callable(getattr(HandHistoryConverter, step, None))
        assert declared or f"hhc.{step}(" in hand_source, step


def test_categories_are_the_games_fpdb_can_evaluate() -> None:
    from fpdb_3_legacy import Card

    assert set(Card.games) == parser_contract.CATEGORIES


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"type": None}, "gametype.type"),
        ({"type": "cash"}, "gametype.type"),
        ({"limitType": "xl"}, "gametype.limitType"),
        ({"base": "flop"}, "gametype.base"),
        ({"category": "soko"}, "gametype.category"),
        ({"base": "stud"}, "gametype.base"),
        ({"bb": "two"}, "gametype.bb"),
    ],
)
def test_determine_game_type_contract(change, field) -> None:
    gametype = {**GAMETYPE, **change}

    assert field in {violation.field for violation in check_gametype(gametype)}


def test_no_game_type_breaks_the_contract() -> None:
    assert [violation.field for violation in check_gametype(None)] == ["gametype"]


def test_a_game_the_converter_does_not_support_breaks_the_contract() -> None:
    violations = check_gametype(GAMETYPE, [["ring", "hold", "pl"]])

    assert [violation.found for violation in violations] == ["ring/hold/nl"]


def test_hand_info_contract() -> None:
    errors = _errors(_hand(handid="", tablename=None, startTime="2026-01-01"))

    assert {("readHandInfo", "handid"), ("readHandInfo", "tablename"), ("readHandInfo", "startTime")} <= errors


def test_a_tournament_hand_needs_its_tournament() -> None:
    hand = _hand(gametype={**GAMETYPE, "type": "tour"})

    assert ("readHandInfo", "tourNo") in _errors(hand)


def test_player_stacks_contract() -> None:
    hand = _hand(players=[[1, "alice", "2.00"], [1, "bob", "two"], [3, "alice", "1"]])

    errors = {(violation.field, violation.message) for violation in check_hand(hand) if violation.severity == "error"}
    assert ("players.seat", "Seat 1 is taken twice") in errors
    assert ("players.name", "Player 'alice' is seated twice") in errors
    assert ("players.stack", "Stack of 'bob' is not an amount") in errors


def test_one_player_is_not_a_hand() -> None:
    assert ("readPlayerStacks", "players") in _errors(_hand(players=[[1, "alice", "2.00"]]))


def test_an_unseated_player_cannot_act_or_collect() -> None:
    hand = _hand(
        actions={"BLINDSANTES": [], "PREFLOP": [("carol", "folds")]},
        collectees={"carol": Decimal("1")},
    )

    assert {("readAction", "actions.PREFLOP"), ("readCollectPot", "collectees")} <= _errors(hand)


def test_unknown_action_types_and_amounts_break_the_contract() -> None:
    hand = _hand(
        actions={
            "BLINDSANTES": [("alice", "posts dead", Decimal(1), False)],
            "PREFLOP": [("bob", "calls", Decimal(-1), False)],
        }
    )

    messages = {violation.message for violation in check_hand(hand) if violation.severity == "error"}
    assert "Unknown action type 'posts dead'" in messages
    assert "'bob' calls a non-amount" in messages


@pytest.mark.parametrize(
    ("board", "field"),
    [
        ({"FLOP": ["2c", "3d"], "TURN": [], "RIVER": []}, "board.FLOP"),
        ({"FLOP": ["2c", "3d", "4h"], "TURN": ["5s", "6s"], "RIVER": []}, "board.TURN"),
        ({"FLOP": [], "TURN": [], "RIVER": ["5s"]}, "board.RIVER"),
    ],
)
def test_board_contract(board, field) -> None:
    assert ("readCommunityCards", field) in _errors(_hand(board=board))


def test_too_many_hole_cards_break_the_contract_and_too_few_only_warn() -> None:
    too_many = _hand(holecards={"PREFLOP": {"alice": [[], ["As", "Ks", "Qs"]]}})
    too_few = _hand(holecards={"PREFLOP": {"alice": [[], ["As"]]}})

    assert ("readHoleCards", "holecards") in _errors(too_many)
    assert [violation.severity for violation in check_hand(too_few)] == ["warning"]


def test_placeholders_are_not_cards() -> None:
    hand = _hand(holecards={"PREFLOP": {"alice": [[], ["0x", "0x"]], "bob": [[], ["xx", "xx"]]}})

    assert check_hand(hand) == []


def test_a_walk_holds_no_betting_action_legitimately() -> None:
    walk = _hand(
        actions={
            "BLINDSANTES": [
                ("alice", "small blind", Decimal("0.01"), False),
                ("bob", "big blind", Decimal("0.02"), False),
            ]
        },
        board={},
        collectees={"bob": Decimal("0.03")},
    )

    assert "no betting actions" not in completeness_issues(walk)
    assert not [violation for violation in check_hand(walk) if violation.field == "actions"]


def test_completeness_keeps_the_import_wording() -> None:
    hand = _hand(handid="", players=[], actions={}, handText="*** Flop ***", board={"FLOP": []}, collectees={})

    assert completeness_issues(hand) == [
        "missing required handid",
        "fewer than two players",
        "no blind/ante actions",
        "no betting actions",
        "flop marker present but board cards missing",
    ]


# ---------------------------------------------------------------------------
# Whole-hand invariants
# ---------------------------------------------------------------------------


def _check(hand, name):
    return next(check for check in hand_invariants(hand) if check.name == name)


def test_a_coherent_hand_passes_every_check() -> None:
    assert {check.status for check in hand_invariants(_hand())} == {"pass"}


def test_chip_conservation() -> None:
    assert _check(_hand(totalpot=Decimal("1.00")), "chip conservation").status == "fail"
    assert _check(_hand(rake=Decimal("-0.01"), totalpot=Decimal("0.03")), "chip conservation").status == "fail"


def test_a_card_dealt_twice_fails() -> None:
    hand = _hand(board={"FLOP": ["As", "3d", "4h"], "TURN": [], "RIVER": []})

    assert _check(hand, "no duplicated card").details == ["As"]


def test_run_it_twice_boards_are_not_duplicates() -> None:
    hand = _hand(board={"FLOP": ["2c", "3d", "4h"], "TURN": [], "RIVER": [], "FLOP1": ["2c", "3d", "4h"]})

    assert _check(hand, "no duplicated card").status == "pass"


def test_acting_after_a_fold_and_overbetting_warn() -> None:
    hand = _hand(
        players=[[1, "alice", "0.10"], [2, "bob", "2.00"]],
        actions={
            "PREFLOP": [
                ("alice", "bets", Decimal("0.11"), False),
                ("bob", "folds"),
                ("bob", "calls", Decimal(1), False),
            ]
        },
    )

    details = _check(hand, "betting order").details
    assert any("commits 0.11 with only 0.10 remaining" in detail for detail in details)
    assert any("after folding" in detail for detail in details)


def test_a_short_raise_warns_unless_it_is_all_in() -> None:
    hand = _hand(
        actions={
            "BLINDSANTES": [
                ("alice", "small blind", Decimal("0.01"), False),
                ("bob", "big blind", Decimal("0.02"), False),
            ],
            "PREFLOP": [("alice", "raises", Decimal("0.01"), Decimal("0.03"), Decimal("0.01"), False)],
        }
    )

    assert any("less than the previous bet" in detail for detail in _check(hand, "betting order").details)


def test_a_player_cannot_act_after_going_all_in() -> None:
    hand = _hand(
        players=[[1, "alice", "0.10"], [2, "bob", "2.00"]],
        actions={
            "BLINDSANTES": [],
            "PREFLOP": [
                ("alice", "bets", Decimal("0.10"), True),
                ("bob", "calls", Decimal("0.10"), False),
                ("alice", "checks"),
            ],
        },
    )

    assert any("after going all-in" in detail for detail in _check(hand, "betting order").details)


def test_a_folded_player_collecting_warns_unless_for_nothing() -> None:
    assert _check(_hand(collectees={"bob": Decimal(1)}), "winners").status == "warn"
    assert _check(_hand(collectees={"alice": Decimal("0.04"), "bob": Decimal(0)}), "winners").status == "pass"


# ---------------------------------------------------------------------------
# Every converter, over the regression corpus
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus_config() -> Config:
    return Config(file="HUD_config.xml")


@pytest.mark.parametrize(("key", "parser_class", "hand_file"), CASES, ids=[case[0] for case in CASES])
def test_every_converter_meets_the_contract(key, parser_class, hand_file, corpus_config) -> None:
    logging.disable(logging.CRITICAL)
    try:
        parser = parser_class(config=corpus_config, in_path=str(hand_file), autostart=True)
    finally:
        logging.disable(logging.NOTSET)
    supported = parser.readSupportedGames()
    found = {
        (violation.step, violation.field): violation
        for hand in parser.getProcessedHands()
        for violation in parser_contract.contract_errors(hand, supported)
    }

    expected = KNOWN_CONTRACT_DEBT.get(key, set())
    assert set(found) == expected, (
        "\n".join(
            f"{step} {field}: {violation.message} (found {violation.found})"
            for (step, field), violation in sorted(found.items())
            if (step, field) not in expected
        )
        or f"fixed, remove from KNOWN_CONTRACT_DEBT: {sorted(expected - set(found))}"
    )


def test_every_known_debt_is_still_a_fixture() -> None:
    assert set(KNOWN_CONTRACT_DEBT) <= {key for key, _, _ in CASES}
