"""The replayer summary's decision metrics, from real TableState steps (#826)."""

from __future__ import annotations

import copy
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from fpdb_3_legacy.GuiReplayer import GuiReplayer, ReplayPlayer, TableState, format_spr

D = Decimal


def _hand(stacks: dict[str, str]) -> Any:
    """Enough of a parsed hold'em hand to build TableStates."""
    return SimpleNamespace(
        board={},
        maxseats=len(stacks),
        gametype={"category": "holdem", "base": "hold", "type": "ring"},
        actionStreets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
        players=[[seat, name, stack] for seat, (name, stack) in enumerate(stacks.items(), start=1)],
        join_holecards=lambda *_args, **_kwargs: [],
    )


def _states(hand: Any, streets: list[tuple[str, list[tuple]]]) -> list[Any]:
    """The replay steps the replayer builds: a phase start, then one per action."""
    state = TableState(hand)
    states = []
    for street, actions in streets:
        state = copy.deepcopy(state)
        state.startPhase(street)
        states.append(state)
        for action in actions:
            state = copy.deepcopy(state)
            state.updateForAction(action)
            states.append(state)
    return states


def _replayer(hand: Any, states: list[Any], *, all_players: bool = False) -> Any:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    replayer.states = states
    replayer.replay_model = SimpleNamespace(hand=hand)
    replayer.all_decisions = SimpleNamespace(isChecked=lambda: all_players)
    return replayer


PREFLOP = (
    "PREFLOP",
    [
        ("Villain", "small blind", D("0.5")),
        ("Hero", "big blind", D(1)),
        ("Villain", "calls", D("0.5")),
        ("Hero", "checks"),
    ],
)


def _heads_up() -> tuple[Any, list[Any]]:
    # Index: 0-4 preflop, 5 flop, 6 hero bets 1 into 2, 7 call, 8 turn,
    # 9 hero checks, 10 villain bets 3 into 4, 11 hero calls.
    hand = _hand({"Hero": "100", "Villain": "100"})
    return hand, _states(
        hand,
        [
            PREFLOP,
            ("FLOP", [("Hero", "bets", D(1)), ("Villain", "calls", D(1))]),
            ("TURN", [("Hero", "checks"), ("Villain", "bets", D(3)), ("Hero", "calls", D(3))]),
        ],
    )


def test_hero_bet_shows_sizing_and_heads_up_mdf_and_fold_equity() -> None:
    hand, states = _heads_up()

    lines = _replayer(hand, states)._decision_lines(6)

    assert lines == [
        "Hero bets 50% of the pot · MDF 66.7% · fold equity needed 33.3% (heads-up)",
        "Hero SPR 49.5",
    ]


def test_hero_facing_a_bet_shows_its_sizing_and_the_street_spr() -> None:
    hand, states = _heads_up()

    # The villain's bet is not the hero's: only the decision it puts to the hero.
    assert _replayer(hand, states)._decision_lines(10) == ["Hero to call $3.00 · facing 75% of the pot · SPR 24.5"]


def test_all_players_toggle_prices_the_opponents_decisions() -> None:
    hand, states = _heads_up()
    replayer = _replayer(hand, states, all_players=True)

    assert replayer._decision_lines(6) == [
        "Hero bets 50% of the pot · MDF 66.7% · fold equity needed 33.3% (heads-up)",
        "Villain to call $1.00 · pot odds 25.0% · facing 50% of the pot · SPR 49.5",
    ]
    assert replayer._decision_lines(10)[0] == (
        "Villain bets 75% of the pot · MDF 57.1% · fold equity needed 42.9% (heads-up)"
    )


def test_spr_is_hidden_preflop_and_the_result_has_no_decision() -> None:
    hand, states = _heads_up()
    replayer = _replayer(hand, states)

    # Preflop the hero only checks: no call to price, and no SPR against the blinds.
    assert not replayer._decision_lines(3)
    assert replayer._decision_lines(5) == ["Hero to act · SPR 49.5"]
    ended = copy.deepcopy(states[-1])
    ended.endHand({"Hero": D(10)}, {})
    replayer.states = [*states, ended]
    assert not replayer._decision_lines(len(states))


def test_multiway_bet_shows_spr_per_opponent_and_no_mdf() -> None:
    hand = _hand({"Hero": "100", "Short": "21", "Deep": "100"})
    states = _states(
        hand,
        [
            (
                "PREFLOP",
                [
                    ("Short", "small blind", D("0.5")),
                    ("Deep", "big blind", D(1)),
                    ("Hero", "calls", D(1)),
                    ("Short", "calls", D("0.5")),
                    ("Deep", "checks"),
                ],
            ),
            ("FLOP", [("Hero", "bets", D(3))]),
        ],
    )

    lines = _replayer(hand, states)._decision_lines(len(states) - 1)

    # Flop pot 3: Short has 20 behind (SPR 6.67), Deep and the hero 99 (33).
    assert lines == [
        "Hero bets 100% of the pot · MDF / fold equity: heads-up only",
        "Hero SPR 6.67–33",
    ]


def test_hero_call_against_a_covering_bet_is_capped_at_the_hero_stack(monkeypatch) -> None:
    monkeypatch.setattr("fpdb_3_legacy.GuiReplayer.replay_hero_equity", lambda *_args, **_kwargs: None)
    hand = _hand({"Hero": "10", "Villain": "100"})
    flop = ("FLOP", [("Hero", "checks"), ("Villain", "bets", D(50)), ("Hero", "calls", D(9))])
    states = _states(hand, [PREFLOP, flop])
    replayer = _replayer(hand, states)
    bet = len(states) - 2
    state = states[bet]
    frame = cast(
        Any,
        SimpleNamespace(
            players=[
                ReplayPlayer(p.name, p.seat, p.stack, p.chips, p.action, p.justacted, [], p.allin)
                for p in state.players.values()
            ],
            pot=state.newpot,
            board={},
            render_board=set(),
            street="FLOP",
        ),
    )

    metrics = replayer._hero_decision_metrics(frame, bet)

    # Hero calls 9 to win the 2 in the pot and the 9 of the bet it matches.
    assert metrics["call_amount"] == D(9)
    assert metrics["pot_odds_pct"] == D(45)
    assert metrics["pot_odds_ratio"] == D(55) / D(45)
    assert replayer._decision_lines(bet) == ["Hero to call $9.00 · facing 2,500% of the pot · SPR 4.5"]


def test_tournament_antes_are_in_the_street_pot() -> None:
    hand = _hand({"Hero": "1000", "Villain": "1000"})
    hand.gametype["type"] = "tour"
    states = _states(
        hand,
        [
            ("BLINDSANTES", [("Hero", "ante", D(10)), ("Villain", "ante", D(10))]),
            (
                "PREFLOP",
                [
                    ("Villain", "small blind", D(15)),
                    ("Hero", "big blind", D(30)),
                    ("Villain", "calls", D(15)),
                    ("Hero", "checks"),
                ],
            ),
            ("FLOP", [("Hero", "checks"), ("Villain", "bets", D(40)), ("Hero", "calls", D(40))]),
        ],
    )

    # Flop pot 80 (antes and blinds), 960 behind each: SPR 12; the 40 bet is half of it.
    replayer = _replayer(hand, states)
    replayer.currency_code = "T$"
    assert replayer._decision_lines(len(states) - 2) == ["Hero to call 40.00 · facing 50% of the pot · SPR 12"]


@pytest.mark.parametrize(
    ("values", "text"),
    [
        ((), ""),
        ((D("4.5"),), "4.5"),
        ((D(2), D(2)), "2"),
        ((D(1), D("1.5")), "1–1.5"),
        # An all-in matchup has no SPR left.
        ((D(0), D("0.32")), "0.32"),
        ((D(0),), ""),
    ],
)
def test_format_spr(values, text) -> None:
    assert format_spr(values) == text


def test_facing_bet_sizing_comes_from_the_bettor_not_an_earlier_seated_caller() -> None:
    # "Caller" is listed before "Bettor" and both hold 3 when the hero acts:
    # the sizing is still the bettor's 3 into 3 (Codex on #839).
    hand = _hand({"Caller": "100", "Bettor": "100", "Hero": "100"})
    states = _states(
        hand,
        [
            (
                "PREFLOP",
                [
                    ("Caller", "small blind", D("0.5")),
                    ("Bettor", "big blind", D(1)),
                    ("Hero", "calls", D(1)),
                    ("Caller", "calls", D("0.5")),
                    ("Bettor", "checks"),
                ],
            ),
            ("FLOP", [("Bettor", "bets", D(3)), ("Caller", "calls", D(3)), ("Hero", "calls", D(3))]),
        ],
    )

    # The step after the caller's call: the hero faces 3 into 6.
    lines = _replayer(hand, states)._decision_lines(len(states) - 2)

    assert lines == ["Hero to call $3.00 · facing 100% of the pot · SPR 33"]


def test_hero_with_chips_behind_wins_every_ante_and_bet() -> None:
    # Codex on #839: only Villain posts a 1 ante; a call of 1 that is not all-in
    # wins the whole 5, so it needs 20 %, not the 25 % a side-pot cap would give.
    hand = _hand({"Hero": "100", "Villain": "100"})
    states = _states(
        hand,
        [
            ("BLINDSANTES", [("Villain", "ante", D(1))]),
            ("PREFLOP", [("Villain", "small blind", D(1)), ("Hero", "big blind", D(1)), ("Villain", "checks")]),
            ("FLOP", [("Hero", "checks"), ("Villain", "bets", D(1)), ("Hero", "calls", D(1))]),
        ],
    )
    replayer = _replayer(hand, states)

    assert replayer._capped_hero_call(len(states) - 2) == (D(1), D(20), D(4))


def test_all_in_call_counts_the_whole_ante_as_dead_money() -> None:
    # Hero calls 2 all-in. Villain's betting counts up to the hero's 3, and its
    # 1 ante (a big-blind ante) stays whole: 2 / (3 + 3 + 1).
    hand = _hand({"Hero": "3", "Villain": "100"})
    states = _states(
        hand,
        [
            ("BLINDSANTES", [("Villain", "ante", D(1))]),
            ("PREFLOP", [("Villain", "small blind", D(1)), ("Hero", "big blind", D(1)), ("Villain", "checks")]),
            ("FLOP", [("Hero", "checks"), ("Villain", "bets", D(10)), ("Hero", "calls", D(2))]),
        ],
    )

    amount, odds, _ratio = _replayer(hand, states)._capped_hero_call(len(states) - 2)

    assert amount == D(2)
    assert odds == D(2) / D(7) * 100
