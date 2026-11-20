"""The replayer summary's decision metrics, from real TableState steps (#826)."""

from __future__ import annotations

import copy
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from fpdb_3_legacy.GuiReplayer import GuiReplayer, ReplayPlayer, TableState, format_spr
from fpdb_3_legacy.replayer_decision import hero_decision
from fpdb_3_legacy.replayer_panel import PanelSection

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


def _frame(state: Any) -> Any:
    """The replay frame of a step: its players as the summary sees them."""
    return cast(
        Any,
        SimpleNamespace(
            players=[
                ReplayPlayer(p.name, p.seat, p.stack, p.chips, p.action, p.justacted, [], p.allin)
                for p in state.players.values()
            ],
            pot=state.newpot,
            board={},
            render_board=set(),
            street=state.street,
        ),
    )


def _sections(replayer: Any, index: int, *, detailed: bool = False) -> list[tuple[str, list[tuple[str, str]]]]:
    """The decision sections at a step, as (title, [(label, value)]) -- notes have an empty value."""
    sections: list[PanelSection] = replayer._decision_sections(_frame(replayer.states[index]), index)
    shown = (section.visible(detailed) for section in sections)
    return [(s.title, [(row.label, row.value) for row in s.rows]) for s in shown if s is not None]


def _replayer(hand: Any, states: list[Any], *, all_players: bool = False) -> Any:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    replayer.states = states
    replayer.replay_model = SimpleNamespace(hand=hand)
    replayer.all_decisions = SimpleNamespace(isChecked=lambda: all_players)
    replayer.hand_icm = replayer.hand_bounty = None
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
    replayer = _replayer(hand, states)

    # Compact: the bet's size and the hero's SPR; MDF and fold equity are in the detail.
    assert _sections(replayer, 6) == [
        ("Hero bets", [("Bet size", "50% of the pot")]),
        ("Hero", [("SPR", "49.5")]),
    ]
    assert _sections(replayer, 6, detailed=True)[0] == (
        "Hero bets",
        [
            ("Bet size", "50% of the pot"),
            ("MDF (heads-up)", "66.7%"),
            ("Fold equity needed (heads-up)", "33.3%"),
            ("Simplified model: one opponent, a bluff that never wins when called.", ""),
        ],
    )


def test_hero_facing_a_bet_shows_the_call_its_pot_odds_and_the_street_spr(monkeypatch) -> None:
    monkeypatch.setattr("fpdb_3_legacy.GuiReplayer.replay_hero_estimate", lambda *_args, **_kwargs: None)
    hand, states = _heads_up()
    replayer = _replayer(hand, states)

    # The villain's bet is not the hero's: only the decision it puts to the hero, 3 into 4.
    assert _sections(replayer, 10) == [
        (
            "Hero to call",
            [
                ("Call amount", "$3.00"),
                ("Effective pot after call", "$10.00"),
                ("Required equity", "30.0%"),
                ("SPR", "24.5"),
            ],
        )
    ]
    title, rows = _sections(replayer, 10, detailed=True)[0]
    assert ("Pot odds", "2.3:1") in rows
    assert ("Facing", "75% of the pot") in rows
    assert ("Pot on the table", "$7.00") in rows
    # Nothing on the table is out of the call's reach: no breakdown of it.
    assert not any(label == "Uncalled or side money" for label, _value in rows)


def test_all_players_toggle_prices_the_opponents_decisions() -> None:
    hand, states = _heads_up()
    replayer = _replayer(hand, states, all_players=True)

    assert _sections(replayer, 6) == [
        ("Hero bets", [("Bet size", "50% of the pot")]),
        (
            "Villain to call",
            [
                ("Call amount", "$1.00"),
                ("Effective pot after call", "$4.00"),
                ("Required equity", "25.0%"),
                ("SPR", "49.5"),
            ],
        ),
    ]
    assert _sections(replayer, 10, detailed=True)[0][0] == "Villain bets"
    assert ("MDF (heads-up)", "57.1%") in _sections(replayer, 10, detailed=True)[0][1]


def test_spr_is_hidden_preflop_and_the_result_has_no_decision() -> None:
    hand, states = _heads_up()
    replayer = _replayer(hand, states)

    # Preflop the hero only checks: no call to price, and no SPR against the blinds.
    assert not _sections(replayer, 3)
    assert _sections(replayer, 5) == [("Hero to act", [("SPR", "49.5")])]
    ended = copy.deepcopy(states[-1])
    ended.endHand({"Hero": D(10)}, {})
    replayer.states = [*states, ended]
    assert not _sections(replayer, len(states))


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

    # Flop pot 3: Short has 20 behind (SPR 6.67), Deep and the hero 99 (33).
    assert _sections(_replayer(hand, states), len(states) - 1, detailed=True) == [
        ("Hero bets", [("Bet size", "100% of the pot"), ("MDF and fold equity: heads-up only.", "")]),
        ("Hero", [("SPR", "6.67–33")]),
    ]


def test_hero_call_against_a_covering_bet_is_capped_at_the_hero_stack(monkeypatch) -> None:
    monkeypatch.setattr("fpdb_3_legacy.GuiReplayer.replay_hero_estimate", lambda *_args, **_kwargs: None)
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
    # The villain's 50 is shown, but 41 of it goes back uncalled: the call wins 9 + 9 + 2.
    title, rows = _sections(replayer, bet, detailed=True)[0]
    assert title == "Hero to call"
    assert rows[:3] == [("Call amount", "$9.00"), ("Effective pot after call", "$20.00"), ("Required equity", "45.0%")]
    assert ("Facing", "2,500% of the pot") in rows
    assert ("Pot on the table", "$52.00") in rows
    assert ("Uncalled or side money", "$41.00") in rows
    assert ("Effective pot before call", "$11.00") in rows
    assert ("SPR", "4.5") in rows


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
    title, rows = _sections(replayer, len(states) - 2)[0]
    # A tournament call is priced in chips: chip equity, never an ICM threshold.
    assert title == "Hero to call"
    assert rows == [
        ("Call amount", "40.00"),
        ("Effective pot after call", "160.00"),
        ("Required chip equity", "25.0%"),
        ("SPR", "12"),
    ]
    detail = _sections(replayer, len(states) - 2, detailed=True)[0][1]
    assert ("Chip pot odds: not an ICM threshold.", "") in detail


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
    rows = _sections(_replayer(hand, states), len(states) - 2, detailed=True)[0][1]

    assert ("Facing", "100% of the pot") in rows
    assert ("SPR", "33") in rows


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


def test_room_splash_counts_in_the_pot_the_decision_is_priced_against() -> None:
    """A Winamax/BetRivers splash is in the pot without coming out of any stack (#843).

    2 from the blinds and a 20 splash, then a 5 bet: the call is 5 into 32, not
    5 into 12 as summing the players' contributions alone made it.
    """
    hand = _hand({"Hero": "100", "Villain": "100"})
    hand.pot = SimpleNamespace(stp=D(20))
    states = _states(hand, [PREFLOP, ("FLOP", [("Hero", "checks"), ("Villain", "bets", D(5))])])

    flop_start, facing = hero_decision(states, 5, "Hero"), hero_decision(states, 7, "Hero")

    assert flop_start.street_pot == D(22)
    assert facing.mode == "call"
    assert facing.pot_odds_pct == D(5) / D(32) * 100
    assert facing.bet_pct == D(5) / D(22) * 100


def test_room_splash_is_dead_money_an_all_in_caller_still_contests() -> None:
    hand = _hand({"Hero": "10", "Villain": "100"})
    hand.pot = SimpleNamespace(stp=D(20))
    states = _states(hand, [PREFLOP, ("FLOP", [("Hero", "checks"), ("Villain", "bets", D(50))])])

    # Hero can win 9 from the villain's bet, the 2 of blinds and the 20 splash.
    assert hero_decision(states, 7, "Hero").pot_odds_pct == D(9) / D(2 + 20 + 9 + 9) * 100


def test_cap_table_effective_stack_stops_at_the_unused_cap() -> None:
    """Both players reach a $30 cap preflop: chips behind cannot be bet, SPR is 0 (#843).

    The stacks are those of tests/fixtures/hands/winning/plo8_cap_2026.txt.
    """
    hand = _hand({"Hero": "41.20", "Villain": "38.40"})
    hand.gametype["buyinType"] = "cap"
    hand.capAmount = D(30)
    states = _states(
        hand,
        [
            (
                "PREFLOP",
                [
                    ("Villain", "small blind", D("0.5")),
                    ("Hero", "big blind", D(1)),
                    ("Villain", "raises", D(29)),
                    ("Hero", "calls", D(29)),
                ],
            ),
            ("FLOP", [("Hero", "checks")]),
        ],
    )

    flop = hero_decision(states, 5, "Hero")

    assert flop.street_pot == D(60)
    assert flop.effective == (("Villain", D(0)),)
    assert flop.spr == (D(0),)


def test_cap_table_below_the_cap_keeps_what_is_left_of_it() -> None:
    hand = _hand({"Hero": "41.20", "Villain": "38.40"})
    hand.gametype["buyinType"] = "cap"
    hand.capAmount = D(30)
    states = _states(hand, [PREFLOP, ("FLOP", [("Hero", "checks")])])

    # 1 in each, 29 of the cap left, though both have more than that behind.
    assert hero_decision(states, 5, "Hero").effective == (("Villain", D(29)),)
