"""The replayer's action history (#825): entries, the state each one seeks, and the row kept selected."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.replay_history import (
    ACTION,
    ACTION_ICONS,
    ACTION_STYLES,
    DEFAULT_ACTION_STYLE,
    END,
    PHASE,
    RESULT,
    action_icon,
    action_style,
    format_history_amount,
    history_row_for_index,
    phase_label,
    replay_history_entries,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hands" / "pokerstars"
RUN_IT_TWICE = (
    Path(__file__).resolve().parents[1]
    / "regression-test-files/cash/GGPoker/Flop/PLO-7max-USD-0.02-0.05-202601.run.it.twice.first.streets.txt"
)


def player(name, stack, chips=0, action=None, justacted=False, allin=False, **extra):
    return SimpleNamespace(
        name=name,
        stack=Decimal(str(stack)),
        chips=Decimal(str(chips)),
        action=action,
        justacted=justacted,
        allin=allin,
        **extra,
    )


def state(street, *players, ended=False, board=None, render=()):
    return SimpleNamespace(
        street=street,
        players={p.name: p for p in players},
        ended=ended,
        board=board or {},
        renderBoard=set(render),
    )


def texts(entries):
    return [entry.text for entry in entries]


# --- Built from the replayer's own states ------------------------------------------------------


def replay_states(hand):
    from fpdb_3_legacy.GuiReplayer import GuiReplayer

    replayer = GuiReplayer.__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer._format_hand_info = lambda _hand: ""
    return GuiReplayer._build_replay_model(replayer, hand).states


def parsed(legacy_config, relative):
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    return PokerStars(config=legacy_config, in_path=str(FIXTURES / relative), autostart=True).getProcessedHands()[0]


def test_holdem_phases_calls_and_raises_to(legacy_config):
    states = replay_states(parsed(legacy_config, "holdem/cash_nl_6max.txt"))

    entries = replay_history_entries(states, "USD")

    assert texts(entries) == [
        "Blinds and antes",
        "Player2: posts small blind $0.50",
        "Player3: posts big blind $1.00",
        "Preflop",
        "Player4: folds",
        "Player5: folds",
        "Player6: folds",
        # A shown hand appears as its cards, not as the amount; the amount stays on the entry.
        "Player1: raises [Ah Kh]",
        # The small blind adds $2.50 to complete the raise, not "$3.00" (entry.amount).
        "Player2: calls [2s 2c]",
        "Player3: folds",
        "Flop dealt: As Ks 2d",
        "Player2: checks",
        "Player1: bets [Ah Kh]",
        "Player2: calls [2s 2c]",
        "Turn dealt: Td",
        "Player2: checks",
        "Player1: bets [Ah Kh]",
        "Player2: raises [2s 2c]",
        "Player1: calls [Ah Kh]",
        "River dealt: Qh",
        "Player2: bets [2s 2c]",
        "Player1: calls [Ah Kh]",
        "Hand complete",
        "Player2: collected $95.00",
    ]
    # The amounts are still on the entries, in order: the raise is to $3.00, the call adds $2.50.
    by_action = [(entry.player, entry.action, entry.amount) for entry in entries if entry.action in {"raises", "calls"}]
    assert by_action[0] == ("Player1", "raises", Decimal("3.00"))
    assert by_action[1] == ("Player2", "calls", Decimal("2.50"))
    # Every entry but the winners seeks to a state of its own, in order.
    assert [entry.index for entry in entries] == [*range(len(states)), len(states) - 1]
    assert entries[-2].kind == END and entries[-1].kind == RESULT


def test_amounts_in_big_blinds(legacy_config):
    states = replay_states(parsed(legacy_config, "holdem/cash_nl_6max.txt"))

    entries = replay_history_entries(states, "USD", blind=Decimal(1))

    # Shown hands appear as their cards; posts and the collected amount keep the BB figure.
    assert "Player1: raises [Ah Kh]" in texts(entries)
    assert "Player2: calls [2s 2c]" in texts(entries)
    assert "Player2: posts small blind 0.5 BB" in texts(entries)
    assert texts(entries)[-1] == "Player2: collected 95 BB"
    assert not any("$" in text for text in texts(entries))
    # The action amounts are still there, in big blinds' units.
    amounts = [(entry.action, entry.amount) for entry in entries if entry.action in {"raises", "calls"}]
    assert amounts[0] == ("raises", Decimal("3.00")) and amounts[1] == ("calls", Decimal("2.50"))


def test_all_in_raise_and_call(legacy_config):
    states = replay_states(parsed(legacy_config, "holdem/run_it_twice.txt"))

    entries = replay_history_entries(states, "USD")

    assert "Player2: raises to $400.00 (all-in)" in texts(entries)  # Player2's cards are not shown
    assert "Player1: calls [As Ks Qs Js] (all-in)" in texts(entries)
    allin = [entry for entry in entries if entry.allin]
    assert [(entry.player, entry.action, entry.amount) for entry in allin] == [
        ("Player2", "raises", Decimal(400)),
        ("Player1", "calls", Decimal(388)),
    ]


def test_triple_draw_streets_and_discards(legacy_config):
    states = replay_states(parsed(legacy_config, "draw/triple_draw.txt"))

    entries = replay_history_entries(states, "USD")
    phases = [entry.text for entry in entries if entry.kind == PHASE]

    assert phases == ["Blinds and antes", "Cards dealt", "First draw", "Second draw", "Third draw"]
    assert "rumble1111: discards 2" in texts(entries)
    assert "bakter9: stands pat" in texts(entries)
    assert "bakter9: calls $0.18 (all-in)" in texts(entries)


def test_stud_streets_antes_and_bring_in(legacy_config):
    states = replay_states(parsed(legacy_config, "stud/7stud.txt"))

    entries = replay_history_entries(states, "USD")
    phases = [entry.text for entry in entries if entry.kind == PHASE]

    assert phases == [
        "Blinds and antes",
        "Third street",
        "Fourth street",
        "Fifth street",
        "Sixth street",
        "Seventh street",
    ]
    assert "Player1: posts ante $0.10" in texts(entries)
    assert "Player1: brings in $0.25" in texts(entries)
    assert "Player2: calls [3d]" in texts(entries)  # the up card dealt so far, not the amount


def test_run_it_twice_lists_each_run(legacy_config):
    from fpdb_3_legacy.GGPokerToFpdb import GGPoker

    hands = GGPoker(config=legacy_config, in_path=str(RUN_IT_TWICE), autostart=True).getProcessedHands()
    hand = next(h for h in hands if str(h.handid) == "537421857")
    states = replay_states(hand)

    entries = replay_history_entries(states, "USD")
    phases = [entry for entry in entries if entry.kind == PHASE]

    assert [entry.text for entry in phases if "run" in entry.text] == [
        "Flop dealt (run 1): Qd 7s 9h",
        "Turn dealt (run 1): 4d",
        "River dealt (run 1): Ac",
        # The second run shares the flop and the turn; only its river is new.
        "Flop dealt (run 2)",
        "Turn dealt (run 2)",
        "River dealt (run 2): 3h",
    ]
    assert "Hero: bets [As Jc Ts 9d] (all-in)" in texts(entries)
    # A player whose cards are not shown keeps the amount.
    assert "a0000001: calls $0.05" in texts(entries)
    # Each street seeks to the state that deals it.
    for entry in phases:
        assert entry.text.startswith(phase_label(states[entry.index].street))


# --- Synthetic states --------------------------------------------------------------------------


def test_a_double_board_bomb_pot_lists_both_flops():
    flop = state(
        "FLOP",
        player("A", 90),
        board={"FLOP1": ["2h", "3h", "4h"], "FLOP2": ["Ks", "Kd", "7c"]},
        render={"FLOP1", "FLOP2"},
    )
    entries = replay_history_entries([state("BLINDSANTES", player("A", 100)), flop], "USD")

    assert entries[-1].text == "Flop dealt: 2h 3h 4h | Ks Kd 7c"


def test_chips_are_numbers_not_money():
    states = [
        state("PREFLOP", player("A", 1500), player("B", 1500)),
        state("PREFLOP", player("A", 1200, chips=300, action="raises", justacted=True), player("B", 1500)),
    ]

    assert texts(replay_history_entries(states, "T$"))[-1] == "A: raises to 300.00"


def test_a_raise_after_a_blind_is_read_to_the_total():
    states = [
        state("PREFLOP", player("SB", 99.5, chips=0.5), player("BB", 99, chips=1)),
        state("PREFLOP", player("SB", 96, chips=4, action="raises", justacted=True), player("BB", 99, chips=1)),
        state("PREFLOP", player("SB", 96, chips=4), player("BB", 96, chips=4, action="calls", justacted=True)),
    ]

    entries = replay_history_entries(states, "USD")

    assert texts(entries)[1:] == ["SB: raises to $4.00", "BB: calls $3.00"]
    assert entries[2].amount == Decimal(3)


def test_known_discards_show_the_cards():
    states = [
        state("DRAWONE", player("Hero", 10)),
        state(
            "DRAWONE",
            player("Hero", 10, action="discards 2", justacted=True, discardCards=["Kh", "Qd"]),
        ),
    ]

    assert texts(replay_history_entries(states, "USD"))[-1] == "Hero: discards 2 [Kh Qd]"


def test_an_unfinished_list_of_states_has_no_end():
    states = [state("PREFLOP", player("A", 100)), state("PREFLOP", player("A", 100, action="checks", justacted=True))]

    entries = replay_history_entries(states, "USD")

    assert [entry.kind for entry in entries] == [PHASE, ACTION]
    assert not replay_history_entries([], "USD")


def test_a_known_hand_shows_its_cards_instead_of_the_amount():
    states = [
        state("PREFLOP", player("A", 100), player("B", 100)),
        state(
            "PREFLOP",
            player("A", 99, chips=1, action="raises", justacted=True, holecards=["Ah", "Kh"]),
            player("B", 100),
        ),
        state("PREFLOP", player("A", 99, chips=1), player("B", 99, chips=1, action="calls", justacted=True)),
    ]

    entries = replay_history_entries(states, "USD")

    assert texts(entries)[-2] == "A: raises [Ah Kh]"  # the amount stays on the entry
    assert entries[-2].amount == Decimal(1)
    assert texts(entries)[-1] == "B: calls $1.00"  # B's cards are not shown: the amount stays


def test_cards_the_table_hides_stay_hidden_in_the_history():
    # "Hide Cards": a villain's hand known from the showdown is not given away by the history.
    states = [
        state("PREFLOP", player("Hero", 100), player("Villain", 100)),
        state(
            "PREFLOP",
            player("Hero", 100, holecards=["Qs", "Qd"]),
            player("Villain", 98, chips=2, action="raises", justacted=True, holecards=["Ah", "Kh"]),
        ),
        state(
            "PREFLOP",
            player("Hero", 98, chips=2, action="calls", justacted=True, holecards=["Qs", "Qd"]),
            player("Villain", 98, chips=2, holecards=["Ah", "Kh"]),
        ),
    ]

    hidden = replay_history_entries(states, "USD", shows_cards=lambda name: name == "Hero")
    shown = replay_history_entries(states, "USD", shows_cards=lambda _name: True)

    assert texts(hidden)[-2:] == ["Villain: raises to $2.00", "Hero: calls [Qs Qd]"]
    assert texts(shown)[-2] == "Villain: raises [Ah Kh]"


@pytest.mark.parametrize(
    ("street", "label"),
    [
        ("FLOP", "Flop dealt"),
        ("RIVER2", "River dealt (run 2)"),
        ("DRAWTHREE", "Third draw"),
        ("SEVENTH", "Seventh street"),
        (None, "Start of hand"),
        ("MYSTERY", "Mystery"),
    ],
)
def test_phase_labels(street, label):
    assert phase_label(street) == label


def test_amount_formats():
    assert format_history_amount(Decimal("2.50"), "USD") == "$2.50"
    assert format_history_amount(Decimal(1500), "play") == "1,500.00"
    assert format_history_amount(Decimal("2.50"), "USD", blind=Decimal(1)) == "2.5 BB"
    assert format_history_amount(Decimal(60), "T$", blind=Decimal(20)) == "3 BB"


def test_the_row_kept_selected_while_stepping():
    entries = replay_history_entries(
        [
            state("PREFLOP", player("A", 100), player("B", 100)),
            state("PREFLOP", player("A", 100, action="checks", justacted=True), player("B", 100)),
            state(
                "PREFLOP",
                player("A", 110, chips=10, action="collected", justacted=True),
                player("B", 110, chips=10, action="collected", justacted=True),
                ended=True,
            ),
        ],
        "USD",
    )

    assert texts(entries) == ["Preflop", "A: checks", "Hand complete", "A: collected $10.00", "B: collected $10.00"]
    assert history_row_for_index(entries, 0) == 0
    assert history_row_for_index(entries, 1) == 1
    # The end of the hand highlights "Hand complete", not the last winner.
    assert history_row_for_index(entries, 2) == 2
    assert history_row_for_index([], 3) is None
    # A state without an entry of its own keeps the latest one before it.
    assert history_row_for_index([entries[0], entries[2]], 1) == 0


# --- the colour grammar shared by the inspector's timeline and the history window -------------


def test_every_action_has_its_own_colour_pair_and_glyph():
    assert set(ACTION_STYLES) == {"folds", "checks", "calls", "bets", "raises", "collected"}
    assert set(ACTION_ICONS) == set(ACTION_STYLES)
    for action in ACTION_STYLES:
        style = action_style(action)
        assert style is ACTION_STYLES[action]
        assert style.foreground.startswith("#") and style.background.startswith("#")
        assert action_icon(action) == ACTION_ICONS[action]
    # Bets and raises are distinct, as are calls and checks: the timeline tells them apart.
    assert action_style("bets") != action_style("raises")
    assert action_style("calls") != action_style("checks")


def test_posts_phases_and_unknown_actions_use_the_default_style():
    for action in ("small blind", "ante", "bringin", "discards 2", "stands pat", "", None, "mystery"):
        assert action_style(action) is DEFAULT_ACTION_STYLE
        assert action_icon(action) == ""


def test_the_entries_carry_the_verb_the_colours_come_from():
    entries = replay_history_entries(
        [
            state("PREFLOP", player("A", 100)),
            state("PREFLOP", player("A", 99, chips=1, action="big blind", justacted=True)),
            state("PREFLOP", player("A", 97, chips=3, action="raises", justacted=True)),
            state("PREFLOP", player("B", 98, action="folds", justacted=True), player("A", 97, chips=3)),
        ],
        "USD",
    )

    assert [entry.action for entry in entries] == [None, "big blind", "raises", "folds"]
    assert action_style(entries[2].action) is ACTION_STYLES["raises"]
    assert action_style(entries[3].action) is ACTION_STYLES["folds"]
